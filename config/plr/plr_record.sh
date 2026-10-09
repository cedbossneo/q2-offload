#!/bin/bash
# Record the current G-code position (in bytes) for power-loss resume.
# The stock Qidi Klipper did this; mainline Klipper does not.
POS="$1"
[[ "$POS" =~ ^[0-9]+$ ]] || exit 0
echo "$POS" > @HOME@/printer_data/scripts/plr/plr_record
