# shellcheck shell=bash
# First-install calibration: make the printer usable with standard Q2 values, then offer
# the calibrations that only take a few minutes (PID, input shaper). Source after verify.sh.

# Run G-code through Moonraker and wait for it to finish (PID and shaper take minutes)
gcode() {
    local reply
    reply="$(curl -s -m 3600 -H 'Content-Type: application/json' \
        -d "$(python3 -c 'import json,sys; print(json.dumps({"script": sys.argv[1]}))' "$1")" \
        localhost:7125/printer/gcode/script)"
    echo "$reply" | grep -q '"result": *"ok"' && return 0
    warn "'$1' failed: $(echo "$reply" | python3 -c 'import json,sys
try: print(json.load(sys.stdin)["error"]["message"])
except Exception: print("no answer from Moonraker")')"
    return 1
}

# Value of one status field, e.g. status_field load_cell_probe reference_tare_counts
status_field() {
    moonraker_json "/printer/objects/query?$1=$2" | python3 -c 'import json,sys
v = json.load(sys.stdin)["result"]["status"][sys.argv[1]].get(sys.argv[2])
print("" if v is None else v)' "$1" "$2"
}

restart_klipper() {
    sudo systemctl restart klipper
    sleep 3
    wait_ready
}

# The probe refuses to work until reference_tare_counts is known. Measure it now (nozzle
# touching nothing) and write it into printer.cfg next to the standard counts_per_gram.
calibrate_load_cell_tare() {
    local tare
    [ "$(status_field load_cell_probe is_calibrated)" = True ] && return 0
    [ -n "$(status_field load_cell_probe counts_per_gram)" ] || {
        warn "load cell has no counts_per_gram: run LOAD_CELL_CALIBRATE (docs/calibration.md)"; return 1; }
    cat <<EOF

${C_WARN}Load cell zero${C_OFF}: the Z probe needs the load cell reading at rest.
Make sure NOTHING touches the nozzle (no print, no tool, no filament blob on the bed under it).
EOF
    confirm "Measure it now?" y || { warn "probing will fail until LOAD_CELL_CALIBRATE is done"; return 1; }
    gcode "LOAD_CELL_TARE" || return 1
    sleep 1
    tare="$(status_field load_cell_probe tare_counts)"
    [[ "$tare" =~ ^-?[0-9]+(\.[0-9]+)?$ ]] || { warn "could not read the load cell"; return 1; }
    tare="${tare%.*}"
    python3 - "${CFG}/printer.cfg" "$tare" <<'EOF'
import re, sys
path, tare = sys.argv[1], sys.argv[2]
s = open(path).read()
body, sep, autosave = s.partition('#*# <---------------------- SAVE_CONFIG')
m = re.search(r'^\[load_cell_probe\]\n((?:[^\[].*\n|\n)*)', body, re.M)
if not m or re.search(r'^reference_tare_counts\s*:', m.group(1), re.M):
    sys.exit(0)
section = re.sub(r'^(counts_per_gram\s*:.*\n)', r'\1reference_tare_counts: %s\n' % tare, m.group(1), count=1, flags=re.M)
open(path, 'w').write(body[:m.start(1)] + section + body[m.end(1):] + sep + autosave)
EOF
    restart_klipper || return 1
    [ "$(status_field load_cell_probe is_calibrated)" = True ] \
        || { warn "load cell still not calibrated: run LOAD_CELL_CALIBRATE"; return 1; }
    ok "load cell zero: ${tare} counts"
    load_cell_tap_test
}

# Before anything that homes Z: the user taps the nozzle and the load cell must see it, in
# the right direction, and come back to zero. A dead, inverted or stuck load cell would let
# the nozzle drive into the bed.
LOAD_CELL_TESTED=0
LOAD_CELL_TAP_G=150      # well above trigger_force (75 g)
LOAD_CELL_REST_G=40      # back to rest after the taps
LOAD_CELL_TAP_SECONDS=20

