---
title: Where things are
description: The web interfaces and pages on your host, and the touchscreen.
---

Everything is on the host, in a browser. Replace `<host>` with its address.

| What | Address |
|---|---|
| Mainsail, the main interface | `http://<host>/` |
| Fluidd, the other interface | `http://<host>:81/` |
| Box drying | `http://<host>/box/` |
| Failure detection | `http://<host>/detect/` |
| autopa, pressure advance by hand | `http://<host>/autopa/` |
| Spoolman, your spools | `http://<host>:7912/` |

Mainsail's sidebar links to the Box, failure detection, autopa and Spoolman pages.

The **touchscreen** runs HelixScreen, connected to the host: temperatures, prints, the Box
and its drying, and the dialogs q2-offload opens (a new spool's calibration, a failed load).

- **Print options.** Before a print you start from the touchscreen, **Cleaning nozzle** and
  **Auto Bed Mesh** can be turned off for that print. Without a mesh, the print uses the mesh
  in use, else the last print's: fine for a reprint of the same part. When there is none, the
  bed is probed anyway.
- **Preparation.** While `PRINT_START` runs, a checklist shows each step: homing, cleaning,
  heating, Z tilt, bed mesh, loading the filament.
- **After a power cut**, it asks **Resume interrupted print?**: **Resume** runs q2-offload's
  power-loss recovery, **Discard** forgets it. Mainsail's console offers the same choice.
- **Install Helper Macros**, in its Advanced panel, is not needed: q2-offload installs and
  updates them.

<details>
<summary>The camera, and Home Assistant</summary>

The host relays the printer camera at `/webcam/`, so browsers reach it from any address of the
host. In Home Assistant's Moonraker integration, set the camera URLs in its options:
`http://<host>/webcam/?action=stream` and `http://<host>/webcam/?action=snapshot`. A client
that adds Moonraker's port (`:7125`) to them gets a 404.

</details>

<details>
<summary>Mainsail is on port 81 and Fluidd on 80</summary>

Installs made before Mainsail moved to port 80 keep the old order. To switch, set
`MAINSAIL_PORT=80` and `FLUIDD_PORT=81` in `~/.config/q2-offload/settings.env`, then run
`./install.sh host`.

</details>
