#!/bin/bash

# Read the number from the plr_record file
number=$(cat @HOME@/printer_data/scripts/plr/plr_record)

# Make sure it is a number
if ! [[ $number =~ ^[0-9]+$ ]] ; then
   echo "Error: No valid number found in @HOME@/printer_data/scripts/plr/plr_record"
   exit 1
fi

# Check whether the gcode_lines field exists
if grep -q "^gcode_lines = " @HOME@/printer_data/config/saved_variables.cfg; then
    # If it exists, update its value
    sed -i "s/^gcode_lines = [0-9]*/gcode_lines = $number/" @HOME@/printer_data/config/saved_variables.cfg
else
    # Otherwise, add the field
    echo "gcode_lines = $number" >> @HOME@/printer_data/config/saved_variables.cfg
fi
