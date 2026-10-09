# Calibration after the install

The configuration ships with stock Qidi values. These steps adapt it to your machine; run
them from Mainsail/Fluidd once Klipper reports **ready**, in this order. Each `SAVE_CONFIG`
writes the result at the bottom of `printer.cfg` and restarts Klipper.

## 1. Load cell (Z probe)

The Q2 probes with a CS1237 load cell under the nozzle. It needs its scale once:

```
LOAD_CELL_DIAGNOSTIC          ; readings must change when you press the nozzle gently
LOAD_CELL_CALIBRATE           ; follow the prompts (tare, then a known weight)
SAVE_CONFIG
```

`FAKE_HOME_Z` marks Z as homed at mid-travel without probing, if you need to jog Z before
the probe is calibrated (watch the nozzle).

## 2. Heaters

```
PID_CALIBRATE HEATER=extruder TARGET=250
SAVE_CONFIG
PID_CALIBRATE HEATER=heater_bed TARGET=100
SAVE_CONFIG
```

## 3. Gantry and bed

```
G28
Z_TILT_ADJUST
BED_MESH_CALIBRATE
SAVE_CONFIG
```

Prints use an adaptive mesh (`ADAPTIVE=1`) from `PRINT_START`.

## 4. Input shaper

The toolhead has an LIS2DW accelerometer:

```
SHAPER_CALIBRATE
SAVE_CONFIG
```

Keep `max_accel` in `[printer]` at or below what the recommendation allows for your shapers.

## 5. Pressure advance (autopa)

Open `http://<host>/autopa/`, load the filament, run a **Sweep**. autopa measures with the
load cell and can remember the value per filament.

## 6. Qidi Box (Happy Hare)

With one spool loaded in each gate:

```
MMU_HOME
MMU_CALIBRATE_BOWDEN
MMU_CHECK_GATE ALL=1
```

Happy Hare then tunes the gear rotation distance of each gate while printing (sync
feedback autotune). See the [Happy Hare calibration guide](https://github.com/moggieuk/Happy-Hare/wiki)
for details.

NFC: write your spool tags in the OpenSpool format ([docs/spoolman-nfc.md](spoolman-nfc.md)).

## 7. Box drying

Each material has two Box temperatures, with the same materials in both tables:

- **drying** (`drying_data` in `config/happy-hare/overrides.cfg`): used by `MMU_HEATER DRY=1`
  and by `MMU_KEEP_DRY`, which restarts a drying cycle when the Box humidity goes above 35 %
  (`MMU_KEEP_DRY TRIGGER=40 TARGET=25` to change, `MMU_KEEP_DRY ENABLE=0` to stop);
- **printing** (`print_temps` in `_BOX_PRINT_HEAT`, `mmu_keep_dry.cfg`): the stock Qidi
  values. `PRINT_START` heats the Box to it (PLA, PC and TPU 0 = off;
  PETG and ASA 45 °C, ABS 55 °C, PA/PAHT/PPS/PET-CF 65 °C).
  `DISABLE_BOX_HEATER` (slicer end G-code, `PRINT_END`, cancel) turns it off but lets a
  running drying cycle finish. `SET_GCODE_VARIABLE MACRO=_BOX_PRINT_HEAT VARIABLE=enable
  VALUE=False` disables it.

In both cases the lowest temperature of the loaded materials wins, so a PLA spool next to a
PETG one never softens, and the Box never goes above 65 °C (`heater_max_temp`). Spool
adapters printed in PETG soften above about 60 °C: print them in ABS, ASA or PC if you dry
ASA/ABS or print PA-type filaments.
