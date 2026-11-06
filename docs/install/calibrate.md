---
title: Calibrate
description: The calibrations worth doing once, next to the printer, in this order.
---

The printer already prints with standard Q2 values. These calibrations replace them with your
printer's own. Run them from the console of Mainsail or Fluidd, once Klipper says **ready**,
in this order. You can skip the ones the installer already did (PID, input shaper).

Each `SAVE_CONFIG` writes the result at the bottom of `printer.cfg` and restarts Klipper.

1. **Load cell.** The load cell under the nozzle is the Z probe. If the installer didn't
   measure it:

   ```
   LOAD_CELL_DIAGNOSTIC
   LOAD_CELL_CALIBRATE
   SAVE_CONFIG
   ```

   The first command shows the readings: they must change when you press the nozzle gently.
   The second guides you: tare, then a known weight on the nozzle.

2. **Heaters.**

   ```
   PID_CALIBRATE HEATER=extruder TARGET=250
   SAVE_CONFIG
   PID_CALIBRATE HEATER=heater_bed TARGET=100
   SAVE_CONFIG
   ```

3. **Gantry and bed.**

   ```
   G28
   Z_TILT_ADJUST
   BED_MESH_CALIBRATE
   SAVE_CONFIG
   ```

   Prints then measure only the area of the part, at the start of each print.

4. **Input shaper.** The toolhead's accelerometer measures its vibrations. Bed empty:

   ```
   SHAPER_CALIBRATE
   SAVE_CONFIG
   ```

   Keep `max_accel` in `[printer]` at or below what the result recommends.

5. **The Box** (with a Box). One spool loaded in each gate:

   ```
   MMU_HOME
   MMU_CALIBRATE_BOWDEN
   MMU_CHECK_GATE ALL=1
   ```

   Happy Hare then fine-tunes each gate on its own while printing.
   The [Happy Hare guide](https://github.com/moggieuk/Happy-Hare/wiki) explains more.

Pressure advance is measured per filament, when you add a spool: see
[Pressure advance](../use/pressure-advance.md).

Next: [Set up OrcaSlicer](slicer.md).

<details>
<summary>The standard values it starts from</summary>

| Value | Default | Where |
|---|---|---|
| Hotend, bed, chamber PID | Qidi stock | `printer.cfg` |
| Input shaper | Qidi stock (X 3hump_ei 68.8 Hz, Y mzv 42.2 Hz) | `printer.cfg` |
| Load cell scale | 206.4 counts/g, measured on a Q2 | `printer.cfg` |
| Load cell zero (`reference_tare_counts`) | measured by the installer, nozzle free | `printer.cfg` |
| Box gear rotation distance | 13.8 mm (Qidi factory) | Happy Hare overrides |
| Bowden length | 763.2 mm (stock Box tube) | `saved_variables.cfg` |

`SAVE_CONFIG` comments out the standard value it replaces. A standard value you uncomment
again in `printer.cfg` wins over the calibrated one.

</details>

<details>
<summary>Moving Z before the load cell is calibrated</summary>

`FAKE_HOME_Z` marks Z as homed at mid-travel without probing. Watch the nozzle.

</details>
