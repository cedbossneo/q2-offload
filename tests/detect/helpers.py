"""Shared test doubles for the failure detection service: a printer that prints when told, an
Obico ML API answering a scripted p per frame, a camera, and a watcher wired to them over a
temporary data directory. The spaghetti values are Obico's per-frame p on a real failed print
seen by the Q2 camera."""
import asyncio
import io
import logging
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "detect"))

from PIL import Image  # noqa: E402

from q2_detect import images, store, watcher  # noqa: E402
from q2_detect.mlapi import MlApiError  # noqa: E402

logging.getLogger("q2_detect").setLevel(logging.ERROR)
SPAGHETTI = [1.74, 1.13, 1.27, 1.91, 2.21]
WIDTH, HEIGHT = 1280, 720


def jpeg() -> bytes:
    out = io.BytesIO()
    Image.new("RGB", (WIDTH, HEIGHT), (40, 40, 40)).save(out, "JPEG")
    return out.getvalue()


FRAME = jpeg()


class Printer:
    def __init__(self):
        self.ready = True
        self.state = "standby"
        self.filename = ""
        self.progress = 0.0
        self.paused = 0
        self.pause_error = None
        self.console_lines = []
        self.webcam = {"name": "q2", "stream_url": "http://printer/webcam/?action=stream",
                       "snapshot_url": "http://printer/webcam/?action=snapshot"}

    def camera(self):
        return self.webcam

    async def pause(self):
        self.paused += 1
        if self.pause_error:
            raise RuntimeError(self.pause_error)
        self.state = "paused"

    async def console(self, message):
        self.console_lines.append(message)


class MlApi:
    """Answers with boxes whose confidences add up to self.p (or raises self.error)."""

    def __init__(self):
        self.p = 0.0
        self.error = None
        self.urls = []

    async def detect(self, url):
        self.urls.append(url)
        if self.error:
            raise MlApiError(self.error)
        out, left = [], self.p
        while left > 1e-9:
            out.append(["failure", min(0.9, left), (400.0, 300.0, 128.0, 128.0)])
            left -= 0.9
        return out

    async def healthy(self):
        return self.error is None


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


class Rig:
    """A watcher over a temporary directory, its printer, ML API and clock."""

    def __init__(self, settings=None, root=None):
        self.tmp = None if root else tempfile.TemporaryDirectory()
        self.root = pathlib.Path(root or self.tmp.name)
        self.clock = Clock()
        self.ml = MlApi()
        self.printer = Printer()
        self.notified = []
        self.store = store.Store(self.root)
        if settings:
            self.store.save_settings({**self.store.load_settings(), **settings})
        self.watcher = watcher.Watcher(self.store, None, self.ml, "http://127.0.0.1:7130", clock=self.clock)
        self.watcher.printer = self.printer

        async def fetch(session, url):
            if self.camera_error:
                raise images.CameraError(self.camera_error)
            return FRAME

        async def send(urls, title, body, image=None):
            self.notified.append((title, body, image))

        self.camera_error = None
        images.fetch = fetch
        watcher.notify.send = send

    def set_state(self, state, filename="part.gcode"):
        self.printer.state = state
        self.printer.filename = filename
        self.watcher.on_printer_change()

    async def frames(self, n, p=0.0):
        for i in range(n):
            self.clock.now += 10
            self.ml.p = p(i) if callable(p) else p
            if self.watcher._watching():
                await self.watcher.analyse()
            await asyncio.sleep(0)

    def record(self):
        return self.watcher.record

    def warm_up(self, frames=2000):
        """A printer that has already watched clean prints: Obico's long-term mean is learnt."""
        from q2_detect import obico
        self.watcher.baseline = obico.Baseline(frames, 0.0)


def spaghetti(i):
    return SPAGHETTI[i % len(SPAGHETTI)]


def run(tests):
    for name, fn in tests:
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                asyncio.run(result)
        except Exception:
            print(f"{name} FAILED")
            raise
    return len(tests)
