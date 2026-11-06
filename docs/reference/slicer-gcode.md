---
title: Slicer and G-code
description: The OrcaSlicer presets, start and end G-code, multi-material settings, and the spool presets.
---

`slicer/orca/` holds the OrcaSlicer presets used on a q2-offload Q2 and Qidi Box, and the Q2
Spool Presets plugin. Setup steps: [Set up OrcaSlicer](../install/slicer.md).

| File | Preset |
|---|---|
| `machine/Q2 Offload 0.4 nozzle.json` | printer: start, end, tool change and layer G-code, machine limits |
| `process/0.20mm Standard @Q2 Offload.json` | print settings (0.20 mm, 4 walls, 20 % honeycomb, organic supports) |
| `filament/Generic {PLA,PETG,ABS,TPU} @Q2 Offload.json` | filament templates with the multi-material fields set for Happy Hare |

They inherit Orca's own Qidi Q2 and Generic presets, so only the differences are stored.

## The printer agent

The printer preset uses Orca's `qidi` printer agent. q2-offload publishes the Happy Hare gates
in the layout of the stock Box firmware (`host/extras/qidi_box_compat.py`), so with **Use
printer agents** on:

- **Sync filaments** reads the colours and materials of the four slots;
- the print dialog lets you pick a slot per filament: `PRINT_START` turns the choice into a
  Happy Hare tool map (`MMU_TTG_MAP`). It stays for a power-loss resume, and goes back to
  one-to-one at the next print that did not choose slots.

**Timelapse and Auto bed leveling in the print dialog have no effect**: the agents don't send
them. The adaptive mesh always runs, and timelapse follows Moonraker's settings.

## Spool presets

Orca matches a slot to a preset by `filament_id`, and a preset with a parent takes the id of
that parent, so it can't tell two spools of the same PLA apart. q2-offload therefore generates
one parentless preset per spool from Spoolman (`scripts/orca-spool-presets.py`,
`q2-spool-presets.timer`, every minute), with the id `QD_1_0_<10000 + spool id>`, and the Box
publishes that number for the spool in each gate. The plugin reads them from
`http://<host>/q2-spools/index.json`.

Settings come from Spoolman, so edit them there: the Spoolman columns (colour, density,
diameter, nozzle temperature), then any filament extra field named `orca_<option>`, which wins
over them (`orca_pressure_advance`, `orca_nozzle_temperature`…). `orca_base_preset` chooses the
Orca preset to start from (`SUNLU PETG @System`); the default is the Generic preset of the
material. Fields must exist in Spoolman (Settings → Extra fields).

## Start G-code

```
SET_PRINT_STATS_INFO TOTAL_LAYER={total_layer_count}
PRINT_START BED=… HOTEND=… CHAMBER=… EXTRUDER=… INITIAL_TOOL={initial_tool}
    TOTAL_TOOLCHANGES=!total_toolchanges! REFERENCED_TOOLS=!referenced_tools!
    TOOL_COLORS=!colors! TOOL_TEMPS=!temperatures! TOOL_MATERIALS=!materials!
    FILAMENT_NAMES=!filament_names! PURGE_VOLUMES=!purge_volumes!
M83
G92 E0
G4 P3000
_BOX_PURGE_LINES FLOW={outer_wall_volumetric_speed} HEIGHT=[initial_layer_print_height]
    MIN_X={first_layer_print_min[0]} MIN_Y={first_layer_print_min[1]}
    MAX_X={first_layer_print_max[0]} MAX_Y={first_layer_print_max[1]}
```

- The `!…!` values are filled in by Happy Hare's Moonraker component when the file is uploaded
  (`[mmu_server] enable_file_preprocessor`). Print through Moonraker (upload from Orca, Fluidd
  or Mainsail), not from a USB stick.
- `PRINT_START` (`config/klipper/gcode_macro_mmu.cfg`) does the rest, in this order: Box heating
  for the materials used ([drying](../use/drying.md#while-printing)), TPU detection (sync
  feedback off), homing, nozzle wipe, second homing with a clean nozzle, bed and chamber
  heating, Z tilt, adaptive bed mesh, nozzle heating, Happy Hare setup, the pressure advance
  calibration of new spools waiting for it, then the load of the first tool with a purge into
  the bucket.
- The mesh covers the part with a 10 mm margin (Klipper's `ADAPTIVE=1`). The two purge lines go
  5 mm in front of the first layer, skirt and brim included, so they stay inside it; behind the
  part if there is no room in front, and skipped on a full plate. They only prime the nozzle;
  the filament is already loaded. `M83` is needed there because Orca only switches to relative
  extrusion after the start G-code.
- Macros are named `_BOX_…`: Klipper cuts a command name at its first digit, so a macro with a
  digit in the middle of its name loads fine and then fails with `Unknown command`.

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
  statistics, and leaves the filament loaded (`variable_unload_tool: False` in `overrides.cfg`;
  `MMU_END UNLOAD=1` unloads).
- Retract, lift, park at the back (Y first, then X), and lower the bed to half height for short
  prints so the part is easy to reach.
- `PRINT_END` turns off the heaters, the fans, the sensors and the Box print heating
  (`DISABLE_BOX_HEATER`).

## Other G-code

- **Change filament G-code:** `T[next_extruder]`. Happy Hare does the whole tool change (tip
  cut, unload, load, purge into the bucket).
- **Layer change G-code:** `SET_PRINT_STATS_INFO CURRENT_LAYER=…` (layer count in the
  interfaces), `MMU_UPDATE_HEIGHT` (tells Happy Hare the current print height), and a timelapse
  frame (moonraker-timelapse).

## Multi-material fields

Orca's multi-material settings are written for a Prusa MMU, where the slicer itself shapes the
filament tip, cools it, and pushes it in and out. With Happy Hare the Box and its macros do all
of that, so these must be **0**, or the slicer and Happy Hare both move the filament at every
tool change:

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

There is no prime tower: Happy Hare purges into the Q2 bucket after each tool change, with the
volumes Orca computes from the flushing matrix (`PURGE_VOLUMES`). Keep the flushing volumes in
Orca; the bucket purge uses them.

**Filament type matters.** The Box heating and drying tables, and the TPU detection, use the
filament type (`PLA`, `PETG`, `ABS`, `TPU`, `PA-CF`…). An unknown type doesn't heat the Box.

## Machine limits

The acceleration limits (5600 mm/s² on X and Y) come from our input shaper calibration. Run
`SHAPER_CALIBRATE` on your printer and set **Printer → Motion ability** and the process
accelerations from your own results.
