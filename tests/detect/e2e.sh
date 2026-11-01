#!/usr/bin/env bash
# q2-detect end to end: the real service, Obico's ML API container and a fake Moonraker whose
# webcam serves <jpeg>, with frames every 0.5 s. Checks that frames are analysed by the ML API,
# and with --expect-pause that a print showing a failure gets paused (pause mode, a printer
# whose long-term mean is already learnt). PYTHON must have detect/requirements.txt installed.
# Usage: tests/detect/e2e.sh <ml-api-image> <jpeg> [--expect-pause]
set -Eeuo pipefail
root="$(cd "$(dirname "$0")/../.." && pwd)"
image="${1:?ml-api image}"; jpeg="${2:?jpeg}"; expect_pause="${3:-}"
python="$("${PYTHON:-python3}" -c 'import sys; print(sys.executable)')"
work="$(mktemp -d)"
mr=7999; port=7131; frames=40
pids=()

cleanup() {
    for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; done
    docker rm -f q2-detect-e2e-ml >/dev/null 2>&1 || true
    rm -rf "$work"
}
trap cleanup EXIT

status() { curl -sf -m 5 "http://127.0.0.1:${port}/api/status"; }
field() { "$python" -c "import json, sys; d = json.load(sys.stdin); print(eval(sys.argv[1], {}, {'d': d}))" "$1"; }

# Docker Desktop has no host network: there the ML API reaches the service through the host
if [ "$(uname)" = Darwin ]; then
    docker run -d --name q2-detect-e2e-ml -p 127.0.0.1:3333:3333 "$image" >/dev/null
    listen=0.0.0.0; frame_base="http://host.docker.internal:${port}"
else
    docker run -d --name q2-detect-e2e-ml --network host "$image" \
        gunicorn --bind 127.0.0.1:3333 --workers 1 --timeout 120 wsgi >/dev/null
    listen=127.0.0.1; frame_base="http://127.0.0.1:${port}"
fi

mkdir -p "${work}/data"
echo '{"lifetime": 2000, "long": 0.0}' > "${work}/data/baseline.json"
echo '{"mode": "pause"}' > "${work}/data/settings.json"
"$python" "${root}/tests/detect/fake_moonraker.py" "$jpeg" "$mr" > "${work}/moonraker.log" 2>&1 &
pids+=($!)
PYTHONPATH="${root}/detect" "$python" -m q2_detect --data "${work}/data" --moonraker "ws://127.0.0.1:${mr}/websocket" \
    --ml-api http://127.0.0.1:3333 --host "$listen" --port "$port" --frame-base "$frame_base" --frame-s 0.5 \
    > "${work}/q2-detect.log" 2>&1 &
pids+=($!)

for _ in $(seq 120); do
    curl -sf -m 2 http://127.0.0.1:3333/hc/ >/dev/null 2>&1 && status >/dev/null 2>&1 && break
    sleep 1
done
curl -sf -m 5 -X POST "http://127.0.0.1:${mr}/control?state=printing&filename=e2e.gcode" >/dev/null

done_frames=0
for _ in $(seq 240); do
    done_frames="$(status | field "(d['print'] or {}).get('frame', 0)")"
    [ "$done_frames" -ge "$frames" ] && break
    if [ -n "$expect_pause" ] && [ "$(curl -sf "http://127.0.0.1:${mr}/control" | field "d['pauses']")" -ge 1 ]; then break; fi
    sleep 1
done
echo "--- q2-detect log"; tail -15 "${work}/q2-detect.log"
summary="$(status | field "(d['ml_api'], d['print']['frame'], round(max(d['print']['series']['p'] or [0]), 2), [x['kind'] for x in d['print']['decisions']])")"
echo "ml_api, frames, highest p, decisions: ${summary}"
[ "$(status | field "d['ml_api']['ok']")" = True ] || { echo "FAIL: the ML API did not answer"; exit 1; }
[ "$done_frames" -ge 3 ] || { echo "FAIL: only ${done_frames} frames analysed"; exit 1; }
if [ -n "$expect_pause" ]; then
    pauses="$(curl -sf "http://127.0.0.1:${mr}/control" | field "d['pauses']")"
    [ "$pauses" -ge 1 ] || { echo "FAIL: the failing print was not paused"; exit 1; }
    echo "paused by q2-detect (${pauses} pause request)"
fi
echo "e2e ok"
