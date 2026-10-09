#!/bin/bash 
# Stock Qidi power-loss-recovery script, paths adapted by q2-offload
# shellcheck disable=SC2002,SC2004,SC2034
 
CONFIG_FILE="@HOME@/printer_data/config/saved_variables.cfg" 

BED_TEMP="" 
GCODE_LINES="" 
CHAMBER_TEMP="" 
EXTRUDER_TEMP="" 
 
BED_TEMP=$(awk -F " = " '/bed_temp/ {gsub(/'\''/, "", $2); print $2}' $CONFIG_FILE) 
GCODE_LINES=$(awk -F " = " '/gcode_lines/ {gsub(/'\''/, "", $2); print $2}' $CONFIG_FILE) 
CHAMBER_TEMP=$(awk -F " = " '/hot_temp/ {gsub(/'\''/, "", $2); print $2}' $CONFIG_FILE) 
EXTRUDER_TEMP=$(awk -F " = " '/print_temp/ {gsub(/'\''/, "", $2); print $2}' $CONFIG_FILE) 
 
echo "" 
echo "Running power-loss resume" 
echo "GCODE_LINES: $GCODE_LINES" 
echo "EXTRUDER_TEMP: $EXTRUDER_TEMP" 
echo "BED_TEMP: $BED_TEMP" 
echo "CHAMBER_TEMP: $CHAMBER_TEMP" 

rm -f "@HOME@/printer_data/.temp/plr.gcode" 
GCODE_PATH=$(find @HOME@/printer_data/.temp/ -maxdepth 1 -name "*.gcode" -print -quit)

if [ -z "$GCODE_PATH" ]; then
    echo "Error: no gcode file found in @HOME@/printer_data/.temp/"
    exit 1
fi

echo "Found gcode file: $GCODE_PATH"

GCODE_FILENAME=$(basename "$GCODE_PATH")
echo "File name: $GCODE_FILENAME"

# if grep -q "gcode_filename" "$CONFIG_FILE"; then
#     sed -i "s/gcode_filename = .*/gcode_filename = '$GCODE_FILENAME'/" "$CONFIG_FILE"
# else
#     echo "gcode_filename = '$GCODE_FILENAME'" >> "$CONFIG_FILE"
# fi

TEMP_FILE=$(mktemp)

# GCODE_LINES holds a byte offset (from mainline Klipper's
# virtual_sdcard.file_position), not a line number.
head -c "$GCODE_LINES" "$GCODE_PATH" > "$TEMP_FILE.header"
tail -c +$(($GCODE_LINES + 1)) "$GCODE_PATH" > "$TEMP_FILE.footer"

z_position=$(cat "$TEMP_FILE.header" | sed -n '/;Z:/s/.*;Z:\([0-9.]*\).*/\1/p' | tail -n 1)
if [ -z "$z_position" ]; then
    z_position=$(cat "$TEMP_FILE.header" | sed -n '/; Z_HEIGHT: /s/.*;\x20Z_HEIGHT:\x20\([0-9.]*\).*/\1/p' | tail -n 1)
fi
echo "z_position: $z_position"

isInFile=$(grep -c "thumbnail end" "$GCODE_PATH")

{
    # if [ $isInFile -ne 0 ]; then
    #     sed -n '/thumbnail begin/,/thumbnail end/p' "$GCODE_PATH"
    #     echo ";"
    #     echo ""
    # fi
    
    echo "SET_KINEMATIC_POSITION Z=$z_position"

    grep "EXCLUDE_OBJECT_DEFINE" "$TEMP_FILE.header"
    
    echo "M109 S$EXTRUDER_TEMP"
    echo "M140 S$BED_TEMP"
    echo "M104 S$EXTRUDER_TEMP"
    
    echo "G91"
    echo "G1 Z5 F600"
    echo "G90"
    echo "G28 X Y"
    echo "G28 X"
    
    echo "CLEAR_NOZZLE_PLR hotend=$EXTRUDER_TEMP"
    
    echo "M190 S$BED_TEMP"
    echo "M191 S$CHAMBER_TEMP"
    
    grep "M106 S" "$TEMP_FILE.header" | tail -n 1
    grep "M106 P2 S" "$TEMP_FILE.header" | tail -n 1
    grep "M106 P3 S" "$TEMP_FILE.header" | tail -n 1
    
    echo "G90"
    echo "G1 Z$z_position"
    
    grep -E "M83|M82" "$TEMP_FILE.header" | tail -n 1
    
    echo "ENABLE_ALL_SENSOR"
    
    echo "G1 F6000"
    
    cat "$TEMP_FILE.footer"
} > "$TEMP_FILE"


# Write to gcodes/: mainline Klipper only opens a .gcode from that folder
# (the Q2 patch only redirects to .temp/ for .3mf files)
mv "$TEMP_FILE" "@HOME@/printer_data/gcodes/plr.gcode"
chmod 644 "@HOME@/printer_data/gcodes/plr.gcode"

rm -f "$TEMP_FILE.header" "$TEMP_FILE.footer"

echo "Power-loss resume file ready: $GCODE_PATH"