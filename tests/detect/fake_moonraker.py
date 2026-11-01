"""A Moonraker for the failure detection end-to-end test: the websocket calls q2-detect makes,
a webcam serving one JPEG, POST /printer/print/resume, and /control to change the print state
or the camera picture. Pausing flips the state.
Usage: python3 tests/detect/fake_moonraker.py <jpeg> [port]
  POST /control?state=printing&filename=x.gcode&frame=other.jpg
  GET /control -> {"state", "pauses", "console"}"""
import asyncio
import json
import pathlib
import sys

from aiohttp import web

FRAME = {"jpeg": pathlib.Path(sys.argv[1]).read_bytes()}
PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 7125
STATE = {"state": "standby", "filename": "", "pauses": 0, "console": []}
CLIENTS: set = set()


def status() -> dict:
    return {"print_stats": {"state": STATE["state"], "filename": STATE["filename"]}, "virtual_sdcard": {"progress": 0.4}}


async def push() -> None:
    msg = json.dumps({"jsonrpc": "2.0", "method": "notify_status_update", "params": [status(), 0.0]})
    for ws in list(CLIENTS):
        await ws.send_str(msg)


async def answer(method: str, params: dict):
    if method == "server.webcams.list":
        url = f"http://127.0.0.1:{PORT}/webcam/?action="
        return {"webcams": [{"name": "q2", "enabled": True, "stream_url": url + "stream", "snapshot_url": url + "snapshot"}]}
    if method == "server.info":
        return {"klippy_state": "ready"}
    if method == "printer.objects.subscribe":
        return {"eventtime": 0.0, "status": status()}
    if method == "printer.print.pause":
        STATE["pauses"] += 1
        STATE["state"] = "paused"
        asyncio.get_running_loop().call_soon(lambda: asyncio.ensure_future(push()))
        return "ok"
    if method == "printer.gcode.script":
        STATE["console"].append(params.get("script"))
        return "ok"
    return {"connection_id": 1}


async def websocket(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    CLIENTS.add(ws)
    try:
        async for msg in ws:
            call = json.loads(msg.data)
            result = await answer(call["method"], call.get("params") or {})
            await ws.send_str(json.dumps({"jsonrpc": "2.0", "result": result, "id": call["id"]}))
    finally:
        CLIENTS.discard(ws)
    return ws


async def webcam(request):
    return web.Response(body=FRAME["jpeg"], content_type="image/jpeg")


async def resume(request):
    STATE["state"] = "printing"
    await push()
    return web.json_response({"result": "ok"})


async def control(request):
    if request.method == "POST":
        STATE["state"] = request.query.get("state", STATE["state"])
        STATE["filename"] = request.query.get("filename", STATE["filename"])
        if "frame" in request.query:
            FRAME["jpeg"] = pathlib.Path(request.query["frame"]).read_bytes()
        await push()
    return web.json_response(STATE)


app = web.Application()
app.add_routes([web.get("/websocket", websocket), web.get("/webcam/", webcam),
                web.get("/control", control), web.post("/control", control),
                web.post("/printer/print/resume", resume)])
web.run_app(app, host="127.0.0.1", port=PORT, print=None)
