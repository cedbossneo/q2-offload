---
title: Going back to stock
description: Putting Qidi's firmware back through Katapult, without an ST-Link. Not automated yet.
---

> [!WARNING]
> This is checked against Qidi's images, **not yet on a printer**, and the installer has no
> `uninstall` command yet. Until it does, ask in the
> [issues](https://github.com/cedbossneo/q2-offload/issues) before trying it.

**No ST-Link is needed to put Qidi's firmware back.** Qidi's three images start at 0x8008000 and
answer Katapult's request to enter the bootloader, so they can be flashed through Katapult like
q2-offload's Klipper. Katapult stays installed, so the printer can be converted again later.

| Board | Qidi image | Katapult application start | Flash |
|---|---|---|---|
| Mainboard | `QD_Q2_MCU` | 0x8008000 (same as Qidi) | as is |
| Toolhead | `QD_Q2_THR` | 0x8002000 | after moving the image to 0x8008000 (padding) |
| Qidi Box | `mcu_box_to_v2_1.1.3.bin` | 0x8004000 | after moving the image to 0x8008000 (padding) |

The printer's board keeps the images (`~/bck_firmware/QD_Q2_MCU`, `~/bck_firmware/QD_Q2_THR`,
`~/mcu_box_to_v2_1.1.3.bin`), and Qidi publishes them in the `Q2_V1.1.1` release of
[QIDITECH/QIDI_Q2](https://github.com/QIDITECH/QIDI_Q2/releases). The coming `uninstall`
command will build the padded images, check each one before writing, and restore the
printer's own services.

## What stays changed

- **Qidi's bootloader is replaced by Katapult**, so Qidi's own firmware updates (which look
  for Qidi's bootloader) won't work. Putting Qidi's bootloader back needs an ST-Link, or a
  "reverse deployer" for the mainboard and toolhead (bootloader dumps exist in
  [MisterSheikh/Qidi_Q2_Mainline_Klipper](https://github.com/MisterSheikh/Qidi_Q2_Mainline_Klipper),
  none for the Box); not provided.
- **The printer's board is only reconfigured.** `sudo bash ~/q2-offload/q2-printer.sh
  stock-start` starts Qidi's Klipper, Moonraker and screen app again, and the configuration
  backup made before the conversion is in `~/q2-offload/backup-*.tgz` on the printer.
