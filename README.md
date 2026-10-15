# q2-offload

Run **mainline Klipper** for a **Qidi Q2 + Qidi Box** on another Linux machine (a mini PC,
a NAS, a Raspberry Pi 4/5…). The printer's own board keeps only the jobs it is good at:
it forwards the three MCU serial links over the network, runs the touchscreen
(HelixScreen) and the camera.

```
 Klipper host (x86_64 / arm64)                 Qidi Q2 printer board
 ┌──────────────────────────────┐   TCP         ┌──────────────────────────────┐
 │ Klipper ── pty ── socat ─────┼── 7001 ──────►│ socat ── USB  ── mainboard   │
 │                   socat ─────┼── 7002 ──────►│ socat ── UART ── toolhead    │
 │                   socat ─────┼── 7003 ──────►│ socat ── USB  ── Qidi Box    │
 │ Moonraker, Happy Hare        │               │ HelixScreen ──► host:7125    │
 │ Mainsail, Fluidd, autopa     │               │ webcam (/webcam/)            │
 │ Spoolman, PrintGuard         │               └──────────────────────────────┘
 └──────────────────────────────┘
```

Everything is configured: the Klipper configuration for the Q2 (load cell probing, 200 MHz
mainboard, 120 MHz toolhead), Happy Hare for the Qidi Box (NFC tags → Spoolman, drying
with a keep-dry watchdog and spool rotation), purge bucket and chute macros, power-loss
recovery, and the web UIs.

> [!CAUTION]
> This replaces Qidi's firmware on three microcontrollers. The **first** conversion
> replaces Qidi's bootloader with Katapult: a power cut during that step, or a wrong
> image, can only be recovered with an ST-Link. Going back to Qidi's firmware does not
> need one: Qidi's MCU images can be flashed back through Katapult (not automated yet).
> Read [docs/recovery.md](docs/recovery.md) before starting. No warranty
> (GPL-3.0); you do this at your own risk.

## What you need

- A Qidi Q2 with a Qidi Box (one unit), on the stock Qidi OS, reachable over SSH
  (`mks` / `makerbase`).
- A Klipper host running **Debian 12 or Ubuntu 22.04+** (x86_64 or arm64), on a wired
  link to the printer if possible. Any recent mini PC is plenty; PrintGuard alone
  uses about one CPU core.
- Both machines on the same LAN. If your router filters between VLANs, the host must
  reach the printer on TCP 7001–7003 and 80 (camera), and the printer must reach the
  host on TCP 7125 (touchscreen).

## Install

On the Klipper host, as your normal user:

```sh
git clone https://github.com/cedbossneo/q2-offload.git ~/q2-offload
cd ~/q2-offload
git checkout "$(git tag -l 'v*' --sort=-creatordate | grep -v -- -beta | head -1)"  # latest stable
./install.sh --printer 192.168.1.50
```

