---
title: Pressure advance and max flow
description: Measured with the load cell once per filament, saved in Spoolman, used by the slicer.
---

Pressure advance makes corners and line starts clean. It depends on the filament, so it is
measured once per filament, with the load cell, and saved in Spoolman.

## New spools from an NFC tag

When a [tag creates a spool](spools.md) whose filament has never been measured, the
touchscreen asks:

- **Calibrate now**: when the printer is not printing;
- **Now + max flow**: the same, after measuring the filament's [max flow](#max-flow), about 3
  more minutes;
- **At next print**: at the start of the next print that uses that spool;
- **Skip**.

The measurement takes about 3 minutes, in the air over the purge chute (some filament goes
into the bucket), then the nozzle is wiped on the brush. Each step shows on the touchscreen,
Mainsail and Fluidd, and the result stays on screen until you press OK.

It runs at the temperature and flow ratio your slicer prints that filament with, so the value
fits your prints. Once saved:

- the value is on the filament in Spoolman, so **another spool of the same filament is not
  measured again**;
- the OrcaSlicer presets pick it up within a minute (with the [Box tab](../install/slicer.md#the-box-tab)).

> [!NOTE]
> A result at the very edge of the range tried for the material is not saved: the
> measurement didn't find a clear best value. The spool stays waiting, and
> `SPOOL_PA_CALIBRATE SPOOL=<id>` tries again. At the start of a print it is only tried once.

## Max flow

The max volumetric speed is the highest flow (mm³/s) the printer sustains with a filament: the
slicer slows down wherever a print would need more. Measuring it is optional. Choose **Now +
max flow** when a new spool appears, or run `SPOOL_FLOW_CALIBRATE SPOOL=<Spoolman id>` for any
spool in a Box slot (not during a print).

The hotend extrudes in the air over the chute at increasing flow while the load cell measures
the force. While the filament melts fully, the force rises in step with the flow; past that it
climbs much faster, then the extruder skips. The test stops before that, and before the force
on the extruder gets near 2 kg: the steps get smaller as the force rises, and the extrusion
stops within about a second and a half when the force heads too high, so the gears and the
motor are never pushed hard. It takes about 3 minutes and at most 1 m of filament, into the
bucket.

The value saved keeps a 10 % margin under the last flow the printer sustained cleanly. It goes
on the filament in Spoolman, so the next spool of the same filament isn't measured again, and
the OrcaSlicer presets pick it up within a minute. With **Now + max flow**, the pressure advance
is then measured at a flow under it.

> [!NOTE]
> When the 2 kg limit stops the test before the filament reaches its limit (common with PLA
> around 20 mm³/s), the value is the highest flow tested, not the filament's real limit.

## Any filament, by hand

Open `http://<host>/autopa/`, load the filament and run a **Sweep**. autopa measures with the
load cell and can remember the value per filament. `SPOOL_FLOW_CALIBRATE SPOOL=<id>` measures
the max flow of a spool in a Box slot.

<details>
<summary>Where the temperature and flow ratio come from</summary>

- **Temperature:** the filament's, in Spoolman. It comes from SpoolmanDB when the tag's
  brand, material and colour match an entry there, else from the tag.
- **Flow ratio:** `orca_filament_flow_ratio` on the filament in Spoolman, else OrcaSlicer's
  Generic preset of the material.

The value is saved as `orca_pressure_advance` on the filament. During a print it is applied
right away only when the print uses that one spool. Spools waiting for a measurement are in
`saved_variables.cfg` (`q2_pa_pending`). The measurement itself is autopa's load cell sweep.

The max flow is saved as `orca_filament_max_volumetric_speed` (the q2_calibration Moonraker
component runs `scripts/flow-test.py`; its report and force data go to
`~/printer_data/logs/flow-test-*`). After it, the pressure advance sweep runs at 80 % of it,
at most 18 mm³/s.

</details>
