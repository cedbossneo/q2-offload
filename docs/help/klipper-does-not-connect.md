---
title: Klipper does not connect
description: What reconnects Klipper on its own, and what to check when it doesn't.
---

**Usually, wait a minute.** When the printer was switched on after the host, the host
restarted, or the network dropped, `q2-link-watch` brings Klipper back on its own: once the
printer answers on the network, it restarts the links and Klipper, then the printer's side a
minute later if needed, then tries again every 10 minutes.

It never touches a heater or other fault: those need you to read the message. If the link was
lost during a print, that print has stopped; use power-loss recovery to resume it.

## If it doesn't come back

1. **See what runs on both sides:**

   ```sh
   cd ~/q2-offload && ./install.sh status
   ```

2. **Read what the watchdog saw** before each restart (connections, printer devices, kernel
   messages): `~/printer_data/logs/q2-link-watch.log`.

3. **Did the host's address change?** The printer only accepts the host address saved at
   install. Run `./install.sh printer` to save the new one.

4. **Check the links.** On the host, `journalctl -u 'q2-serial-bridge@*'` (they reconnect every
   second) and `~/printer_data/logs/klippy.log`. On the printer,
   `systemctl status 'q2-serial-proxy@*'`.

Still stuck? Open an [issue](https://github.com/cedbossneo/q2-offload/issues) with the output
of `./install.sh status` and the end of `q2-link-watch.log`.

## "Timer too close" during a print

Klipper sends the printer its moves a little ahead of time, and a network or host stall of a
few hundred milliseconds stops the print with this message. Use a network cable, keep the host
lightly loaded, and don't put the host on Wi-Fi.
