---
title: Direct Connect Guide 
description: Guide for wiring the host directly to the Q2 with a single Ethernet cable.
---

This serves as a reference guide for setting up a direct connection from the host to the Qidi Q2 without the use of a router.
This was tested and implemented on a Debian 13 (Trixie) x86-64 machine.

## Step 0. Plugging it in

Connect the LAN port of the Q2 directly to an Ethernet port on the host. If Ethernet is your only network connection and you only have one Ethernet port, or you don't have an Ethernet port to begin with, a USB dongle that works under Linux will suffice.

The author has used a Cable Matters USB-A to Ethernet adapter for their setup.


## Step 1. Install

Run `sudo apt install network-manager dnsmasq-base`, then `sudo systemctl disable --now dnsmasq`.

## Step 2. Finding the network port

Run `ip -br link` to find the name of the Ethernet interface. This guide will use `eth0` as the name- replace that with your actual interface.

Then run `grep -rn eth0 /etc/network/interfaces /etc/netplan/ 2>/dev/null`. If it finds anything, delete those lines. On Ubuntu, run `sudo netplan apply` afterwards.

Next, run: 

```
sudo systemctl enable --now NetworkManager
sudo nmcli dev set eth0 managed yes
```
To make sure Ubuntu doesn't switch the port back to unmanaged after a reboot, add this file:
```
printf '[keyfile]\nunmanaged-devices=*,except:interface-name:eth0\n' | \
  sudo tee /etc/NetworkManager/conf.d/99-printer.conf
sudo systemctl restart NetworkManager
```

### Step 3: Creating the shared connection

```
sudo nmcli con add type ethernet ifname eth0 con-name printer-link \
     ipv4.method shared ipv4.addresses 10.42.0.1/24 ipv6.method disabled
sudo nmcli con up printer-link

```

## Step 4: Finding the Printer's MAC address and connecting 

At this point your printer should be plugged in via Ethernet.

Run `cat /var/lib/NetworkManager/dnsmasq-eth0.leases`. 

If it doesn't show anything, you either have the wrong port name or the printer isn't plugged in.

Then run (replacing AA:BB:CC:DD:EE:FF with your actual MAC):

```
echo 'dhcp-host=AA:BB:CC:DD:EE:FF,10.42.0.67' | \
  sudo tee /etc/NetworkManager/dnsmasq-shared.d/q2-printer.conf
sudo nmcli con down printer-link && sudo nmcli con up printer-link
```
Reboot the printer so it picks up the new IP.

## Step 5. Check and install

Run `ping -c 3 10.42.0.67`. Three pings and you're good to go.

Next: [Run the installer](../install/run-installer.md). Substitute `192.168.1.50` with `10.42.0.67`.
