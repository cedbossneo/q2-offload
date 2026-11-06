---
title: Run the installer
description: The commands to run, and what each question of the installer means.
---

On the host, as your normal user (not root), with the printer's address:

```sh
git clone https://github.com/cedbossneo/q2-offload.git ~/q2-offload
cd ~/q2-offload
git checkout "$(git tag -l 'v*' --sort=-creatordate | grep -v -- -beta | head -1)"
./install.sh --printer 192.168.1.50
```

The `git checkout` line picks the latest **stable** version, the one tested on a printer.

Stay next to the printer: the installer asks you things on the way, and some steps need
you there. Here is each question, in order.

## On the host

1. **Components to install.** A menu of the optional parts, all selected: Mainsail, Fluidd,
   Spoolman, autopa and failure detection. Press **Enter** to keep them all, or type numbers
   to untick some. Klipper, Moonraker and (with a Box) Happy Hare are always installed.

2. **Updates offered in Mainsail/Fluidd.** Choose **1, stable** (versions tested on a
   printer). **2, latest** offers every version that passes the automatic tests.
   [More on updates](../use/updates.md).

3. **This will: … Continue?** A summary of what comes next. Answer `y`.

4. **The printer's password.** The installer connects to the printer over SSH and may ask for
   its password once: on stock software, `makerbase`.

5. **No Box found?** If it doesn't find a Qidi Box, it asks whether to install without one.
   Answer `n` if you have a Box, and check its cable.

Then it installs Klipper, Moonraker, Happy Hare and the components on the host, without
questions: the longest part. It also makes a backup of the printer's configuration.

## On the printer

6. **Is this the first conversion from Qidi's stock firmware?** `y` on a printer that still
   runs Qidi's firmware. It checks the printer first and stops, with nothing flashed, if
   something is missing.

7. **Type `INSTALL KATAPULT`.** The [step that needs care](../start/before-you-start.md):
   Katapult replaces Qidi's bootloader on each microcontroller, one at a time. Keep the
   printer powered.

8. **Type `FLASH`.** Klipper is written on the mainboard, the toolhead and the Box, after
   checking each one.

9. **Install HelixScreen on the touchscreen?** `y`. Qidi's screen app needs Klipper on the
   printer, so it is replaced by HelixScreen, connected to the host. Its own installer may
   ask for the printer password again.

## First checks

10. **Load cell.** The load cell under the nozzle is what finds the bed. If it hasn't been
    measured yet, the installer offers to do it now. Then it asks you to **push the nozzle up
    gently with a finger**, a few times: the printer is only homed if it sees those taps.

11. **PID and input shaper.** It offers to measure the heaters (about 10 minutes) and the
    vibrations of the toolhead (about 5 minutes, **bed empty**). Say yes: your printer's own
    values are better than the standard ones.

At the end it prints the addresses of the web interfaces. Open `http://<host>/` in a
browser: Mainsail shows the printer, **ready**.

Next: [Calibrate](calibrate.md).

<details>
<summary>Installer options</summary>

| Option | What it does |
|---|---|
| `--printer <ip>` | the printer's address (asked if missing) |
| `--components mainsail,fluidd,spoolman,autopa,detect` | skips the menu and installs these |
| `--channel stable` or `latest` | skips the update channel question |
| `--no-box`, `--box` | install without a Box, or switch back to one |

Without the `git checkout` line you install the head of `main`, the `latest` channel.

Other commands, once installed: `./install.sh status` (services on both sides),
`./install.sh check` (checks the install), `./install.sh update`, `./install.sh flash`,
`./install.sh host` (host part only), `./install.sh printer` (printer part only).

</details>

<details>
<summary>What it changes on the printer</summary>

- Qidi's bootloader is replaced by Katapult, and Qidi's firmware by Klipper, on the three
  microcontrollers.
- The printer's board stops its own Klipper, Moonraker and screen app, and forwards the
  microcontroller links to the host instead. Its configuration is backed up first, in
  `~/q2-offload/backup-*.tgz` on the printer.
- HelixScreen is installed on the touchscreen.
- A sudo rule lets the `mks` user run `q2-offload/q2-printer.sh` (and nothing else) as root
  without a password, so the host can drive it. `mks` already has full sudo with the stock
  password, so this grants nothing new.

</details>
