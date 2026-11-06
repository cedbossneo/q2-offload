---
title: Pressure advance
description: Measured with the load cell once per filament, saved in Spoolman, used by the slicer.
---

Pressure advance makes corners and line starts clean. It depends on the filament, so it is
measured once per filament, with the load cell, and saved in Spoolman.

## New spools from an NFC tag

When a [tag creates a spool](spools.md) whose filament has never been measured, the
touchscreen asks:

- **Calibrate now**: when the printer is not printing;
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

## Any filament, by hand

Open `http://<host>/autopa/`, load the filament and run a **Sweep**. autopa measures with the
load cell and can remember the value per filament.

<details>
<summary>Where the temperature and flow ratio come from</summary>

- **Temperature:** the filament's, in Spoolman. It comes from SpoolmanDB when the tag's
  brand, material and colour match an entry there, else from the tag.
- **Flow ratio:** `orca_filament_flow_ratio` on the filament in Spoolman, else OrcaSlicer's
  Generic preset of the material.

The value is saved as `orca_pressure_advance` on the filament. During a print it is applied
right away only when the print uses that one spool. Spools waiting for a measurement are in
`saved_variables.cfg` (`q2_pa_pending`). The measurement itself is autopa's load cell sweep.

</details>
