"""The HTTP API the detection page uses (nginx serves it at /detect/api/), and the frames Obico's
ML API fetches (/internal/frames/, on localhost only: nginx does not proxy it)."""
from __future__ import annotations

import asyncio
import json
import logging

from aiohttp import web

from . import records, settings as settings_mod
from .notify import NotifyError, send as notify_send
from .watcher import Conflict

log = logging.getLogger(__name__)

KEEPALIVE_S = 15
LIMIT_MAX = 500


def _json(data, status: int = 200) -> web.Response:
    return web.json_response(data, status=status, dumps=lambda d: json.dumps(d, separators=(",", ":")))


def _error(status: int, message: str) -> web.Response:
    return _json({"error": message}, status)


@web.middleware
async def errors(request: web.Request, handler):
    try:
        return await handler(request)
    except web.HTTPException:
        raise
    except LookupError as exc:
        return _error(404, str(exc).strip("'"))
    except Conflict as exc:
        return _error(409, str(exc))
    except ValueError as exc:
        return _error(400, str(exc))
    except Exception:
        log.exception("%s %s failed", request.method, request.path)
        return _error(500, "internal error, see the q2-detect log")


async def _body(request: web.Request):
    try:
        return await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError("the body is not valid JSON") from exc


def build(watcher) -> web.Application:
    routes = web.RouteTableDef()

    @routes.get("/api/status")
    async def status(request):
        return _json(watcher.status())

    @routes.get("/api/events")
    async def events(request):
        resp = web.StreamResponse(headers={
            "Content-Type": "text/event-stream", "Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
        await resp.prepare(request)
        queue = watcher.subscribe()
        try:
            await resp.write(f"event: status\ndata: {json.dumps(watcher.status())}\n\n".encode())
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), KEEPALIVE_S)
                    await resp.write(f"event: status\ndata: {json.dumps(payload)}\n\n".encode())
                except asyncio.TimeoutError:
                    await resp.write(b": keepalive\n\n")
        except (ConnectionResetError, asyncio.CancelledError):
            pass
        finally:
            watcher.unsubscribe(queue)
        return resp

    @routes.get("/api/frame.jpg")
    async def frame(request):
        if not watcher.last_jpeg:
            return _error(404, "no frame analysed yet")
        return web.Response(body=watcher.last_jpeg, content_type="image/jpeg", headers={"Cache-Control": "no-store"})

    @routes.get("/api/prints")
    async def prints(request):
        try:
            limit = max(1, min(LIMIT_MAX, int(request.query.get("limit", "50"))))
        except ValueError:
            raise ValueError("limit is a number") from None
        return _json(watcher.prints(limit))

    @routes.get("/api/prints/{id}")
    async def one_print(request):
        record = watcher.get_print(request.match_info["id"])
        return _json(records.view(record, watcher.settings["sensitivity"], watcher.frame_s))

    @routes.get("/api/prints/{id}/{file}")
    async def print_file(request):
        path = watcher.store.image_path(request.match_info["id"], request.match_info["file"])
        return web.FileResponse(path, headers={"Cache-Control": "max-age=86400"})

    @routes.post("/api/prints/{id}/decisions/{n}/label")
    async def label(request):
        body = await _body(request)
        if not isinstance(body, dict) or "label" not in body:
            raise ValueError('send {"label": "false_alarm" | "real_failure" | null}')
        try:
            n = int(request.match_info["n"])
        except ValueError:
            raise LookupError("no such decision") from None
        record = watcher.label(request.match_info["id"], n, body["label"])
        return _json(records.view(record, watcher.settings["sensitivity"], watcher.frame_s))

    @routes.delete("/api/prints/{id}")
    async def delete(request):
        watcher.delete(request.match_info["id"])
        return _json({"ok": True})

    @routes.post("/api/ack")
    async def ack(request):
        watcher.ack()
        return _json(watcher.status())

    @routes.post("/api/mute")
    async def mute(request):
        watcher.mute()
        return _json(watcher.status())

    @routes.get("/api/settings")
    async def get_settings(request):
        return _json(watcher.settings)

    @routes.put("/api/settings")
    async def put_settings(request):
        return _json(watcher.update_settings(await _body(request)))

    @routes.post("/api/notify/test")
    async def notify_test(request):
        # Optional {"urls": [...]}: try URLs before saving them
        urls = watcher.settings["notify"]["urls"]
        if request.can_read_body:
            body = await _body(request)
            if isinstance(body, dict) and "urls" in body:
                urls = settings_mod.merge(watcher.settings, {"notify": {"urls": body["urls"]}})["notify"]["urls"]
        try:
            await notify_send(urls, "Failure detection test",
                              "Notifications from q2-offload's failure detection reach you.")
        except NotifyError as exc:
            return _json({"ok": False, "error": str(exc)})
        except Exception as exc:  # Apprise can raise anything for a malformed URL
            log.warning("test notification failed: %s", exc)
            return _json({"ok": False, "error": str(exc) or type(exc).__name__})
        return _json({"ok": True})

    @routes.get("/internal/frames/{seq}.jpg")
    async def internal_frame(request):
        try:
            jpeg = watcher.frames.get(int(request.match_info["seq"]))
        except ValueError:
            jpeg = None
        if jpeg is None:
            return _error(404, "frame gone")
        return web.Response(body=jpeg, content_type="image/jpeg")

    app = web.Application(middlewares=[errors], client_max_size=64 * 1024)
    app.add_routes(routes)
    return app