Skip the `git checkout` line to install the head of `main` instead (the `latest` channel,
see [Updates](#updates)).

It first shows a menu of the optional components (Mainsail, Fluidd, Spoolman, autopa,
PrintGuard; all selected by default, `--components` skips it). The installer asks before
each step that touches the printer, and makes a backup of the printer config first. It:

1. installs Klipper, Moonraker, Happy Hare and the components on the host
   (`--components mainsail,fluidd,spoolman,autopa,printguard`, all by default);
2. on a stock printer, installs Katapult on the three MCUs with Qidi's own update
   scripts (no ST-Link needed), then flashes Klipper, checking the Katapult application
   offset of each MCU before writing;
3. turns the printer board into a serial proxy and stops its stock Klipper, Moonraker
   and touchscreen UI;
4. installs HelixScreen on the touchscreen and points it at the host.

Then calibrate the machine: [docs/calibration.md](docs/calibration.md).
Slicer: OrcaSlicer presets for the Q2 + Box are in `slicer/orca/`, see
[docs/orca-slicer.md](docs/orca-slicer.md).

| Service | URL |
|---|---|
| Fluidd | `http://<host>/` |
| Mainsail | `http://<host>:81/` (sidebar links to the Box page, autopa, PrintGuard, Spoolman) |
| Box drying | `http://<host>/box/` (humidity, drying cycle, keep-dry settings) |
| autopa | `http://<host>/autopa/` |
| Spoolman | `http://<host>:7912/` |
| PrintGuard | `http://<host>:8000/` |

## Updates

Upstream projects are tracked automatically: every day CI moves Klipper, Happy Hare,
Moonraker, autopa and the web clients to their latest versions, re-applies the patches,
builds the firmware, installs the whole stack on a clean machine and validates the
configuration against the new firmware. Only a version that passes reaches `main`, with
its firmware published as a release.

**From Mainsail or Fluidd:** update **q2-offload** in the update manager. Moonraker pulls
the repo, then starts `q2-offload.service`, which installs the new Klipper, Happy Hare,
autopa, web clients and containers and restarts Klipper. Progress and errors appear in the
console and in `logs/q2-offload-update.log`.

- Nothing is applied during a print: a dialog says how to apply the update afterwards.
- The MCUs are never flashed from there (flashing needs someone at the printer). If the
  new Klipper needs them reflashed, everything else is updated, Klipper stays at the
  version of the flashed firmware, and a dialog gives the command for later:
  `./install.sh flash`.

**Update channels.** The installer asks which versions Moonraker offers (change it later
with `./install.sh host --channel stable|latest`):

| Channel | Offers | Tags |
|---|---|---|
| `stable` (default) | versions tested on a printer and promoted by the maintainer | `vYYYY.MM.DD` |
| `latest` | every version of `main` that passes CI (Moonraker's `beta` channel) | `vYYYY.MM.DD-beta.N` |

CI tags every passing version of `main` as a beta. To promote one that was tested on a
printer: Actions → **Promote to stable** → Run workflow, with its beta tag (empty: the
latest beta), or `gh workflow run promote.yml -f tag=vYYYY.MM.DD-beta.N`.

**From a terminal:**

```sh
cd ~/q2-offload && ./install.sh update
```

It applies the version checked out in `~/q2-offload` (the one Moonraker installed; `git
pull` first to take the head of `main`). When the Klipper version changes it asks whether
to reflash the three MCUs now (through Katapult, offsets and image MCU type checked, typed
confirmation), because the host and the MCUs must run the same Klipper; without a flash,
Klipper is kept until `./install.sh flash`. Your edits to the installed config files are
kept: a changed upstream version is written next to them as `*.new`. `printer.cfg` and
`moonraker.conf` are yours after the first install; settings listed in
`config/happy-hare/overrides.cfg` are re-applied on every update.

Klipper, Happy Hare and autopa are not listed separately in the update manager (they are
patched, and the firmware must match Klipper). Klipper shows as "dirty/invalid" there:
never use "Recover" on it.

The printer board gets a sudo rule that lets its `mks` user run `q2-offload/q2-printer.sh`
(and nothing else) as root without a password, so the host can drive it non-interactively.
`mks` already has full sudo with the stock password, so this grants nothing new.

## What is in here

| Path | |
|---|---|
| `VERSIONS` | every upstream version used, pinned |
| `patches/klipper/` | Q2 support on mainline Klipper: GD32F425 USB fix, 200 MHz mainboard, 120 MHz toolhead, toolhead SPI2, MCU temperature, multi-MCU probing timeout, timing tweaks |
| `patches/happy-hare/` | changes not yet merged upstream ([#1368](https://github.com/moggieuk/Happy-Hare/pull/1368), [#1370](https://github.com/moggieuk/Happy-Hare/pull/1370), drying cycle in the status for the Box page); dropped automatically once upstream |
| `firmware/configs/` | Klipper build configs for the three MCUs |
| `config/klipper/` | Klipper configuration and macros for the Q2 |
| `slicer/orca/` | OrcaSlicer printer, process and filament presets ([docs/orca-slicer.md](docs/orca-slicer.md)) |
| `config/happy-hare/` | Happy Hare menuconfig for Qidi Box + Q2, and the settings applied on top of it |
| `host/`, `printer/` | systemd units, nginx, Moonraker config, printer board helper |
| `install.sh`, `scripts/` | installer, firmware build, validation, upstream bump |

## Good to know

- **Network stalls.** Klipper schedules MCU commands a little ahead of time; a long
  network stall shuts the printer down with "Timer too close". Use a wired link, keep
  the host lightly loaded (Klipper and the bridges run at nice -10, PrintGuard is capped
  at one CPU with the lowest weight), and do not put the host on Wi-Fi.
- **Box LEDs are static** like stock: animations send many small commands and made the
  Box MCU shut down over the network.
- `[mcu]` serial devices are ptys in `~/printer_data/comms/q2-{main,thr,mmu}`.

## Credits

This builds on the work of:

- [MisterSheikh/Qidi_Q2_Mainline_Klipper](https://github.com/MisterSheikh/Qidi_Q2_Mainline_Klipper)
  — the Klipper patches for the Q2 MCUs (GD32F425 USB, CS1237, clocks)
- [n3oney/qidi-q2-klipper](https://github.com/n3oney/qidi-q2-klipper) — the Katapult
  deployers that make the no-ST-Link conversion possible (downloaded, pinned by SHA-256)
- [endeavour/Qidi_Q2_Mainline_Klipper](https://github.com/endeavour/Qidi_Q2_Mainline_Klipper)
  and [theboleslaw/Klipper-Offload](https://github.com/theboleslaw/Klipper-Offload) — the
  socat serial-over-network design
- [Happy Hare](https://github.com/moggieuk/Happy-Hare), [Klipper](https://github.com/Klipper3d/klipper),
  [Katapult](https://github.com/Arksine/katapult), [Moonraker](https://github.com/Arksine/moonraker),
  [autopa](https://github.com/G0BL1N/autopa), [HelixScreen](https://github.com/prestonbrown/helixscreen),
  [Spoolman](https://github.com/Donkie/Spoolman), [PrintGuard](https://github.com/oliverbravery/printguard),
  [Mainsail](https://github.com/mainsail-crew/mainsail), [Fluidd](https://github.com/fluidd-core/fluidd)
- [QIDITECH/QIDI_Q2](https://github.com/QIDITECH/QIDI_Q2) — stock configuration (pins,
  macros, power-loss recovery), and the BunnyBox community port of the stock Box flow

## License

GPL-3.0. autopa (AGPL-3.0) and PrintGuard (GPL-2.0) are installed from their own
repositories, not redistributed here.
