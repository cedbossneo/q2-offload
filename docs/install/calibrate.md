---
title: Calibrate
description: The calibrations worth doing once, next to the printer, in this order.
---

The printer already prints with standard Q2 values. These calibrations replace them with your
printer's own. Run them from the console of Mainsail or Fluidd, once Klipper says **ready**,
in this order. Skip the ones the installer already did (PID, input shaper).

Each `SAVE_CONFIG` writes the result at the bottom of `printer.cfg` and restarts Klipper.

> [!NOTE]
> **The load cell needs no calibration**, as on the stock firmware: every Q2 has the same
> sensor, so the standard values fit all of them. The installer only checks it reacts, with
> three taps on the nozzle. If you skipped that check, run `./install.sh calibrate`.

1. **Heaters.**

   ```
   PID_CALIBRATE HEATER=extruder TARGET=250
   SAVE_CONFIG
   PID_CALIBRATE HEATER=heater_bed TARGET=100
   SAVE_CONFIG
   ```

2. **Gantry and bed.**

   ```
   G28
   Z_TILT_ADJUST
   BED_MESH_CALIBRATE
   SAVE_CONFIG
   ```

   Prints then measure only the area of the part, at the start of each print.

3. **Input shaper.** The toolhead's accelerometer measures its vibrations. Bed empty:

   ```
   SHAPER_CALIBRATE
   SAVE_CONFIG
   ```

   Keep `max_accel` in `[printer]` at or below what the result recommends.

4. **The Box** (with a Box). One spool loaded in each gate:

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
| Load cell scale and zero | 206.4 counts/g and -712492, measured on a Q2 | `printer.cfg` |
| Box gear rotation distance | 13.8 mm (Qidi factory) | Happy Hare overrides |
| Bowden length | 763.2 mm (stock Box tube) | `saved_variables.cfg` |

`SAVE_CONFIG` comments out the standard value it replaces. A standard value you uncomment
again in `printer.cfg` wins over the calibrated one.

</details>

<details>
<summary>The load cell, in detail</summary>

Klipper uses two values in `[load_cell_probe]`:

- `counts_per_gram`, the scale: it depends on the sensor, its gain and the load cell, the
  same on every Q2.
- `reference_tare_counts`, the reading at rest.

q2-offload ships both, measured on a Q2. The probe triggers at 75 g measured from a tare taken
just before each probe, so the zero doesn't change when it stops. The zero only centres the
2000 g safety limit, a backup in case the probe never triggers: on a printer whose zero
differs from ours, that limit moves by as much, and a printer far from it refuses to probe.

What matters is that your load cell reacts. Before the first homing, the installer asks you to
push the nozzle up three times: each tap must read above 150 g, and the reading must come back
to rest. A dead, inverted or stuck load cell fails the check, and nothing homes until it passes.

To measure your own values anyway (optional), with a known weight:

```
LOAD_CELL_DIAGNOSTIC
LOAD_CELL_CALIBRATE
SAVE_CONFIG
```

The first command shows the readings: they must change when you press the nozzle gently.
The second guides you: tare, then the weight on the nozzle. `FAKE_HOME_Z` marks Z as homed at
mid-travel without probing, if you need to move Z first; watch the nozzle.

</details>
