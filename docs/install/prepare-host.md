---
title: Prepare the host
description: Get the computer that will run Klipper ready, and find the printer's address.
---

The host is the computer that will run Klipper. Ten minutes, nothing on the printer yet.

1. **Install the system.** Debian 12 or 13, or Ubuntu Server 22.04, 24.04 or 26.04 LTS. A
   minimal install is enough; no desktop needed. Create your normal user with `sudo` rights.

2. **Plug it into the network**, with a cable if you can, on the same network as the printer.

3. **Give both machines a fixed address.** In your router, reserve an IP address for the
   printer and for the host. The printer's board only accepts the host address saved at
   install, so a host that changes address loses the printer until you
   [run the installer again](../help/klipper-does-not-connect.md).

4. **Find the printer's address**: in your router's list of devices, or in the network
   settings on the printer's touchscreen. Write it down, for example `192.168.1.50`.

5. **Install git**, logged in on the host as your normal user:

   ```sh
   sudo apt update && sudo apt install -y git
   ```

6. **Check the host reaches the printer:**

   ```sh
   ping -c 3 192.168.1.50
   ```

   Three replies: you're ready.

Next: [Run the installer](run-installer.md).
