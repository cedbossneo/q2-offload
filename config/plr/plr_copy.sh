#!/bin/bash
# Copy the running G-code into .temp/ for power-loss resume.
# The stock Qidi Moonraker did this; mainline Moonraker does not.
D=@HOME@/printer_data/.temp
SRC="$1"
[ -f "$SRC" ] || { echo "PLR: source file not found: $SRC"; exit 1; }
mkdir -p "$D"
rm -f "$D"/*.gcode
cp -f "$SRC" "$D"/ && echo "PLR: copied: $(basename "$SRC")"
