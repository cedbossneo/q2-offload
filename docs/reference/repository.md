---
title: The repository
description: What is in the repository, how releases work, and where things live on the host.
---

## What is in here

| Path | |
|---|---|
| `VERSIONS` | every upstream version used, pinned |
| `patches/klipper/` | Q2 support on mainline Klipper: GD32F425 USB fix, 200 MHz mainboard, 120 MHz toolhead, toolhead SPI2, MCU temperature, multi-MCU probing timeout, timing tweaks |
| `patches/happy-hare/` | changes not yet merged in Happy Hare (drying status, spool rotation, the spool-created event, SpoolmanDB for any brand…); each is dropped once upstream has it |
| `firmware/configs/` | Klipper build configs for the three boards |
| `config/klipper/` | Klipper configuration and macros for the Q2 |
| `config/happy-hare/` | Happy Hare menuconfig for the Qidi Box and Q2, and the settings applied on top of it (`overrides.cfg`) |
| `slicer/orca/` | OrcaSlicer presets and the Q2 Spool Presets plugin |
| `host/`, `printer/` | systemd units, nginx, Moonraker config and components, printer board helper |
| `detect/`, `web/` | the failure detection service, the Box drying and failure detection pages |
| `install.sh`, `scripts/` | installer, firmware build, validation, upstream bump |
| `docs/` | this documentation; `site/` builds it with the project page |

## Releases

CI tags every passing version of `main` as a beta, `vYYYY.MM.DD-beta.N`: that is the `latest`
channel. A beta tested on a printer is promoted to `vYYYY.MM.DD`, the `stable` channel:
Actions → **Promote to stable** → Run workflow with its beta tag (empty: the latest beta), or
`gh workflow run promote.yml -f tag=vYYYY.MM.DD-beta.N`.

Every day, `bump.yml` moves Klipper, Happy Hare, Moonraker, autopa and the web clients to their
latest versions, re-applies the patches, builds the firmware, installs the whole stack on a
clean machine and validates the configuration against the new firmware. Only a version that
passes reaches `main`, with its firmware published as a release.

## On the host

- Settings: `~/.config/q2-offload/settings.env` (printer and host addresses, components,
  channel, ports, Box).
- Logs: `~/printer_data/logs/` (`klippy.log`, `q2-link-watch.log`, `q2-offload-update.log`).
- The boards' serial links are ptys in `~/printer_data/comms/q2-{main,thr,mmu}`, used by the
  `[mcu]` sections.
- Klipper and the bridges run at nice -10; failure detection at nice 10, with Obico's ML API
  capped at one CPU with the lowest weight.

## Building the site

```sh
cd site && npm ci && npm run dev
```

The pages are the Markdown files in `docs/`; links between them and GitHub alerts work both on
GitHub and on the site.
