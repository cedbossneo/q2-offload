#!/usr/bin/env bash
# Validate an installed host: Klipper parses the whole config against the firmware
# dictionaries (batch mode, no hardware), and Moonraker starts without warnings.
# Usage: scripts/validate-config.sh <firmware-dir>
set -Eeuo pipefail
. "$(dirname "$0")/lib.sh"

fw="$(cd "${1:?usage: $0 <firmware-dir>}" && pwd)"
data="${HOME}/printer_data"
tmp="$(mktemp -d)"
log="${tmp}/klippy.log"

info "Klipper batch mode against q2-main/q2-thr/q2-box dictionaries"
"${HOME}/klippy-env/bin/python" "${HOME}/klipper/klippy/klippy.py" "${data}/config/printer.cfg" \
    -i /dev/null -o "${tmp}/out" -l "$log" \
    -d "${fw}/q2-main.dict" -d "THR=${fw}/q2-thr.dict" -d "unit0=${fw}/q2-box.dict" || true
if grep -Eq "^(Config error|Error|Internal error)|Traceback|Unhandled exception|Option '.*' is not valid" "$log" \
    || ! grep -q "Configured MCU 'unit0'" "$log"; then
    grep -Ev '^(Stats|Args|Git version|Untracked files|Branch|Remote|Tracked URL|CPU|Python|Start printer)' "$log" | tail -60
    die "Klipper rejected the configuration"
fi
grep -E "^Configured MCU|^Loaded MCU|mcu '.*': Starting" "$log" | sort -u || true
ok "Klipper configuration valid"

info "Moonraker configuration"
"${HOME}/moonraker-env/bin/python" "${HOME}/moonraker/moonraker/moonraker.py" -d "$data" > /dev/null 2>&1 &
pid=$!
# Moonraker's update manager runs git on the repos at start: wait for it to exit and for those
# git commands to release their locks, or the next install step finds index.lock and fails
stop_moonraker() {
    kill "$pid" 2>/dev/null || true
    wait "$pid" 2>/dev/null || true
    local _
    for _ in $(seq 1 40); do
        compgen -G "${HOME}/*/.git/index.lock" > /dev/null || return 0
        sleep 0.25
    done
    warn "a git lock is still there after Moonraker stopped"
}
trap stop_moonraker EXIT
for _ in $(seq 1 30); do
    sleep 1
    info_json="$(curl -s localhost:7125/server/info || true)"
    [ -n "$info_json" ] && break
done
[ -n "$info_json" ] || die "Moonraker did not start"
echo "$info_json" | python3 -c '
import json, sys
r = json.load(sys.stdin)["result"]
print("components:", ", ".join(sorted(r["components"])))
bad = [w for w in r.get("warnings", []) if not any(k in w.lower() for k in ("klippy", "dbus", "polkit", "policykit"))]  # host-permission warnings: not config
failed = r.get("failed_components", [])
for w in bad: print("WARNING:", w)
if failed: print("FAILED:", failed)
sys.exit(1 if (bad or failed) else 0)
' || die "Moonraker reported warnings"
ok "Moonraker configuration valid"
