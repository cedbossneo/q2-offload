"""The failure detection service against simulated prints: a frame every 10 s answered with
Obico detections whose summed confidence follows the scenario, Obico's rules deciding, and what
the service keeps and does. Usage: python3 tests/detect/test_watcher.py"""
import asyncio

from helpers import FRAME, Rig, run, spaghetti

from q2_detect import obico, store, watcher


async def test_clean_print_never_alerts():
    rig = Rig({"mode": "pause"})
    rig.warm_up()
    rig.set_state("printing")
    await rig.frames(600, lambda i: 1.2 if i % 97 == 50 else 0.0)
    assert rig.record().decisions == ()
    assert rig.printer.paused == 0 and rig.notified == []
    assert rig.record().pred.frame == 600


async def test_spaghetti_pauses_within_a_minute_in_pause_mode():
    rig = Rig({"mode": "pause", "notify": {"urls": ["ntfy://x/y"], "on_warning": True, "on_pause": True, "attach_image": True}})
    rig.warm_up()
    rig.set_state("printing")
    await rig.frames(240)
    n = 0
    while not rig.printer.paused and n < 30:
        await rig.frames(1, spaghetti(n))
        n += 1
    assert n * 10 <= 60, f"paused after {n * 10} s"
    kinds = [d["kind"] for d in rig.record().decisions]
    assert kinds[-1] == "pause", kinds
    titles = [t for t, _, _ in rig.notified]
    assert "Print paused: failure detected" in titles
    assert rig.notified[-1][2][:2] == b"\xff\xd8", "the notification carries the picture"
    assert any("Failure detection" in line for line in rig.printer.console_lines)
    decision = rig.record().decisions[-1]
    assert rig.store.image_path(rig.record().id, decision["snapshot"]).read_bytes() == FRAME
    assert decision["levels"]["pause"] > decision["levels"]["warning"] > 0
    rig.set_state("paused")
    assert rig.watcher.status()["print"]["paused_by_detection"] is True
    rig.set_state("printing")
    rig.clock.now += 3600
    rig.set_state("paused")
    assert rig.watcher.status()["print"]["paused_by_detection"] is False, "a pause long after ours is the user's"
    assert decision["detections"] and decision["detections"][0][1:] == [0.3125, 0.4167, 0.1, 0.1]


async def test_a_refused_pause_is_reported_and_asked_again():
    rig = Rig({"mode": "pause", "notify": {"urls": ["ntfy://x/y"], "on_warning": False, "on_pause": True, "attach_image": False}})
    rig.warm_up()
    rig.printer.pause_error = "Print is busy"
    rig.set_state("printing")
    await rig.frames(240)
    await rig.frames(8, spaghetti)
    await asyncio.sleep(0)
    assert rig.printer.paused == 2, rig.printer.paused
    assert [t for t, _, _ in rig.notified].count("Failure detected, pause FAILED") == 2
    assert "Print is busy" in rig.notified[0][1]
    await rig.frames(20, spaghetti)
    assert rig.printer.paused == 2, "two tries at most"


async def test_paused_print_is_not_analysed_and_resumes_the_same_print():
    rig = Rig()
    rig.set_state("printing")
    await rig.frames(40)
    rig.set_state("paused")
    await rig.frames(10)
    assert rig.record().pred.frame == 40 and rig.record().status == "paused"
    first = rig.record().id
    rig.set_state("printing")
    await rig.frames(1)
    assert rig.record().id == first and rig.record().pred.frame == 41


async def test_observe_mode_reports_once_until_acknowledged():
    rig = Rig({"notify": {"urls": ["ntfy://x/y"], "on_warning": True, "on_pause": True, "attach_image": False}})
    rig.warm_up()
    rig.set_state("printing")
    await rig.frames(240)
    await rig.frames(60, spaghetti)
    assert rig.printer.paused == 0
    assert [t for t, _, _ in rig.notified].count("Failure detected") == 1
    assert rig.notified[0][2] is None, "attach_image off"
    assert rig.record().alert_pending
    rig.watcher.ack()
    assert not rig.record().alert_pending
    await rig.frames(1, spaghetti(0))
    assert [t for t, _, _ in rig.notified].count("Failure detected") == 2, "reported again, as Obico does"
    sent = len(rig.notified)
    rig.watcher.mute()
    await rig.frames(30, spaghetti)
    assert len(rig.notified) == sent and rig.record().alerts.muted


async def test_print_lifecycle_and_history():
    rig = Rig()
    rig.set_state("printing", "first.gcode")
    await rig.frames(70)
    rig.set_state("complete", "first.gcode")
    done = rig.record()
    assert done.status == "completed" and done.ended is not None
    assert [t["file"] for t in done.timeline] == ["t000.jpg", "t001.jpg", "t002.jpg"], done.timeline
    rig.clock.now += 60
    rig.set_state("printing", "second.gcode")
    assert rig.record().id != done.id and rig.record().pred.frame == 0
    assert rig.record().pred.baseline.lifetime == 70, "the long-term mean carries over"
    listing = rig.watcher.prints(50)
    assert [p["filename"] for p in listing["prints"]] == ["second.gcode", "first.gcode"]
    assert listing["summary"]["prints"] == 2 and listing["prints"][1]["thumbnail"] == "t001.jpg"