load_cell_tap_test() {
    [ "$LOAD_CELL_TESTED" = 1 ] && return 0
    [ "$(status_field load_cell_probe is_calibrated)" = True ] || {
        warn "load cell not calibrated: no homing"; return 1; }
    cat <<EOF

${C_WARN}Load cell check${C_OFF} (it is the Z endstop: if it does not react, the nozzle drives into the bed)
When asked, push the nozzle UP gently with a finger, a few times, for ${LOAD_CELL_TAP_SECONDS} seconds.
EOF
    confirm "Ready?" y || return 1
    gcode "LOAD_CELL_TARE" || return 1
    sleep 1
    info "Tap the nozzle now (${LOAD_CELL_TAP_SECONDS} s)"
    local result
    result="$(python3 - "$LOAD_CELL_TAP_SECONDS" "$LOAD_CELL_TAP_G" "$LOAD_CELL_REST_G" <<'PY'
import json, sys, time, urllib.request
seconds, tap_g, rest_g = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
url = "http://localhost:7125/printer/objects/query?load_cell_probe=force_g,max_force_g,min_force_g,errors,overflows"
def read():
    return json.load(urllib.request.urlopen(url, timeout=2))["result"]["status"]["load_cell_probe"]
high = low = 0.0
end = time.time() + seconds
while time.time() < end:
    s = read()
    high, low = max(high, s.get("max_force_g", 0)), min(low, s.get("min_force_g", 0))
    time.sleep(0.2)
time.sleep(1.5)
s = read()
if s.get("errors") or s.get("overflows"):
    print("sensor errors: %s errors, %s overflows" % (s.get("errors"), s.get("overflows")))
elif high < tap_g and low <= -tap_g:
    print("force goes NEGATIVE when the nozzle is pushed up (%.0f g): set sensor_orientation: inverted" % low)
elif high < tap_g:
    print("no tap seen (max %.0f g, %.0f g needed): check the THR cable and the load cell" % (high, tap_g))
elif abs(s.get("force_g", 0)) > rest_g:
    print("does not come back to zero after the taps (%.0f g)" % s.get("force_g", 0))
else:
    print("OK %.0f" % high)
PY
)" || result="could not read the load cell"
    if [ "${result%% *}" = OK ]; then
        ok "load cell reacts (${result#OK } g) and returns to zero"
        LOAD_CELL_TESTED=1
        return 0
    fi
    warn "load cell check failed: ${result}"
    warn "nothing will home the printer; fix it, then run the calibrations from docs/calibration.md"
    return 1
}

calibrate_offer() {
    local saved=0
    if [ "${ASSUME_YES:-0}" = 1 ] || [ ! -t 0 ]; then
        info "Skipping the calibrations (non-interactive run): see docs/calibration.md"
        return 0
    fi
    cat <<EOF

${C_INFO}Calibration${C_OFF}
The printer now runs on standard Q2 values: Qidi's PID and input shaper, a load cell scale
measured on another Q2, the Box gear rotation distance (13.8) and bowden length (${BOX_BOWDEN_LENGTH} mm)
of a stock Box. That is enough to print, but this printer's own values are safer and better.
Two of them take a few minutes and can run now (stay next to the printer):
EOF
    if confirm "PID: heat the hotend to 250 °C and the bed to 70 °C, about 10 minutes?" y; then
        gcode "PID_CALIBRATE HEATER=extruder TARGET=250" && gcode "PID_CALIBRATE HEATER=heater_bed TARGET=70" \
            && saved=1
        gcode "TURN_OFF_HEATERS" || true
    fi
    if confirm "Input shaper: home the printer and shake the toolhead, about 5 minutes (bed must be empty)?" y; then
        if load_cell_tap_test; then
            gcode "G28" && gcode "SHAPER_CALIBRATE" && saved=1
        fi
    fi
    if [ "$saved" = 1 ]; then
        info "Saving the results (SAVE_CONFIG restarts Klipper)"
        gcode "SAVE_CONFIG" || true
        sleep 5
        wait_ready || true
    fi
    cat <<EOF

Still worth doing yourself (docs/calibration.md):
  - load cell scale with a known weight: LOAD_CELL_CALIBRATE
  - Box gears and bowden: MMU_CALIBRATE_GEAR, MMU_CALIBRATE_BOWDEN (Happy Hare)
  - pressure advance per filament: autopa
EOF
}
