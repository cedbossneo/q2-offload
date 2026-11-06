---
title: What you need
description: The printer, a computer to run Klipper, and the network between them.
---

## The printer

- [ ] A **Qidi Q2**, on Qidi's stock software, connected to your network.
- [ ] Optionally **one Qidi Box**. Without one, see [No Box?](#no-box) below.
- [ ] You can reach it over SSH. On the stock software the user is `mks` and the password
      `makerbase`; you don't need to do anything with it, the installer logs in for you.

> [!WARNING]
> Printers on stock firmware **01.01.02 or newer** haven't been converted yet: they
> change the printer's user accounts and flashing tool. The installer checks the printer and
> stops before flashing anything if something is missing.
> [Details](../help/flashing.md#stock-firmware-010102-and-newer).

## A computer to run Klipper

Any recent mini PC is plenty. A NAS or a Raspberry Pi 4 or 5 works too.

- [ ] **Debian 12 or 13, or Ubuntu 22.04, 24.04 or 26.04 LTS**, on x86_64 or arm64.
- [ ] A user with `sudo` (not root).
- [ ] 2 GB of free disk for failure detection. While printing, it uses about a second of
      one CPU core every 10 seconds.
- [ ] Ideally on a **network cable**, not Wi-Fi: Klipper sends the printer its moves a
      little ahead of time, and a long network stall stops the print.

The automatic tests install the software on each of these systems, on both architectures.

## The network

- [ ] Both machines on the same network.

<details>
<summary>My router separates networks (VLANs)</summary>

The host must reach the printer on TCP ports 7001 to 7003 (the microcontroller links) and 80
(camera), and the printer must reach the host on TCP 7125 (the touchscreen).

</details>

## Optional

- **NFC stickers** (NTAG215) and a phone, if you want the Box to recognise your spools.
  See [Spools and NFC tags](../use/spools.md).
- **OrcaSlicer 2.5 or newer** on your computer. See [Set up OrcaSlicer](../install/slicer.md).

## No Box?

Install with `./install.sh --no-box`. Only the mainboard and toolhead are flashed, Happy Hare
is skipped, and the toolhead filament sensor pauses the print when the filament runs out.
`./install.sh --box` switches back later. The installer checks for a Box before flashing
anything either way.

Next: [Before you start](before-you-start.md).
