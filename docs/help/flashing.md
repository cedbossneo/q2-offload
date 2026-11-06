---
title: Flashing problems
description: A board that doesn't come back after a flash, what can go wrong, and recent stock firmware.
---

## A board doesn't come back after a flash

1. **On the printer**, list the boards:

   ```sh
   sudo bash ~/q2-offload/q2-printer.sh detect
   ```

2. **Flash again** from the host if a `usb-katapult_*` device is listed (mainboard, Box), and
   for the toolhead in any case:

   ```sh
   cd ~/q2-offload && ./install.sh flash
   ```

   Katapult survives a failed Klipper flash: the board waits in it until it gets a good image.

3. **Nothing shows up after a power cycle?** The bootloader is damaged. This can only happen
   during the first conversion. Recovery needs an ST-Link wired to the board's SWD pads:
   MisterSheikh documents the
   [board pinouts](https://github.com/MisterSheikh/Qidi_Q2_Mainline_Klipper/tree/main/board_pinouts).

## What can go wrong, step by step

| Step | Protection | If it fails |
|---|---|---|
| First conversion: Katapult through Qidi's update scripts | checksums of the pinned images, typed confirmation | a power cut or interrupted write may leave the board unable to start: recovery needs an **ST-Link** |
| Klipper through Katapult (install and updates) | Katapult checks the board type; the installer refuses to write if the application address is not 0x8008000 / 0x8002000 / 0x8004000 | Katapult stays in place: run `./install.sh flash` again |

## Stock firmware 01.01.02 and newer

These versions move `/home/mks` to `/home/qidi` (leaving a link), create a `qidi` account
(password `qiditech`) and remove the sudo rights of `mks`. The new account reportedly has no
sudo, so the installer keeps logging in as `mks`, which users report still works with
`makerbase` and sudo. To use another account, set `PRINTER_USER` in
`~/.config/q2-offload/settings.env`.

They also flash from the screen app, and no longer ship `hid-flash`, the tool that writes
through Qidi's bootloader. The installer then downloads it from Qidi's public 1.1.1 release
(137 MB), checks its checksum and copies it to the printer. A printer updated from 1.1.x
normally keeps its own.

> [!WARNING]
> No conversion from these versions has been tested yet. The installer checks the printer
> before a first conversion and stops, with nothing flashed, if a board or root access is
> missing. If it stops or the conversion fails, please open an
> [issue](https://github.com/cedbossneo/q2-offload/issues) with its output.
