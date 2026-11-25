#!/usr/bin/env bash
# A config file edited by hand: the update keeps it, says so at the end with what to do, writes
# a readable .new, and "install.sh use-new" takes the new version (the edited one kept as .bak).
# Run by tests/host/run.sh as the install user, after a CI install.
set -euo pipefail
cfg="${HOME}/printer_data/config/gcode_macro_mmu.cfg"
kept="${HOME}/.config/q2-offload/kept-configs"
fail() { echo "FAIL: $*"; exit 1; }

echo "# edited by hand" >> "$cfg"
out="$(./install.sh host --ci --yes)"
grep -q "Config files kept" <<<"$out" || fail "no kept-files notice at the end"
grep -q "printer_data/config/gcode_macro_mmu.cfg" <<<"$out" || fail "edited file not listed"
grep -q "install.sh use-new" <<<"$out" || fail "no instructions"
grep -qxF "$cfg" "$kept" || fail "not in ${kept}"
[ "$(stat -c %a "${cfg}.new")" = 644 ] || fail "${cfg}.new is not 644"

./install.sh use-new --ci
grep -q "edited by hand" "$cfg" && fail "use-new left the edited file"
grep -q "edited by hand" "$cfg".bak-* || fail "edited file not kept as .bak"
[ ! -e "${cfg}.new" ] || fail ".new left behind"
[ ! -s "$kept" ] || fail "kept list not emptied"
[ "$(stat -c %a "$cfg")" = 644 ] || fail "${cfg} is not 644"

out="$(./install.sh host --ci --yes)"
grep -q "Config files kept" <<<"$out" && fail "notice shown with nothing kept"
echo "kept config files: ok"
