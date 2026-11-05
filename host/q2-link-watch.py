#!/usr/bin/env python3
"""Bring Klipper back when the link to the printer was lost and can work again.

Klipper does not reconnect by itself: after the printer was off, or the host started first, it
stays in an error until someone runs FIRMWARE_RESTART. This watches Moonraker and restarts the
link, and only acts on connection errors: never during a print, and never on a heater or other
fault, which a person has to see. Steps and their output go to q2-link-watch.log.

Usage: q2-link-watch.py --printer IP --printer-user USER --work DIR --log FILE
"""
import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

POLL_SECONDS = 15
# Klipper retries the MCUs for a while by itself: only step in after this long
STARTUP_GRACE_SECONDS = 150
SETTLE_SECONDS = 60
BACKOFF_SECONDS = 600
SSH_PORT = 22
CONNECTION_ERRORS = (
    "Unable to connect",
    "Lost communication",
    "Timeout on connect",
    "No communication with MCU",
    "Could not exclusively lock",
    "Unable to open serial port",
)


def is_connection_error(message):
    return any(text in (message or "") for text in CONNECTION_ERRORS)


def next_action(state, message, printer_up, seconds_in_state, attempts):
    """What to do now: None, "link" (restart the host side) or "full" (the printer's proxies too).
    The second try goes further, for a proxy that stopped forwarding."""
    if not printer_up:
        return None
    if state in ("error", "shutdown"):
        if not is_connection_error(message):
            return None
    elif not (state == "startup" and seconds_in_state >= STARTUP_GRACE_SECONDS):
        return None
    return "full" if attempts else "link"


class Watch:
    def __init__(self, args):
        self.args = args
        self.state = None
        self.since = time.monotonic()
        self.attempts = 0
        self.not_before = 0.

    def log(self, text):
        line = "%s %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), text)
        sys.stdout.write(line)
        sys.stdout.flush()
        with open(self.args.log, "a") as output:
            output.write(line)

    def run(self, *command):
        result = subprocess.run(command, capture_output=True, text=True, timeout=120, check=False)
        self.log("%s -> %d %s" % (" ".join(command), result.returncode, (result.stdout + result.stderr).strip()[:300]))

    def printer_up(self):
        try:
            socket.create_connection((self.args.printer, SSH_PORT), timeout=3).close()
            return True
        except OSError:
            return False

    def diagnose(self):
        """What the next person needs to find why the link stopped, before it is restarted."""
        self.run("ss", "-tn", "dst", self.args.printer)
        self.printer("pgrep -af socat; ls -l /dev/serial/by-id/; dmesg | tail -5")

    def printer(self, command):
        self.run("runuser", "-u", self.args.user, "--", "ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5",
                 "%s@%s" % (self.args.printer_user, self.args.printer), command)

    def recover(self, action):
        self.log("%s: %s step" % (self.state, action))
        self.diagnose()
        self.run("systemctl", "stop", "klipper")
        if action == "full":
            script = "%s/q2-printer.sh" % self.args.work
            self.printer("sudo -n /bin/bash %s proxies-stop; sudo -n /bin/bash %s proxies-start" % (script, script))
        self.run("systemctl", "restart", "q2-serial-bridge@*")
        time.sleep(2)
        self.run("systemctl", "start", "klipper")

    def tick(self):
        try:
            with urllib.request.urlopen("http://localhost:7125/printer/info", timeout=5) as response:
                info = json.load(response)["result"]
        except (OSError, ValueError, KeyError, urllib.error.URLError):
            return
        state, message = info.get("state"), info.get("state_message", "")
        now = time.monotonic()
        if state != self.state:
            self.log("state %s -> %s" % (self.state, state))
            self.state, self.since = state, now
        if state == "ready":
            self.attempts = 0
            self.not_before = 0.
            return
        # An install or an update is at work
        if subprocess.run(["systemctl", "is-active", "--quiet", "q2-offload"], check=False).returncode == 0:
            return
        if now < self.not_before:
            return
        action = next_action(state, message, self.printer_up(), now - self.since, self.attempts)
        if action:
            self.recover(action)
            self.attempts += 1
            self.not_before = now + (SETTLE_SECONDS if self.attempts < 2 else BACKOFF_SECONDS)
            self.state, self.since = None, time.monotonic()


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--printer", required=True)
    parser.add_argument("--printer-user", default="mks")
    parser.add_argument("--user", required=True, help="local user with the SSH key to the printer")
    parser.add_argument("--work", required=True, help="q2-offload directory on the printer")
    parser.add_argument("--log", required=True)
    watch = Watch(parser.parse_args())
    while True:
        try:
            watch.tick()
        except Exception as error:  # A helper must keep watching whatever happens
            watch.log("error: %r" % (error,))
        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
