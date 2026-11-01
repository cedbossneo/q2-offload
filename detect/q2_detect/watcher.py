"""The watcher: follows Klipper's print state, sends a camera frame to Obico's ML API every
10 s while printing, applies Obico's decisions (warn, pause) and keeps the history.

`printer` is the Moonraker client, or anything with the same attributes (state, filename,
progress, ready, camera(), pause(), console()), which is how the tests drive it.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import time

from . import __version__, images, notify, obico, records, settings as settings_mod
from .mlapi import MlApiError

log = logging.getLogger(__name__)

TIMELINE_EVERY = 60  # frames: one timeline frame every 10 minutes
PAUSED_BY_WINDOW_S = 900  # a pause asked for this recently is ours, even queued behind a macro
FRAMES_SERVED = 3
HEALTH_EVERY_S = 30
QUEUE_SIZE = 8
MESSAGES = {
    "pause": ("Print paused: failure detected", "Obico sees a failing print and paused it."),
    "would-pause": ("Failure detected", "Obico sees a failing print. Observe mode: the print goes on."),
    "warning": ("Possible print failure", "Obico sees something that may be a failure."),
}


class Conflict(Exception):
    pass


class Watcher:
    def __init__(self, store, session, mlapi, frame_base: str, clock=time.time, frame_s: float = obico.FRAME_S):
        self.store = store
        self.session = session
        self.mlapi = mlapi
        self.frame_base = frame_base.rstrip("/")
        self.clock = clock
        self.frame_s = frame_s
        self.printer = None
        self.settings = store.load_settings()
        self.baseline = store.load_baseline()
        self.record = self._latest()
        self.frames: dict[int, bytes] = {}
        self.seq = 0
        self.last_jpeg: bytes | None = None
        self.ml = {"ok": None, "error": None, "ms": None}
        self.camera_error: str | None = None
        self.listeners: set[asyncio.Queue] = set()
        self.tasks: set[asyncio.Task] = set()
        self._last_health = 0.0
        self._last_seen = None

    def _latest(self) -> records.Print | None:
        """The newest print that loads: a folder left half-written by a power cut is skipped."""
        for print_id in self.store.print_ids():
            try:
                return self.store.load_print(print_id)
            except (LookupError, KeyError, TypeError, ValueError) as exc:
                log.warning("skipping print %s: %s", print_id, exc)
        return None

    # printer state

    def on_printer_change(self) -> None:
        """Moonraker reports progress several times a second: only real changes go to the page."""
        printer = self.printer
        camera = printer.camera() if printer else None
        seen = (self._state(), printer.filename if printer else "", round(printer.progress if printer else 0.0, 2),
                camera and camera.get("snapshot_url"))
        if seen == self._last_seen:
            return
        self._last_seen = seen
        self._sync()
        self.publish()

    def _state(self) -> str:
        return self.printer.state if self.printer and self.printer.ready else "offline"

    def _sync(self) -> None:
        state, now, record = self._state(), self.clock(), self.record
        if state in ("printing", "paused"):
            filename = self.printer.filename or (record.filename if record else "")
            if record is None or not record.open or filename != record.filename:
                if record is not None and record.open:
                    self._end(record, "cancelled")
                self.record = records.start(filename, self.baseline, now)
                self.store.save_print(self.record)
                self.store.prune(self.settings["keep_prints"], self.record.id)
            elif record.status != state:
                ours = state == "paused" and record.alerts.paused and now - record.alerts.paused < PAUSED_BY_WINDOW_S
                paused_by = ("detection" if ours else "user") if state == "paused" else None
                self._save(dataclasses.replace(record, status=state, paused_by=paused_by))
        elif state in records.END_STATUS and record is not None and record.open:
            self._end(record, records.END_STATUS[state])

    def _end(self, record: records.Print, status: str) -> None:
        last = record.last_frame
        if self.last_jpeg and last and (not record.timeline or record.timeline[-1]["t"] < last["t"]):
            record = self._keep_timeline(record, self.last_jpeg, last["t"])
        self._save(dataclasses.replace(record, status=status, ended=self.clock()))
        self.store.save_baseline(self.baseline)
        self.store.prune(self.settings["keep_prints"], None)

    def _save(self, record: records.Print) -> None:
        self.store.save_print(record)
        if self.record is None or self.record.id == record.id:
            self.record = record

    # the frame loop

    async def run(self) -> None:
        while True:
            started = self.clock()
            try:
                if self._watching():
                    await self.analyse()
                elif started - self._last_health > HEALTH_EVERY_S:
                    await self._health()
            except Exception:  # never let one bad frame stop the watch
                log.exception("frame analysis failed")
            await asyncio.sleep(max(0.5, self.frame_s - (self.clock() - started)))

    def _watching(self) -> bool:
        return (self.settings["enabled"] and self._state() == "printing"
                and self.record is not None and self.record.open)

    async def _health(self) -> None:
        self._last_health = self.clock()
        ok = await self.mlapi.healthy()
        if ok != self.ml["ok"]:
            self.ml = {**self.ml, "ok": ok, "error": None if ok else "Obico's ML API does not answer"}
            self.publish()

    async def analyse(self) -> None:
        camera = self.printer.camera()
        if not camera or not camera["snapshot_url"]:
            return self._fail_camera("Moonraker has no webcam with a snapshot URL")
        try:
            jpeg = await images.fetch(self.session, camera["snapshot_url"])
        except images.CameraError as exc:
            return self._fail_camera(str(exc))
        self.camera_error = None
        self.seq += 1
        self.frames = {k: v for k, v in self.frames.items() if k > self.seq - FRAMES_SERVED} | {self.seq: jpeg}
        sent, record_id = self.clock(), self.record.id
        try:
            detections = await self.mlapi.detect(f"{self.frame_base}/internal/frames/{self.seq}.jpg")
        except MlApiError as exc:
            self.ml = {"ok": False, "error": str(exc), "ms": None}
            return self.publish()
        now = self.clock()
        self.ml = {"ok": True, "error": None, "ms": round((now - sent) * 1000)}
        if not self._watching() or self.record.id != record_id:  # paused or ended meanwhile: not counted
            return self.publish()
        width, height = images.size(jpeg)
        self._save(self._observe(self.record, detections, jpeg, width, height, now))
        self.last_jpeg = jpeg
        self.baseline = self.record.pred.baseline
        self.store.save_baseline(self.baseline)
        self.publish()

    def _fail_camera(self, message: str) -> None:
        self.camera_error = message
        self.publish()

    def _observe(self, record, detections, jpeg, width, height, now) -> records.Print:
        sensitivity, mode = self.settings["sensitivity"], self.settings["mode"]
        pred = obico.observe(record.pred, obico.frame_p(detections))
        series = obico.push(record.series, pred.p, obico.score(pred, sensitivity))
        alerts, action = obico.decide(pred, record.alerts, mode, sensitivity, now)
        boxes = images.boxes(detections, width, height)
        last = {"t": now, "ms": self.ml["ms"], "width": width, "height": height, "detections": boxes}
        record = dataclasses.replace(record, pred=pred, series=series, alerts=alerts, last_frame=last)
        if pred.frame % TIMELINE_EVERY == 1:
            record = self._keep_timeline(record, jpeg, now)
        if action:
            record = self._decision(record, action, jpeg, boxes, now)
        return record

    def _keep_timeline(self, record, jpeg: bytes, t: float) -> records.Print:
        name = f"t{len(record.timeline):03d}.jpg"
        self.store.save_image(record.id, name, images.thumbnail(jpeg))
        return dataclasses.replace(record, timeline=record.timeline + ({"t": t, "file": name},))

    def _decision(self, record, action: str, jpeg: bytes, boxes: list, now: float) -> records.Print:
        n = len(record.decisions)
        name = f"d{n:03d}.jpg"
        self.store.save_image(record.id, name, jpeg)
        score = round(obico.score(record.pred, self.settings["sensitivity"]), 3)
        warning, pause = obico.levels(record.pred)
        decision = {"n": n, "t": now, "kind": action, "score": score, "snapshot": name, "detections": boxes,
                    "levels": {"warning": round(warning, 3), "pause": round(pause, 3)}, "label": None}
        log.warning("%s on %s (frame %d, score %.2f)", action, record.filename, record.pred.frame, score)
        self._act(record, action, jpeg, boxes, score)
        return dataclasses.replace(record, decisions=record.decisions + (decision,))

    def _act(self, record, action: str, jpeg: bytes, boxes: list, score: float) -> None:
        cfg = self.settings["notify"]
        wanted = (cfg["on_warning"] if action == "warning" else cfg["on_pause"]) and cfg["urls"]
        image = images.annotated(jpeg, boxes) if wanted and cfg["attach_image"] else None
        self.spawn(self._report(record.id, record.filename, action, score, image if wanted else False))

    async def _report(self, record_id: str, filename: str, action: str, score: float, image) -> None:
        """Pause first when asked, so the message says whether it worked; then the console line
        and the notification (image False: no notification wanted)."""
        title, text = MESSAGES[action]
        if action == "pause":
            try:
                await self.printer.pause()
            except Exception as exc:
                log.warning("pause refused: %s", exc)
                title, text = "Failure detected, pause FAILED", f"Obico sees a failing print but pausing failed: {exc}."
                self._pause_failed(record_id)
        await self._quietly(self.printer.console(f"Failure detection: {title} (score {score:.2f})"))
        if image is not False:
            cfg = self.settings["notify"]
            await self._quietly(notify.send(cfg["urls"], title, f"{text} {filename} (score {score:.2f}).", image or None))

    def _pause_failed(self, record_id: str) -> None:
        """Let the next failing frame ask again (obico.PAUSE_TRIES in all)."""
        if self.record is not None and self.record.id == record_id and self.record.open:
            self._save(dataclasses.replace(self.record, alerts=dataclasses.replace(self.record.alerts, paused=0.0)))
            self.publish()

    async def _quietly(self, coro) -> None:
        try:
            await coro
        except Exception as exc:
            log.warning("could not send: %s", exc)

    def spawn(self, coro) -> None:
        task = asyncio.ensure_future(coro)
        self.tasks.add(task)
        task.add_done_callback(self._done)

    def _done(self, task: asyncio.Task) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and task.exception():
            log.warning("background action failed: %s", task.exception())

    # what the page does

    def _current(self) -> records.Print:
        if self.record is None or not self.record.open:
            raise Conflict("no print in progress")
        return self.record

    def ack(self) -> None:
        record = self._current()
        self._save(dataclasses.replace(record, alerts=dataclasses.replace(record.alerts, acked=self.clock())))
        self.publish()

    def mute(self) -> None:
        record = self._current()
        self._save(dataclasses.replace(record, alerts=dataclasses.replace(record.alerts, muted=True)))
        self.publish()

    def update_settings(self, patch: dict) -> dict:
        self.settings = settings_mod.merge(self.settings, patch)
        self.store.save_settings(self.settings)
        self.publish()
        return self.settings

    def get_print(self, print_id: str) -> records.Print:
        if self.record is not None and self.record.id == print_id:
            return self.record
        return self.store.load_print(print_id)

    def label(self, print_id: str, n: int, value) -> records.Print:
        updated = records.label(self.get_print(print_id), n, value)
        self.store.save_print(updated)
        if self.record is not None and self.record.id == print_id:
            self.record = updated
            self.publish()
        return updated

    def delete(self, print_id: str) -> None:
        if self.record is not None and self.record.id == print_id and self.record.open:
            raise Conflict("this print is still running")
        self.store.load_print(print_id)
        self.store.delete_print(print_id)
        if self.record is not None and self.record.id == print_id:
            ids = self.store.print_ids()
            self.record = self.store.load_print(ids[0]) if ids else None
            self.publish()

    def prints(self, limit: int) -> dict:
        found = [self.record if self.record is not None and p.id == self.record.id else p
                 for p in self.store.load_prints()]
        lines = [records.summary(p) for p in found]
        totals = {k: sum(line[k] for line in lines) for k in ("warnings", "pauses", "false_alarms", "real_failures", "unreviewed")}
        hours = sum(p.pred.frame for p in found) * obico.FRAME_S / 3600
        return {"summary": {"prints": len(found), "watched_hours": round(hours, 1), **totals}, "prints": lines[:limit]}

    def status(self) -> dict:
        printer = self.printer
        return {
            "version": __version__,
            "settings": self.settings,
            "ml_api": self.ml,
            "camera": {**(printer.camera() or {"name": None, "stream_url": None, "snapshot_url": None}),
                       "error": self.camera_error} if printer else None,
            "printer": {"state": self._state(), "filename": printer.filename if printer else "",
                        "progress": printer.progress if printer else 0.0},
            "print": records.view(self.record, self.settings["sensitivity"], self.frame_s) if self.record else None,
        }

    # live updates for the page

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(QUEUE_SIZE)
        self.listeners.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        self.listeners.discard(queue)

    def publish(self) -> None:
        if not self.listeners:
            return
        payload = self.status()
        for queue in self.listeners:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(payload)
