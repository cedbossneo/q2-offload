---
title: Drying filament
description: Drying cycles in the Box, keep-dry, and the Box heating during prints.
---

The **Box drying** page, `http://<host>/box/` (linked in Mainsail's sidebar), shows the
humidity, the Box temperature and the loaded spools. From there:

- **Start a cycle.** Leave the fields empty: the temperature and time come from the loaded
  materials (PLA 45 °C, PETG 60 °C, ABS 70 °C… for 5 to 10 hours). The time left shows
  while it runs.
- **Stop it.**
- **Set keep-dry**, or turn it off. Keep-dry starts a new cycle when the humidity goes above
  35 %.

> [!IMPORTANT]
> The lowest temperature of the loaded spools wins, so a PLA spool next to a PETG one never
> softens. The Box never goes above 90 °C, like the stock firmware.
>
> Spool holders and adapters printed in PETG soften above about 60 °C, and cardboard spools
> need a holder: print them in ABS, ASA or PC before drying ASA or ABS, or printing PA-type
> filaments.

## Two ways to dry

- **Spools loaded**: start a cycle with the filament in place, parked 80 mm before the hub.
  With **Turn the spools**, every 5 minutes each spool turns a little so it heats evenly: its
  filament moves back up to 30 cm, then returns, never toward the hub. Not while printing,
  and never the spool loaded in the toolhead. At the end each filament is back at its park; if
  the cycle is cut short (a print, a restart) it may stay a little behind, which the next load
  makes up for.
- **Spools out**, for a deeper dry (*Spools out* mode on the page): eject the filaments first
  and secure each end to its spool. Every 5 minutes each empty gate turns its spool a little,
  so it heats evenly, as in the stock firmware. Gates that still hold filament never move.
  Reload the spools afterwards: the NFC tags restore them.

## While printing

Like the stock firmware, the Box warms up for some materials during a print: PETG and ASA
45 °C, ABS 55 °C, PA, PAHT, PPS and PET-CF 65 °C; off for PLA, PC and TPU. It is turned off at
the end of the print, but a drying cycle that was running finishes.

<details>
<summary>Commands and settings</summary>

- Drying: `MMU_HEATER DRY=1`, turning the loaded spools `MMU_HEATER DRY=1 ROTATE=1`, with the spools out `MMU_HEATER DRY=1 ROTATE=1 GATES=0,1,2,3`
  (eject first with `MMU_EJECT GATE=n`). Temperatures and times: `drying_data` in
  `config/happy-hare/overrides.cfg`.
- Keep-dry: `MMU_KEEP_DRY TRIGGER=40 TARGET=25` changes the thresholds, `MMU_KEEP_DRY
  ENABLE=0` stops it. Thresholds set from the page last until Klipper restarts; edit
  `mmu_keep_dry.cfg` to change the defaults.
- Print heating: `print_temps` in `_BOX_PRINT_HEAT` (`mmu_keep_dry.cfg`). `DISABLE_BOX_HEATER`
  turns it off (end G-code, `PRINT_END`, cancel). `SET_GCODE_VARIABLE MACRO=_BOX_PRINT_HEAT
  VARIABLE=enable VALUE=False` disables it.
- Rotation with the spools out: each empty gate retracts 50 mm at 80 mm/s every 5 minutes
  (`heater_rotate_*` in `overrides.cfg`). With the spools loaded: 50 mm steps between the park
  and `heater_rotate_loaded_travel` (300 mm) behind it, Happy Hare patch 0008. The positions
  are saved (`mmu_state_drying_sweep`) until Happy Hare homes the gate again.
- The heater runs at full power and regulates on the air sensor, like the stock firmware, so
  its elements run much hotter than the air while it warms up (above 90 °C, then about 60 °C).
  As in stock, only their Klipper `max_temp` (130 °C) watches them.
- The time left comes from `printer.mmu.drying` (Happy Hare #1507).

</details>
