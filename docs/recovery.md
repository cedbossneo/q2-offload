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

**No ST-Link is needed to put Qidi's firmware back.** Qidi links its three MCU images to
start at 0x8008000 and they keep Katapult's bootloader-request support, so they can be
flashed through Katapult like our Klipper images. Katapult stays installed, so the
printer can be converted again later without a deployer.

| MCU | Qidi image | Katapult application start | Flash |
|---|---|---|---|
| Mainboard | `QD_Q2_MCU` | 0x8008000 (same as Qidi) | as is |
| Toolhead | `QD_Q2_THR` | 0x8002000 | after moving the image to 0x8008000 (padding) |
| Qidi Box | `mcu_box_to_v2_1.1.3.bin` | 0x8004000 | after moving the image to 0x8008000 (padding) |

Where to get the images: the printer board keeps them (`~/bck_firmware/QD_Q2_MCU`,
`~/bck_firmware/QD_Q2_THR`, `~/mcu_box_to_v2_1.1.3.bin`), and Qidi publishes them in the
`Q2_V1.1.1` release of [QIDITECH/QIDI_Q2](https://github.com/QIDITECH/QIDI_Q2/releases).

Status: this is checked against the images (vector tables, link address), **not yet on
hardware**, and `./install.sh` has no `uninstall` command yet: it will build the padded
toolhead and Box images, check each image's MCU type and offset before writing, and
restore the printer board services. Until then, ask in the issues before trying it.

What stays changed:

- Qidi's own bootloader is replaced by Katapult, so Qidi's firmware updates (their
  update scripts look for Qidi's bootloader) will not work. Putting Qidi's bootloader back
  needs an ST-Link, or a "reverse deployer" for the mainboard and toolhead (bootloader dumps
  exist in [MisterSheikh/Qidi_Q2_Mainline_Klipper](https://github.com/MisterSheikh/Qidi_Q2_Mainline_Klipper),
  none for the Box); not provided.
- The printer board itself is not modified beyond configuration: `sudo bash
  ~/q2-offload/q2-printer.sh stock-start` re-enables Qidi's Klipper, Moonraker and
  touchscreen UI, and the config backup made before the conversion is in
  `~/q2-offload/backup-*.tgz` on the printer.
