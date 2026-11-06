---
title: Updates
description: Update from Mainsail or Fluidd in one click; what happens, and when the boards need flashing.
---

## Update from Mainsail or Fluidd

Open the update manager and update **q2-offload**. It installs the new Klipper, Happy Hare,
autopa, web interfaces and failure detection, then restarts Klipper. Progress shows in the
console.

- **Never during a print.** If one is running, a dialog says how to apply the update afterwards.
- **The boards are never flashed from there**, because flashing needs someone at the
  printer. If the new Klipper needs them flashed, everything else is updated, Klipper stays
  on the version of the boards, and a dialog gives the command to run later.

Your own changes are kept: see [what is yours](#what-is-yours).

## When the boards need flashing

The host and the boards must run the same Klipper. When an update needs them flashed, run
this on the host, next to the printer:

```sh
cd ~/q2-offload && ./install.sh flash
```

It checks each board before writing and asks you to type `FLASH`. Until then, Klipper stays on
the version the boards have.

## Stable or latest

The installer asked which versions to offer:

| Channel | Offers |
|---|---|
| `stable` (default) | versions tested on a printer by the maintainer |
| `latest` | every version that passes the automatic tests |

Change it with `./install.sh host --channel stable` or `--channel latest`.

Every day, the automatic tests move Klipper, Happy Hare, Moonraker, autopa and the web
interfaces to their latest versions, re-apply q2-offload's patches, build the firmware,
install everything on a clean machine and check the configuration. Only a version that passes
is offered.

## What is yours

- Your edits to the installed config files are kept. When q2-offload changes one of them, the
  new version is written next to yours as `*.new`: compare them when you have a moment.
- `printer.cfg` and `moonraker.conf` are yours after the first install: updates don't change
  them. When a version brings something worth adding there, the
  [older installs](../reference/older-installs.md) page says what.
- Settings listed in `config/happy-hare/overrides.cfg` are applied again at every update.

<details>
<summary>Update from a terminal</summary>

```sh
cd ~/q2-offload && ./install.sh update
```

It applies the version checked out in `~/q2-offload` (the one Moonraker installed; `git pull`
first to take the head of `main`). When the Klipper version changes it asks whether to flash
the boards now. Its log is `~/printer_data/logs/q2-offload-update.log`.

</details>

> [!WARNING]
> Klipper, Happy Hare and autopa are not listed on their own in the update manager: they are
> patched, and the firmware must match Klipper. Klipper shows as "dirty" or "invalid" there.
> Never use **Recover** on it.
