"""One watched print: what Obico saw frame by frame, what was decided, and its JSON form."""
from __future__ import annotations

import dataclasses
import re
import time

from . import obico

LABELS = (None, "false_alarm", "real_failure")
# Klipper's print_stats.state at the end of a print -> the print's status in the history
END_STATUS = {"complete": "completed", "cancelled": "cancelled", "error": "error", "standby": "cancelled"}
ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[a-z0-9-]{1,40}$")
FILE_PATTERN = re.compile(r"^[td]\d{3,5}\.jpg$")


def new_id(filename: str, now: float) -> str:
    stem = re.sub(r"\.gcode$", "", filename.rsplit("/", 1)[-1], flags=re.I)
    slug = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")[:40] or "print"
    return time.strftime("%Y%m%d-%H%M%S", time.localtime(now)) + "-" + slug


@dataclasses.dataclass(frozen=True)
class Print:
    id: str
    filename: str
    started: float
    status: str = "printing"
    ended: float | None = None
    pred: obico.Prediction = obico.Prediction()
    alerts: obico.Alerts = obico.Alerts()
    series: obico.Series = obico.Series()
    last_frame: dict | None = None
    decisions: tuple = ()
    timeline: tuple = ()
    paused_by: str | None = None  # "detection" or "user" while paused

    @property
    def open(self) -> bool:
        return self.ended is None

    @property
    def alert_pending(self) -> bool:
        return self.alerts.alerted > self.alerts.acked and not self.alerts.muted

    def counts(self) -> dict:
        kinds = [d["kind"] for d in self.decisions]
        labels = [d.get("label") for d in self.decisions]
        return {
            "warnings": kinds.count("warning"),
            "pauses": kinds.count("pause") + kinds.count("would-pause"),
            "false_alarms": labels.count("false_alarm"),
            "real_failures": labels.count("real_failure"),
            "unreviewed": labels.count(None),
        }


def start(filename: str, baseline: obico.Baseline, now: float) -> Print:
    return Print(id=new_id(filename, now), filename=filename, started=now,
                 pred=obico.Prediction(baseline=baseline))


def view(record: Print, sensitivity: float, frame_s: float = obico.FRAME_S) -> dict:
    """The print as the page reads it (status.print, GET /prints/{id})."""
    warning, pause = obico.levels(record.pred)
    return {
        "id": record.id,
        "filename": record.filename,
        "started": record.started,
        "ended": record.ended,
        "status": record.status,
        "frame": record.pred.frame,
        "frame_s": frame_s,
        "safe_frames": obico.INIT_SAFE_FRAME_NUM,
        "p": round(record.pred.p, 3),
        "score": round(obico.score(record.pred, sensitivity), 3),
        "levels": {"warning": round(warning, 3), "pause": round(pause, 3)},
        "muted": record.alerts.muted,
        "alert_pending": record.alert_pending,
        "paused_by_detection": record.status == "paused" and record.paused_by == "detection",
        "last_frame": record.last_frame,
        "series": {"step": record.series.step, "p": list(record.series.p), "score": list(record.series.score)},
        "decisions": [dict(d) for d in record.decisions],
        "timeline": [dict(t) for t in record.timeline],
    }


def summary(record: Print) -> dict:
    """One line of GET /prints."""
    thumbs = [t["file"] for t in record.timeline]
    return {
        "id": record.id,
        "filename": record.filename,
        "started": record.started,
        "ended": record.ended,
        "status": record.status,
        "frames": record.pred.frame,
        "max_score": max(record.series.score, default=0.0),
        **record.counts(),
        "thumbnail": thumbs[len(thumbs) // 2] if thumbs else None,
    }


def to_json(record: Print) -> dict:
    return {
        "id": record.id,
        "filename": record.filename,
        "started": record.started,
        "status": record.status,
        "ended": record.ended,
        "pred": dataclasses.asdict(record.pred),
        "alerts": dataclasses.asdict(record.alerts),
        "series": dataclasses.asdict(record.series),
        "last_frame": record.last_frame,
        "decisions": list(record.decisions),
        "timeline": list(record.timeline),
        "paused_by": record.paused_by,
    }


def from_json(raw: dict) -> Print:
    pred = dict(raw.get("pred") or {})
    pred["baseline"] = obico.Baseline(**(pred.get("baseline") or {}))
    series = dict(raw.get("series") or {})
    return Print(
        id=raw["id"],
        filename=raw.get("filename", ""),
        started=float(raw["started"]),
        status=raw.get("status", "printing"),
        ended=raw.get("ended"),
        pred=obico.Prediction(**pred),
        alerts=obico.Alerts(**(raw.get("alerts") or {})),
        series=obico.Series(series.get("step", 1), series.get("fill", 0),
                            tuple(series.get("p", ())), tuple(series.get("score", ()))),
        last_frame=raw.get("last_frame"),
        decisions=tuple(raw.get("decisions") or ()),
        timeline=tuple(raw.get("timeline") or ()),
        paused_by=raw.get("paused_by"),
    )


def label(record: Print, n: int, value) -> Print:
    if value not in LABELS:
        raise ValueError("label is false_alarm, real_failure or null")
    if not 0 <= n < len(record.decisions):
        raise LookupError(f"no decision {n}")
    decisions = tuple({**d, "label": value} if i == n else d for i, d in enumerate(record.decisions))
    return dataclasses.replace(record, decisions=decisions)
