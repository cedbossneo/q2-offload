# Risks, recovery and going back to stock

## What can go wrong when flashing

| Step | Protection | If it fails |
|---|---|---|
| First conversion: Katapult deployer via Qidi's update scripts | SHA-256 of the pinned deployers, typed confirmation | Power cut or interrupted write: the MCU may not boot. Recovery needs an **ST-Link**. |
| Klipper firmware via Katapult (install and updates) | Katapult checks the MCU type; `q2-printer.sh` refuses to write if the application offset is not 0x8008000 / 0x8002000 / 0x8004000 | Katapult stays in place: re-run `./install.sh flash`. |

Katapult survives a failed Klipper flash: the MCU stays in the bootloader and you can flash
again. Only the first step, which replaces Qidi's bootloader, needs care.

## An MCU does not come back after a flash

1. On the printer: `sudo bash ~/q2-offload/q2-printer.sh detect`.
2. If a `usb-katapult_*` device (mainboard, Box) is listed, or for the toolhead always,
   flash again: `./install.sh flash` on the host.
3. If nothing shows up after a power cycle, the bootloader is damaged: you need an ST-Link
   and the SWD pads of the board. MisterSheikh documents the board pinouts:
   [board_pinouts](https://github.com/MisterSheikh/Qidi_Q2_Mainline_Klipper/tree/main/board_pinouts).

## Klipper does not connect

- `./install.sh status` shows the services on both sides.
- Host: `journalctl -u 'q2-serial-bridge@*'` (the bridges reconnect every second),
  `~/printer_data/logs/klippy.log`.
- Printer: `systemctl status 'q2-serial-proxy@*'`. Each proxy only accepts the host IP saved
  at install; if the host IP changed, run `./install.sh printer`.
- "Timer too close" during prints: a network or host stall of a few hundred ms. Use a wired
  link and check the host load.

## Going back to stock

Qidi's bootloader is replaced by Katapult during the first conversion, and Qidi's stock
images are linked for that bootloader, so **a full return to stock needs an ST-Link**
(flash Qidi's bootloader and firmware back).

The printer board itself is not modified beyond configuration: `sudo bash
~/q2-offload/q2-printer.sh stock-start` re-enables Qidi's Klipper, Moonraker and touchscreen
UI, and the config backup made before the conversion is in `~/q2-offload/backup-*.tgz` on
the printer.
