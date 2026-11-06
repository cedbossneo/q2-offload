---
title: Good to know
description: Limits that come from running the printer over the network.
---

- **Use a wired network.** Klipper schedules the printer's moves a little ahead of time; a
  long network stall stops the print with "Timer too close". Klipper and the links run at a
  higher priority on the host, and failure detection at a lower one, so a busy host is rarely
  the cause, but Wi-Fi often is.
- **Box LEDs are static**, as on the stock firmware: animations send many small commands,
  and made the Box board shut down over the network.
- **Power-loss recovery** saves the print state as it goes, so a print stopped by a power cut
  can resume. A print stopped by a lost link is not resumed automatically.
- **Print through the printer**, not from a USB stick: Happy Hare reads the file's colours and
  tool changes when it is uploaded.
- **The filament type matters** in your slicer presets (`PLA`, `PETG`, `ABS`, `TPU`, `PA-CF`…):
  the Box heating, drying and TPU handling use it, and an unknown type doesn't heat the Box.
