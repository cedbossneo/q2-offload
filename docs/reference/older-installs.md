---
title: Updating an older install
description: Changes that updates can't make for you, because printer.cfg and your slicer presets are yours.
---

Updates never change `printer.cfg` or your slicer presets. When a version brings something
worth having there, it is listed here. Each one is optional unless it says otherwise.

## Board fan

Once an update has moved Klipper to a version with `temperature_limits` (q2-offload's Klipper
patch 0009; an older Klipper refuses the option), add to `[controller_fan board_fan]` in
`printer.cfg`, then restart Klipper:

```ini
stepper: stepper_x, stepper_y, stepper_z, stepper_z1, extruder
idle_timeout: 60
idle_speed: 1.0
temperature_limits: temperature_sensor Mainboard_MCU:45, heater_generic chamber:40
```

Z now stays off at boot unless a power-loss resume is pending, so without `idle_speed` or these
limits the fan stops as soon as the motors do.

## Chamber

To match the stock firmware, in `[heater_generic chamber]` add `soft_start_time: 5` and
`soft_start_power: 0.3`, and set `shutdown_speed: 1.0` in `[controller_fan chamber_fan]` and
`[fan_generic chamber_circulation_fan]`. Needs the same Klipper version as the board fan
options.

## Faster bed mesh

In `printer.cfg`: `speed: 200` and `horizontal_move_z: 3` in `[bed_mesh]`, `lift_speed: 10` and
`sample_retract_dist: 2` in `[load_cell_probe]`.

## Slicer start G-code

Update the start G-code to the current [purge lines](slicer-gcode.md#start-g-code). The mesh now
covers only the part, so the old fixed lines at the front of the bed fall outside it.

## Coming from PrintGuard

PrintGuard was the failure detection before the `detect` component. The first update after it
was replaced removes its container and switches the component to `detect`; updates also remove
its images (about 750 MB each) unless another container uses them. Its data stays in
`/srv/printguard`: remove it with `sudo rm -r /srv/printguard` once you no longer need it.
