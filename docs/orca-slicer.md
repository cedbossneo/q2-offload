# OrcaSlicer profiles

`slicer/orca/` holds the OrcaSlicer presets we print with on a q2-offload Q2 + Qidi Box:

| File | Preset |
|---|---|
| `machine/Q2 Offload 0.4 nozzle.json` | printer: start/end/toolchange/layer G-code, machine limits |
| `process/0.20mm Standard @Q2 Offload.json` | print settings (0.20 mm, 4 walls, 20 % honeycomb, organic supports) |
| `filament/Generic {PLA,PETG,ABS,TPU} @Q2 Offload.json` | filament templates with the multi-material fields set for Happy Hare |

They inherit Orca's own Qidi Q2 and Generic presets, so only the differences are stored.

## Install

1. In OrcaSlicer, add the stock **Qidi Q2 0.4 nozzle** printer once (the presets inherit it).
2. **File → Import → Import Configs…** and select the six JSON files.
3. Select the **Q2 Offload 0.4 nozzle** printer, click the Wi-Fi icon next to it and set
   the host type to **Octo/Klipper** and the host to `http://<klipper-host>` (nginx forwards
   the API to Moonraker).
4. Set one filament per Box gate (T0–T3). For your own filaments, start from one of the
   templates, or copy the fields listed in [Multi-material fields](#multi-material-fields)
   into your preset.

## Start G-code

```
SET_PRINT_STATS_INFO TOTAL_LAYER={total_layer_count}
PRINT_START BED=… HOTEND=… CHAMBER=… EXTRUDER=… INITIAL_TOOL={initial_tool}
    TOTAL_TOOLCHANGES=!total_toolchanges! REFERENCED_TOOLS=!referenced_tools!
    TOOL_COLORS=!colors! TOOL_TEMPS=!temperatures! TOOL_MATERIALS=!materials!
    FILAMENT_NAMES=!filament_names! PURGE_VOLUMES=!purge_volumes!
; purge lines at the front of the bed
```

- The `!…!` values are filled in by Happy Hare's Moonraker component when the file is
  uploaded (`[mmu_server] enable_file_preprocessor`, installed by q2-offload). Print the
  G-code through Moonraker (upload from Orca, Fluidd or Mainsail), not from a USB stick.
- `PRINT_START` (`config/klipper/gcode_macro_mmu.cfg`) does everything else, in this
  order: Box heating for the materials used (see [calibration § 7](calibration.md#7-box-drying)),
  TPU detection (sync feedback off), homing, nozzle wipe, second homing with a clean
  nozzle, bed and chamber heating, Z tilt, adaptive bed mesh, nozzle heating, then Happy
  Hare setup and load of the first tool with a purge into the bucket.
- The two purge lines at the front of the bed only prime the nozzle; the filament is
  already loaded. `M83` is needed there because Orca only switches to relative extrusion
  after the start G-code.

## End G-code

```
MMU_END
G1 E-3 F1800
G0 Z{min(max_print_height, max_layer_z + 3)} F600
G0 Y270 F12000
G0 X90 Y270 F12000
{if max_layer_z < max_print_height / 2}G1 Z{max_print_height / 2 + 10} F600{endif}
PRINT_END
```

- `MMU_END` closes the Happy Hare print: releases the sync feedback, prints the gate
  statistics, and leaves the filament loaded (`variable_unload_tool: False` in
  `overrides.cfg`; `MMU_END UNLOAD=1` unloads).
- Retract, lift, park at the back (Y move first, then X), and lower the bed to half height
  for short prints so the part is easy to reach.
- `PRINT_END` turns off the heaters, the fans, the sensors and the Box print heating
  (`DISABLE_BOX_HEATER`).

## Other G-code

- **Change filament G-code:** `T[next_extruder]`. Happy Hare does the whole tool change
  (tip cut, unload, load, purge into the bucket).
- **Layer change G-code:** `SET_PRINT_STATS_INFO CURRENT_LAYER=…` (layer count in the
  UIs), `MMU_UPDATE_HEIGHT` (tells Happy Hare the current print height), and a timelapse
  frame (moonraker-timelapse).

## Multi-material fields

Orca's multi-material settings are written for a Prusa MMU, where the slicer itself
shapes the filament tip, cools it, and pushes it in and out. With Happy Hare the Box and
its macros do all of that, so these must be **0**, otherwise the slicer and Happy Hare both
move the filament at every tool change:

| Where | Setting | Value |
|---|---|---|
| Filament → Multimaterial | Loading speed, loading speed at the start | 0 |
| | Unloading speed, unloading speed at the start | 0 |
| | Number of cooling moves, initial/final cooling speed | 0 |
| | Delay after unloading (toolchange delay) | 0 |
| | Stamping loading speed, stamping distance | 0 |
| | Ramming (multi-tool ramming) | off |
| Printer → Multimaterial | Enable ramming, cooling tube length, parking position retraction, extra loading distance | 0 / off |
| Printer → Extruder | Retraction length on tool change | 0 |
| Process → Multimaterial | Prime tower | off |

There is no prime tower: Happy Hare purges into the Q2 bucket after each tool change,
with the volumes Orca computes from the flushing matrix (`PURGE_VOLUMES`). Keep the
flushing volumes in Orca; they are what the bucket purge uses.

**Filament type matters.** The Box heating and drying tables, and the TPU detection, use
the filament type (`PLA`, `PETG`, `ABS`, `TPU`, `PA-CF`…). Set it correctly in your
filament presets; an unknown type does not heat the Box.

## Machine limits

The acceleration limits (5600 mm/s² on X/Y) come from our input shaper calibration. Run
`SHAPER_CALIBRATE` on your printer and set **Printer → Motion ability** and the process
accelerations from your own results.
