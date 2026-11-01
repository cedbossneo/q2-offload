"""The HTTP API the detection page uses (detect/q2_detect/api.py), on a real aiohttp server
over a simulated print. Usage: python3 tests/detect/test_api.py"""
import asyncio
import json

from aiohttp.test_utils import TestClient, TestServer
from helpers import FRAME, Rig, run, spaghetti

from q2_detect import api


async def client_for(rig):
    client = TestClient(TestServer(api.build(rig.watcher)))
    await client.start_server()
    return client


async def failed_print(rig):
    rig.warm_up()
    rig.set_state("printing")
    await rig.frames(240)
    await rig.frames(10, spaghetti)


async def test_status_and_frame():
    rig = Rig()
    client = await client_for(rig)
    try:
        status = await (await client.get("/api/status")).json()
        assert status["print"] is None and status["printer"]["state"] == "standby"
        assert (await client.get("/api/frame.jpg")).status == 404
        rig.set_state("printing")
        await rig.frames(1, 0.5)
        resp = await client.get("/api/frame.jpg")
        assert resp.status == 200 and await resp.read() == FRAME
        status = await (await client.get("/api/status")).json()
        assert status["print"]["frame"] == 1 and status["print"]["last_frame"]["detections"]
    finally:
        await client.close()


async def test_events_stream_sends_status():
    rig = Rig()
    client = await client_for(rig)
    try:
        resp = await client.get("/api/events")
        assert resp.headers["Content-Type"] == "text/event-stream"
        first = await asyncio.wait_for(resp.content.readuntil(b"\n\n"), 2)
        assert first.startswith(b"event: status\ndata: ")
        rig.set_state("printing")
        second = await asyncio.wait_for(resp.content.readuntil(b"\n\n"), 2)
        assert json.loads(second.split(b"data: ", 1)[1])["printer"]["state"] == "printing"
        resp.close()
    finally:
        await client.close()


async def test_history_review_and_files():
    rig = Rig({"mode": "pause"})
    client = await client_for(rig)
    try:
        await failed_print(rig)
        rig.set_state("cancelled")
        listing = await (await client.get("/api/prints")).json()
        line = listing["prints"][0]
        assert line["status"] == "cancelled" and line["pauses"] >= 1 and listing["summary"]["unreviewed"] >= 1
        detail = await (await client.get(f"/api/prints/{line['id']}")).json()
        snapshot = detail["decisions"][0]["snapshot"]
        resp = await client.get(f"/api/prints/{line['id']}/{snapshot}")
        assert resp.status == 200 and await resp.read() == FRAME
        resp = await client.post(f"/api/prints/{line['id']}/decisions/0/label", json={"label": "real_failure"})
        assert (await resp.json())["decisions"][0]["label"] == "real_failure"
        assert (await client.post(f"/api/prints/{line['id']}/decisions/0/label", json={"label": "bof"})).status == 400
        assert (await client.post(f"/api/prints/{line['id']}/decisions/99/label", json={"label": None})).status == 404
        assert (await client.get(f"/api/prints/{line['id']}/../../settings.json")).status == 404
        assert (await client.get("/api/prints/nope")).status == 404
        assert (await client.delete(f"/api/prints/{line['id']}")).status == 200
        assert (await (await client.get("/api/prints")).json())["prints"] == []
    finally:
        await client.close()


async def test_running_print_cannot_be_deleted_and_actions_need_a_print():
    rig = Rig()
    client = await client_for(rig)
    try:
        assert (await client.post("/api/ack")).status == 409
        rig.set_state("printing")
        status = await (await client.get("/api/status")).json()
        assert (await client.delete(f"/api/prints/{status['print']['id']}")).status == 409
        assert (await (await client.post("/api/mute")).json())["print"]["muted"] is True
        assert (await client.post("/api/ack")).status == 200
    finally:
        await client.close()


async def test_settings_round_trip_and_validation():
    rig = Rig()
    client = await client_for(rig)
    try:
        resp = await client.put("/api/settings", json={"mode": "pause", "sensitivity": 1.2})
        assert (await resp.json())["mode"] == "pause"
        assert (await (await client.get("/api/settings")).json())["sensitivity"] == 1.2
        resp = await client.put("/api/settings", json={"mode": "panic"})
        assert resp.status == 400 and "mode" in (await resp.json())["error"]
        resp = await client.put("/api/settings", data="not json", headers={"Content-Type": "application/json"})
        assert resp.status == 400
        result = await (await client.post("/api/notify/test")).json()
        assert result == {"ok": False, "error": "no notification URL set"}
        assert (await client.post("/api/notify/test", json={"urls": ["nope"]})).status == 400
        sent = []

        async def fake_send(urls, title, body, image=None):
            sent.append(urls)
        api.notify_send, real = fake_send, api.notify_send
        try:
            result = await (await client.post("/api/notify/test", json={"urls": ["ntfy://ntfy.sh/t"]})).json()
        finally:
            api.notify_send = real
        assert result == {"ok": True} and sent == [["ntfy://ntfy.sh/t"]], "tried before saving"
        assert (await (await client.get("/api/settings")).json())["notify"]["urls"] == []
    finally:
        await client.close()


async def test_internal_frames_for_the_ml_api():
    rig = Rig()
    client = await client_for(rig)
    try:
        rig.set_state("printing")
        await rig.frames(1)
        resp = await client.get("/internal/frames/1.jpg")
        assert resp.status == 200 and await resp.read() == FRAME
        assert (await client.get("/internal/frames/9.jpg")).status == 404
    finally:
        await client.close()


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_")]
    print("%d api tests passed" % run(tests))