async def test_cancel_then_same_file_again_is_a_new_print():
    rig = Rig()
    rig.set_state("printing")
    await rig.frames(5)
    first = rig.record().id
    rig.set_state("cancelled")
    assert rig.record().status == "cancelled"
    rig.clock.now += 5
    rig.set_state("printing")
    assert rig.record().id != first and rig.record().pred.frame == 0


async def test_restart_continues_the_open_print():
    rig = Rig()
    rig.set_state("printing")
    await rig.frames(12)
    again = Rig(root=rig.root)
    again.set_state("printing")
    assert again.record().id == rig.record().id and again.record().pred.frame == 12
    again.set_state("complete")
    assert again.record().status == "completed"


async def test_camera_and_ml_api_errors_are_shown_and_not_counted():
    rig = Rig()
    rig.set_state("printing")
    await rig.frames(3)
    rig.camera_error = "camera not reachable: timeout"
    await rig.frames(1)
    assert rig.watcher.status()["camera"]["error"] == "camera not reachable: timeout"
    rig.camera_error = None
    rig.ml.error = "Obico's ML API answered HTTP 400"
    await rig.frames(1)
    status = rig.watcher.status()
    assert status["ml_api"] == {"ok": False, "error": "Obico's ML API answered HTTP 400", "ms": None}
    assert status["camera"]["error"] is None and rig.record().pred.frame == 3
    rig.ml.error = None
    await rig.frames(1)
    assert rig.watcher.status()["ml_api"]["ok"] and rig.record().pred.frame == 4


async def test_ml_api_fetches_the_frame_from_the_service():
    rig = Rig()
    rig.set_state("printing")
    await rig.frames(2)
    assert rig.ml.urls == ["http://127.0.0.1:7130/internal/frames/1.jpg", "http://127.0.0.1:7130/internal/frames/2.jpg"]
    assert rig.watcher.frames[2] == FRAME and rig.watcher.last_jpeg == FRAME


async def test_disabled_or_idle_analyses_nothing():
    rig = Rig({"enabled": False})
    rig.set_state("printing")
    await rig.frames(5)
    assert rig.record().pred.frame == 0
    idle = Rig()
    idle.set_state("standby")
    await idle.frames(5)
    assert idle.record() is None and idle.ml.urls == []


async def test_labels_and_delete():
    rig = Rig({"mode": "pause"})
    rig.warm_up()
    rig.set_state("printing")
    await rig.frames(240)
    await rig.frames(10, spaghetti)
    print_id = rig.record().id
    try:
        rig.watcher.delete(print_id)
        raise AssertionError("deleting the running print must fail")
    except watcher.Conflict:
        pass
    labelled = rig.watcher.label(print_id, 0, "false_alarm")
    assert labelled.decisions[0]["label"] == "false_alarm"
    assert rig.watcher.prints(5)["summary"]["false_alarms"] == 1
    for bad in ("maybe", 3):
        try:
            rig.watcher.label(print_id, 0, bad)
            raise AssertionError("bad label accepted")
        except ValueError:
            pass
    rig.set_state("complete")
    rig.watcher.delete(print_id)
    assert rig.watcher.prints(5)["prints"] == [] and rig.record() is None


async def test_old_prints_are_forgotten_beyond_keep_prints():
    rig = Rig({"keep_prints": 3})
    for n in range(5):
        rig.clock.now += 3600
        rig.set_state("printing", f"p{n}.gcode")
        await rig.frames(1)
        rig.set_state("complete", f"p{n}.gcode")
    names = [p["filename"] for p in rig.watcher.prints(10)["prints"]]
    assert names == ["p4.gcode", "p3.gcode", "p2.gcode"], names


async def test_status_payload_matches_the_contract():
    rig = Rig()
    rig.set_state("printing")
    await rig.frames(31, 0.3)
    status = rig.watcher.status()
    assert set(status) == {"version", "settings", "ml_api", "camera", "printer", "print"}
    assert status["printer"] == {"state": "printing", "filename": "part.gcode", "progress": 0.0}
    current = status["print"]
    for key in ("id", "filename", "started", "ended", "status", "frame", "frame_s", "safe_frames", "p", "score",
                "levels", "muted", "alert_pending", "last_frame", "series", "decisions", "timeline"):
        assert key in current, key
    assert current["last_frame"]["width"] == 1280 and current["frame_s"] == 10
    assert current["levels"]["pause"] == round(current["levels"]["warning"] * obico.ESCALATING_FACTOR, 3)


async def test_publish_reaches_subscribers():
    rig = Rig()
    queue = rig.watcher.subscribe()
    rig.set_state("printing")
    assert (await asyncio.wait_for(queue.get(), 1))["printer"]["state"] == "printing"
    rig.watcher.unsubscribe(queue)


async def test_settings_are_validated_and_kept():
    rig = Rig()
    rig.watcher.update_settings({"mode": "pause", "notify": {"urls": ["tgram://token/chat"]}})
    assert store.Store(rig.root).load_settings()["mode"] == "pause"
    assert rig.watcher.settings["notify"]["on_pause"] is True
    for bad in ({"mode": "panic"}, {"sensitivity": 9}, {"notify": {"urls": ["nope"]}}, {"colour": 1}, {"enabled": "yes"}):
        try:
            rig.watcher.update_settings(bad)
            raise AssertionError(f"accepted {bad}")
        except ValueError:
            pass


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    print("%d watcher tests passed" % run(tests))
