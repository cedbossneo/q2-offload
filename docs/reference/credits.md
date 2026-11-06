---
title: Credits and license
description: The work q2-offload builds on, and its license.
---

## Credits

This builds on the work of:

- [MisterSheikh/Qidi_Q2_Mainline_Klipper](https://github.com/MisterSheikh/Qidi_Q2_Mainline_Klipper):
  the Klipper patches for the Q2 boards (GD32F425 USB, CS1237, clocks)
- [n3oney/qidi-q2-klipper](https://github.com/n3oney/qidi-q2-klipper): the Katapult deployers
  that make the conversion possible without an ST-Link (downloaded, pinned by SHA-256)
- [endeavour/Qidi_Q2_Mainline_Klipper](https://github.com/endeavour/Qidi_Q2_Mainline_Klipper)
  and [theboleslaw/Klipper-Offload](https://github.com/theboleslaw/Klipper-Offload): the
  serial-over-network design
- [Happy Hare](https://github.com/moggieuk/Happy-Hare), [Klipper](https://github.com/Klipper3d/klipper),
  [Katapult](https://github.com/Arksine/katapult), [Moonraker](https://github.com/Arksine/moonraker),
  [autopa](https://github.com/G0BL1N/autopa), [HelixScreen](https://github.com/prestonbrown/helixscreen),
  [Spoolman](https://github.com/Donkie/Spoolman), [Obico](https://github.com/TheSpaghettiDetective/obico-server)
  (its failure detector and alert rules), [Apprise](https://github.com/caronc/apprise),
  [Mainsail](https://github.com/mainsail-crew/mainsail), [Fluidd](https://github.com/fluidd-core/fluidd)
- [QIDITECH/QIDI_Q2](https://github.com/QIDITECH/QIDI_Q2): the stock configuration (pins,
  macros, power-loss recovery), and the BunnyBox community port of the stock Box flow

## License

GPL-3.0. autopa (AGPL-3.0) is installed from its own repository. Obico's ML API (AGPL-3.0) is
the image Obico publishes, with its model. On hosts with an Intel GPU, it is q2-offload's build
of the same obico-server commit, model included, published on GHCR. Its source is that commit
plus `detect/ml-api/Containerfile.intel`.
