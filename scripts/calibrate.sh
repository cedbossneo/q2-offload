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

# The load cell ships with standard values (printer.cfg [load_cell_probe]): the scale and zero
# of a Q2, the same sensor on every unit, so like the stock firmware nothing is calibrated.
# What must be checked, before anything homes Z, is that this printer's load cell reacts.
load_cell_check() {
    [ "$(status_field load_cell_probe is_calibrated)" = True ] || {
        warn "the load cell has no values in printer.cfg: restore counts_per_gram and reference_tare_counts in [load_cell_probe] (https://cedbossneo.github.io/q2-offload/docs/install/calibrate/), then run ./install.sh calibrate"
        return 1; }
    while ! load_cell_tap_test; do
        confirm "Try the load cell check again?" y || {
            warn "nothing will home the printer until the check passes: run ./install.sh calibrate"; return 1; }
    done
}

# Before anything homes Z: the user taps the nozzle three times, and the load cell must see
# each tap, in the right direction, and come back to zero. A dead, inverted or stuck load
# cell would let the nozzle drive into the bed at the first homing.
LOAD_CELL_TESTED=0
LOAD_CELL_TAP_G=150      # well above trigger_force (75 g)
LOAD_CELL_REST_G=40      # back to rest between and after the taps
LOAD_CELL_TAPS=3
LOAD_CELL_TAP_SECONDS=20

load_cell_tap_test() {
    [ "$LOAD_CELL_TESTED" = 1 ] && return 0
    [ "$(status_field load_cell_probe is_calibrated)" = True ] || {
        warn "load cell not calibrated: no homing"; return 1; }
    cat <<EOF

${C_WARN}Load cell check${C_OFF} (it is the Z endstop: if it does not react, the nozzle drives into the bed)
Nothing must touch the nozzle. When asked, push the nozzle UP gently with a finger,
${LOAD_CELL_TAPS} times, letting go between taps (${LOAD_CELL_TAP_SECONDS} seconds).
EOF
    confirm "Ready?" y || return 1
    gcode "LOAD_CELL_TARE" || return 1
    sleep 1
    info "Tap the nozzle ${LOAD_CELL_TAPS} times now (${LOAD_CELL_TAP_SECONDS} s)"
    local result
    result="$(python3 - "$LOAD_CELL_TAP_SECONDS" "$LOAD_CELL_TAP_G" "$LOAD_CELL_REST_G" "$LOAD_CELL_TAPS" <<'PY'
import json, sys, time, urllib.request
seconds, tap_g, rest_g, need = float(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3]), int(sys.argv[4])
url = "http://localhost:7125/printer/objects/query?load_cell_probe=force_g,max_force_g,min_force_g,errors,overflows"
def read():
    return json.load(urllib.request.urlopen(url, timeout=2))["result"]["status"]["load_cell_probe"]
high = low = 0.0
taps, released = 0, True
end = time.time() + seconds
while time.time() < end and taps < need:
    s = read()
    force = s.get("force_g", 0)
    high = max(high, s.get("max_force_g", 0), force)
    low = min(low, s.get("min_force_g", 0), force)
    # a tap: above tap_g after being back under rest_g
    if released and force >= tap_g:
        taps, released = taps + 1, False
    elif not released and force < rest_g:
        released = True
    time.sleep(0.05)
time.sleep(1.5)
s = read()
if s.get("errors") or s.get("overflows"):
    print("sensor errors: %s errors, %s overflows" % (s.get("errors"), s.get("overflows")))
elif high < tap_g and low <= -tap_g:
    print("force goes NEGATIVE when the nozzle is pushed up (%.0f g): set sensor_orientation: inverted" % low)
elif high < tap_g:
    print("no tap seen (max %.0f g, %.0f g needed): check the THR cable and the load cell" % (high, tap_g))
elif taps < need:
    print("saw %d of %d taps: push a little firmer, and let go fully between taps" % (taps, need))
elif abs(s.get("force_g", 0)) > rest_g:
    print("does not come back to zero after the taps (%.0f g)" % s.get("force_g", 0))
else:
    print("OK %.0f" % high)
PY
)" || result="could not read the load cell"
    if [ "${result%% *}" = OK ]; then
        ok "load cell saw ${LOAD_CELL_TAPS} taps (up to ${result#OK } g) and returns to zero"
        LOAD_CELL_TESTED=1
        return 0
    fi
    warn "load cell check failed: ${result}"
    return 1
}

calibrate_offer() {
    local saved=0
    if [ "${ASSUME_YES:-0}" = 1 ] || [ ! -t 0 ]; then
        info "Skipping the calibrations (non-interactive run): see https://cedbossneo.github.io/q2-offload/docs/install/calibrate/"
        return 0
    fi
    cat <<EOF

${C_INFO}Calibration${C_OFF}
The printer now runs on standard Q2 values: Qidi's PID and input shaper, the load cell
values (the same sensor on every Q2)$(has_box && printf ', the Box gear rotation distance (13.8) and bowden length (%s mm)\nof a stock Box' "$BOX_BOWDEN_LENGTH"). That is enough to print, but this printer's own values are safer and better.
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

Still worth doing yourself (https://cedbossneo.github.io/q2-offload/docs/install/calibrate/):
  - bed: Z_TILT_ADJUST, BED_MESH_CALIBRATE
$(has_box && echo '  - Box gears and bowden: MMU_CALIBRATE_GEAR, MMU_CALIBRATE_BOWDEN (Happy Hare)')
  - pressure advance per filament: autopa
EOF
}
