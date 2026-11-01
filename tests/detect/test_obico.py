"""Obico's rules as ported in detect/q2_detect/obico.py, frame by frame without the service.
Usage: python3 tests/detect/test_obico.py"""
import dataclasses

from helpers import SPAGHETTI, run

from q2_detect import obico

NOW = 1_800_000_000.0


def play(ps, mode="pause", baseline=obico.Baseline(2000, 0.0), alerts=obico.Alerts()):
    """Feed one p per 10 s frame; returns the frame numbers of each decision and the end state."""
    pred, decisions = obico.Prediction(baseline=baseline), []
    for i, p in enumerate(ps):
        pred = obico.observe(pred, p)
        alerts, action = obico.decide(pred, alerts, mode, 1.0, NOW + 10 * i)
        if action:
            decisions.append((pred.frame, action))
    return decisions, pred, alerts


def spaghetti_from(frame, total):
    return [0.0] * frame + [SPAGHETTI[i % 5] for i in range(total - frame)]


def test_the_first_five_minutes_never_alert():
    decisions, _, _ = play(spaghetti_from(0, 29))
    assert decisions == []
    decisions, _, _ = play(spaghetti_from(0, 34))
    assert decisions and decisions[0][0] >= obico.INIT_SAFE_FRAME_NUM


def test_a_first_print_ever_has_no_baseline_yet():
    # The long-term mean is learnt from every frame: on a fresh install a print failing from its
    # first frame looks like the norm, as with Obico itself
    decisions, _, _ = play(spaghetti_from(0, 60), baseline=obico.Baseline())
    assert decisions == []


def test_warning_then_pause_mid_print():
    decisions, _, _ = play(spaghetti_from(240, 260))
    assert decisions[0] == (242, "warning") and decisions[1] == (244, "pause"), decisions


def test_one_pause_per_print_then_only_alerts():
    decisions, _, alerts = play(spaghetti_from(240, 300))
    assert [k for _, k in decisions] == ["warning", "pause"], decisions
    # The user resumed and said it looks fine: the failure carries on, it alerts, never pauses again
    resumed = dataclasses.replace(alerts, acked=NOW + 3000)
    decisions, _, _ = play(spaghetti_from(240, 300), alerts=resumed)
    assert "pause" not in [k for _, k in decisions] and "warning" in [k for _, k in decisions], decisions


def test_a_refused_pause_is_asked_again_once():
    refused = obico.Alerts(pause_sent=1, alerted=NOW, acked=NOW)
    decisions, _, alerts = play(spaghetti_from(240, 260), alerts=refused)
    assert ("pause" in [k for _, k in decisions]) and alerts.pause_sent == 2
    decisions, _, _ = play(spaghetti_from(240, 260), alerts=dataclasses.replace(alerts, paused=0.0))
    assert "pause" not in [k for _, k in decisions], "two tries at most"


def test_observe_mode_says_would_pause_once():
    decisions, _, alerts = play(spaghetti_from(240, 300), mode="observe")
    assert [k for _, k in decisions] == ["warning", "would-pause"], decisions
    assert alerts.would_pause and alerts.paused == 0


def test_an_acknowledgement_holds_the_pause_for_the_cooldown():
    # Acknowledged at frame 243: no pause within 90 s, then Obico may pause again
    alerts = obico.Alerts(acked=NOW + 2420)
    decisions, _, _ = play(spaghetti_from(240, 250), alerts=alerts)
    assert all(kind != "pause" for _, kind in decisions), decisions
    decisions, _, _ = play(spaghetti_from(240, 255), alerts=alerts)
    assert decisions[-1] == (252, "pause"), decisions


def test_muted_says_nothing():
    decisions, _, _ = play(spaghetti_from(240, 300), alerts=obico.Alerts(muted=True))
    assert decisions == []


def test_levels_follow_obico():
    pred = obico.Prediction(frame=100, short=0.05, baseline=obico.Baseline(5000, 0.0))
    assert obico.levels(pred) == (obico.THRESHOLD_LOW, obico.THRESHOLD_LOW * obico.ESCALATING_FACTOR)
    pred = dataclasses.replace(pred, short=0.5)
    assert obico.levels(pred)[0] == obico.THRESHOLD_HIGH


def test_series_keeps_a_ten_hour_print_within_its_buckets():
    series = obico.Series()
    for i in range(3600):
        series = obico.push(series, 0.3 if i == 1234 else 0.1, 0.0)
    assert len(series.p) < obico.SERIES_MAX and series.step == 16
    assert max(series.p) == 0.3, "a spike survives the halving"
    assert len(series.p) * series.step >= 3600 - series.step


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    print("%d obico tests passed" % run(tests))
