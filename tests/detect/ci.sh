#!/usr/bin/env bash
# CI for failure detection: the ML API image (Obico's, pinned in VERSIONS and pulled as the
# installer does, or <image> already built), q2-detect's requirements in a venv like
# host_detect_env, and the end-to-end test on a plain frame (the ML API must answer and frames
# must be analysed; no failure to find). ML_API_ARGS goes to the ML API's docker run.
# Usage: tests/detect/ci.sh [image]
set -Eeuo pipefail
# shellcheck source=../../scripts/lib.sh
. "$(dirname "$0")/../../scripts/lib.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
if [ -n "${1:-}" ]; then
    image="$1"
else
    image="$(obico_ml_api_image)"
    info "Pulling Obico's ML API (obico-server ${OBICO_SERVER_REF:0:12})"
    pull_image "$image" || die "could not pull ${image}"
fi
python3 -m venv "${work}/env"
"${work}/env/bin/pip" install -q -r "${Q2_ROOT}/detect/requirements.txt"
"${work}/env/bin/python" -c 'import sys; from PIL import Image; Image.new("RGB", (1280, 720), (90, 90, 90)).save(sys.argv[1])' \
    "${work}/frame.jpg"
PYTHON="${work}/env/bin/python" "${Q2_ROOT}/tests/detect/e2e.sh" "$image" "${work}/frame.jpg"
