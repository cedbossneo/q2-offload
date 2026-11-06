---
title: Start here
description: What q2-offload does, and the four steps from a stock Qidi Q2 to your first print.
---

q2-offload runs **mainline Klipper** for a **Qidi Q2 and its Qidi Box** on a small computer
next to your printer. The printer keeps its touchscreen and camera; the heavy work moves to
the computer, where everything open source about 3D printing can run: Happy Hare for the
Box, Spoolman for your spools, Mainsail and Fluidd, a load cell pressure advance calibration,
and failure detection.

You don't need to know Klipper to install it. One installer does the work and asks before
each step that touches the printer.

## The path

1. **[Check what you need](start/requirements.md)**: the printer, a computer to run Klipper,
   a network cable. Five minutes.
2. **[Read the risks](start/before-you-start.md)**: one step of the conversion needs care.
   Read it once, so you know which one and why.
3. **[Install](install/prepare-host.md)**: prepare the computer, then run the installer. It
   explains each question it asks, and this guide does too.
4. **[Calibrate and print](install/calibrate.md)**: a few calibrations next to the printer,
   then [set up OrcaSlicer](install/slicer.md) and print.

After that, [Using it](use/web-interfaces.md) covers the day to day: spools and NFC tags,
drying, failure detection and updates.

## How it works

The Q2's own board is too small for current Klipper with everything around it. q2-offload
leaves it the jobs it is good at: it forwards the links of the three microcontrollers
(mainboard, toolhead, Box) over the network, and runs the touchscreen and the camera.

```
 Your Klipper host (x86_64 or arm64)           Qidi Q2 printer board
 ┌──────────────────────────────┐   network     ┌──────────────────────────────┐
 │ Klipper ─────────────────────┼── 7001 ──────►│ mainboard (USB)              │
 │                              ┼── 7002 ──────►│ toolhead (UART)              │
 │                              ┼── 7003 ──────►│ Qidi Box (USB)               │
 │ Moonraker, Happy Hare        │               │ HelixScreen ──► host:7125    │
 │ Mainsail, Fluidd, autopa     │               │ camera (/webcam/)            │
 │ Spoolman, failure detection  │               └──────────────────────────────┘
 └──────────────────────────────┘
```

Want the tour first? The [project page](https://cedbossneo.github.io/q2-offload/) shows a
spool going from the bag to the first layer.

> [!NOTE]
> Stuck, or something isn't clear? Open an [issue on GitHub](https://github.com/cedbossneo/q2-offload/issues)
> with what you ran and what it printed.
