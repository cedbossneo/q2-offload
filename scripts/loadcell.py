"""Shared helpers for the q2-offload load cell tests (flow-test.py, flow-ratio-test.py): Moonraker
calls, Klipper's raw load cell stream and the hotend/extruder status."""
import collections
import json
import math
import os
import socket
import statistics
import threading
import time
import urllib.error
import urllib.request

MOONRAKER = "http://localhost:7125"
KLIPPY_SOCK = os.path.expanduser("~/printer_data/comms/klippy.sock")
LOAD_CELL = "load_cell_probe"
FILAMENT_AREA = math.pi * (1.75 / 2) ** 2         # mm², 1.75 mm filament
STATUS = "extruder=temperature,target,power&motion_report=live_extruder_velocity"
LOG_DIR = os.path.expanduser("~/printer_data/logs")
BLOCK_SAMPLES = 32      # 50 ms at 640 samples/s


def request(path, body=None, timeout=10):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(MOONRAKER + path, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as reply:
        return json.load(reply)["result"]


def query(objects):
    return request("/printer/objects/query?" + objects)["status"]


def gcode(script, timeout=900):
    try:
        request("/printer/gcode/script", {"script": script}, timeout=timeout)
    except urllib.error.HTTPError as err:
        message = json.load(err).get("error", {}).get("message", str(err))
        raise SystemExit("G-code failed: %s\n  %s" % (script.splitlines()[0], message))


def emergency_stop():
    request("/printer/emergency_stop", {})


def confirm(question):
    return input("%s [y/N] " % question).strip().lower() in ("y", "yes")


class ForceStream(threading.Thread):
    """Klipper's raw load cell stream (load_cell/dump_force) in 50 ms blocks of
    (host time, mean, min, max). Klipper reports the nozzle pushed down as a negative force:
    the blocks hold the opposite, the force the filament pushes with."""

    def __init__(self):
        super().__init__(daemon=True)
        self.blocks = collections.deque(maxlen=12000)     # 10 minutes
        self.lock = threading.Lock()
        self.errors = 0
        self.failure = None
        self.last_time = 0.0
        self._offset = None
        self._pending = []
        self._base_errors = None

    def run(self):
        try:
            sock = socket.socket(socket.AF_UNIX)
            sock.connect(KLIPPY_SOCK)
            sock.sendall(json.dumps({"id": 1, "method": "load_cell/dump_force", "params": {
                "load_cell": LOAD_CELL, "response_template": {}}}).encode() + b"\x03")
            buf = b""
            while True:
                data = sock.recv(65536)
                if not data:
                    raise ConnectionError("Klipper closed the connection")
                *messages, buf = (buf + data).split(b"\x03")
                for raw in messages:
                    self.add(json.loads(raw).get("params"), time.time())
        except Exception as err:
            self.failure = err

    def add(self, params, received):
        if not params:
            return
        counts = (params.get("errors") or 0, params.get("overflows") or 0)
        self._base_errors = self._base_errors or counts
        self.errors = max(self.errors, sum(c - b for c, b in zip(counts, self._base_errors)))
        rows = [r for r in params.get("data") or [] if r[1] is not None]
        if not rows:
            return
        offset = received - rows[-1][0]                   # sample clock to host clock
        self._offset = offset if self._offset is None else min(self._offset, offset)
        self._pending += [(r[0], -r[1]) for r in rows]
        blocks = []
        while len(self._pending) >= BLOCK_SAMPLES:
            chunk, self._pending = self._pending[:BLOCK_SAMPLES], self._pending[BLOCK_SAMPLES:]
            forces = [f for _, f in chunk]
            blocks.append((chunk[-1][0] + self._offset, statistics.fmean(forces),
                           min(forces), max(forces)))
        with self.lock:
            self.blocks.extend(blocks)
            self.last_time = received

    def since(self, t0):
        with self.lock:
            out = []
            for block in reversed(self.blocks):
                if block[0] < t0:
                    break
                out.append(block)
        return out[::-1]


class StatusSampler(threading.Thread):
    """Hotend and extruder velocity from Moonraker (Klipper answers about 4 times a second)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.samples = []
        self.lock = threading.Lock()
        self.stopped = threading.Event()

    def run(self):
        while not self.stopped.is_set():
            try:
                s = query(STATUS)
            except Exception:
                time.sleep(0.25)
                continue
            ex = s["extruder"]
            sample = {"t": time.time(), "temp": ex["temperature"], "target": ex["target"],
                      "power": ex["power"],
                      "flow": s["motion_report"]["live_extruder_velocity"] * FILAMENT_AREA}
            with self.lock:
                self.samples.append(sample)
            time.sleep(0.05)

    def since(self, t0):
        with self.lock:
            return [s for s in self.samples if s["t"] >= t0]

    def latest(self):
        with self.lock:
            return self.samples[-1] if self.samples else None


def rate(blocks):
    """Least-squares slope of the force over time, g/s."""
    ts, fs = [b[0] for b in blocks], [b[1] for b in blocks]
    mt, mf = statistics.fmean(ts), statistics.fmean(fs)
    den = sum((t - mt) ** 2 for t in ts)
    return sum((t - mt) * (f - mf) for t, f in zip(ts, fs)) / den if den > 0 else 0.0


def spread(blocks):
    return max(b[3] for b in blocks) - min(b[2] for b in blocks)
