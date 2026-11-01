"""Obico's first-generation failure detection rules, one 10 s frame at a time.

Ported as they are from obico-server: backend/lib/prediction.py (update_prediction_with_detections,
is_failing), FD_1ST_GEN_PARAMS in backend/config/settings.py and the alert / pause rules of
api/octoprint_views.py (alert_should_be_suppressed, pause_if_needed). Pure functions on frozen
dataclasses, so the watcher, the API and the tests share them.
"""
from __future__ import annotations

import dataclasses

EWM_SPAN = 12
ROLLING_WIN_SHORT = 310
ROLLING_WIN_LONG = 7200
THRESHOLD_LOW = 0.38
THRESHOLD_HIGH = 0.78
INIT_SAFE_FRAME_NUM = 30
ROLLING_MEAN_SHORT_MULTIPLE = 3.8
ESCALATING_FACTOR = 1.75
VISUALIZATION_THRESH = 0.2
ALERT_COOLDOWN_S = 90
FRAME_S = 10

PAUSE_TRIES = 2
SERIES_MAX = 240


@dataclasses.dataclass(frozen=True)
class Baseline:
    """This printer's long-term mean of p and the frame count behind it, kept across prints."""
    lifetime: int = 0
    long: float = 0.0


@dataclasses.dataclass(frozen=True)
class Prediction:
    """One print's state (PrinterPrediction, reset for every print)."""
    frame: int = 0
    p: float = 0.0
    ewm: float = 0.0
    short: float = 0.0
    baseline: Baseline = Baseline()


@dataclasses.dataclass(frozen=True)
class Alerts:
    """What has been said and done about this print."""
    alerted: float = 0.0
    acked: float = 0.0
    muted: bool = False
    would_pause: bool = False
    paused: float = 0.0  # when the pause was asked for; cleared again if Moonraker refused it
    pause_sent: int = 0


def _rolling_mean(mean: float, p: float, count: int, win: int) -> float:
    return mean + (p - mean) / float(win if win <= count else count + 1)


def frame_p(detections: list) -> float:
    """p of one frame: the sum of its box confidences."""
    return sum(float(d[1]) for d in detections)


def observe(pred: Prediction, p: float) -> Prediction:
    """update_prediction_with_detections() for a frame scoring p."""
    alpha = 2 / (EWM_SPAN + 1)
    frame = pred.frame + 1
    lifetime = pred.baseline.lifetime + 1
    return Prediction(
        frame=frame,
        p=p,
        ewm=p * alpha + pred.ewm * (1 - alpha),
        short=_rolling_mean(pred.short, p, frame, ROLLING_WIN_SHORT),
        baseline=Baseline(lifetime, _rolling_mean(pred.baseline.long, p, lifetime, ROLLING_WIN_LONG)),
    )


def score(pred: Prediction, sensitivity: float) -> float:
    """The smoothed score above this printer's usual level, the one compared with the levels."""
    return (pred.ewm - pred.baseline.long) * sensitivity


def levels(pred: Prediction) -> tuple[float, float]:
    """Warning and pause levels on the score's scale (calc_normalized_p)."""
    warning = (pred.short - pred.baseline.long) * ROLLING_MEAN_SHORT_MULTIPLE
    warning = min(THRESHOLD_HIGH, max(THRESHOLD_LOW, warning))
    return warning, warning * ESCALATING_FACTOR


def is_failing(pred: Prediction, sensitivity: float, escalating: float = 1.0) -> bool:
    """is_failing()."""
    if pred.frame < INIT_SAFE_FRAME_NUM:
        return False
    adjusted = score(pred, sensitivity) / escalating
    if adjusted < THRESHOLD_LOW:
        return False
    if adjusted > THRESHOLD_HIGH:
        return True
    return adjusted > (pred.short - pred.baseline.long) * ROLLING_MEAN_SHORT_MULTIPLE


def _suppressed(alerts: Alerts, now: float) -> bool:
    """alert_should_be_suppressed(): one alert until acknowledged, never two within the cooldown."""
    return now - alerts.alerted < ALERT_COOLDOWN_S or alerts.alerted > alerts.acked


def decide(pred: Prediction, alerts: Alerts, mode: str, sensitivity: float, now: float) -> tuple[Alerts, str | None]:
    """What to do after a frame: "pause", "would-pause" (observe mode), "warning" or None.

    pause_if_needed() pauses once per print, and not within the cooldown after an
    acknowledgement: once paused (and resumed by the user), a failure only alerts. A pause
    Moonraker refused (alerts.paused cleared by the watcher) is asked for again, PAUSE_TRIES
    times at most.
    """
    if alerts.muted:
        return alerts, None
    should_pause = is_failing(pred, sensitivity, ESCALATING_FACTOR)
    should_alert = not should_pause and is_failing(pred, sensitivity)
    if should_pause and mode == "pause" and not alerts.paused and alerts.pause_sent < PAUSE_TRIES:
        if now - alerts.acked < ALERT_COOLDOWN_S:
            return alerts, None
        return dataclasses.replace(alerts, paused=now, pause_sent=alerts.pause_sent + 1, alerted=now), "pause"
    if should_pause and mode == "pause":
        should_pause, should_alert = False, True
    if should_pause and not alerts.would_pause:
        return dataclasses.replace(alerts, would_pause=True, alerted=now), "would-pause"
    if (should_pause or should_alert) and not _suppressed(alerts, now):
        return dataclasses.replace(alerts, alerted=now), "would-pause" if should_pause else "warning"
    return alerts, None


@dataclasses.dataclass(frozen=True)
class Series:
    """Up to SERIES_MAX buckets for the chart, each the highest value of `step` frames."""
    step: int = 1
    fill: int = 0
    p: tuple[float, ...] = ()
    score: tuple[float, ...] = ()


def _halve(values: tuple[float, ...]) -> tuple[float, ...]:
    return tuple(max(values[i:i + 2]) for i in range(0, len(values), 2))


def push(series: Series, p: float, s: float) -> Series:
    """Add one frame; halving keeps a whole print within SERIES_MAX buckets."""
    p, s = round(p, 2), round(s, 2)
    if 0 < series.fill < series.step:
        ps = series.p[:-1] + (max(series.p[-1], p),)
        ss = series.score[:-1] + (max(series.score[-1], s),)
        fill = series.fill + 1
    else:
        ps, ss, fill = series.p + (p,), series.score + (s,), 1
    if len(ps) < SERIES_MAX:
        return Series(series.step, fill, ps, ss)
    return Series(series.step * 2, series.step + fill, _halve(ps), _halve(ss))
