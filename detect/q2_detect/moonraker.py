"""Moonraker over its websocket (JSON-RPC): print state, the webcam, and pausing the print."""
from __future__ import annotations

import asyncio
import itertools
import json
import logging
import urllib.parse

import aiohttp

from . import __version__

log = logging.getLogger(__name__)

RECONNECT_S = (1, 2, 5, 10, 30)
CALL_TIMEOUT_S = 10
SUBSCRIPTION = {"print_stats": ["state", "filename"], "virtual_sdcard": ["progress"]}


class MoonrakerError(Exception):
    pass


class Moonraker:
    """Keeps a connection open and calls `on_change()` whenever the printer state changes."""

    def __init__(self, url: str, session: aiohttp.ClientSession, on_change):
        self.url = url
        self.session = session
        self.on_change = on_change
        self.ws: aiohttp.ClientWebSocketResponse | None = None
        self.ready = False
        self.state = "offline"
        self.filename = ""
        self.progress = 0.0
        self.webcam: dict | None = None
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}

    async def run(self) -> None:
        failures = 0
        while True:
            try:
                async with self.session.ws_connect(self.url, heartbeat=30) as ws:
                    self.ws = ws
                    failures = 0
                    await self._listen(ws)
            except (aiohttp.ClientError, OSError, asyncio.TimeoutError) as exc:
                log.info("Moonraker not reachable (%s)", exc)
            self._disconnected()
            await asyncio.sleep(RECONNECT_S[min(failures, len(RECONNECT_S) - 1)])
            failures += 1

    async def _listen(self, ws) -> None:
        startup = asyncio.ensure_future(self._startup())
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                try:
                    self._dispatch(json.loads(msg.data))
                except (ValueError, KeyError, IndexError, TypeError) as exc:
                    log.warning("unexpected Moonraker message: %s", exc)
        finally:
            startup.cancel()

    async def _startup(self) -> None:
        try:
            await self.call("server.connection.identify", {
                "client_name": "q2-detect", "version": __version__, "type": "agent",
                "url": "https://github.com/cedbossneo/q2-offload"})
            await self._refresh_webcam()
            info = await self.call("server.info")
            if info.get("klippy_state") == "ready":
                await self._subscribe()
        except (MoonrakerError, asyncio.TimeoutError) as exc:
            log.warning("Moonraker startup: %s", exc)

    async def _subscribe(self) -> None:
        result = await self.call("printer.objects.subscribe", {"objects": SUBSCRIPTION})
        self.ready = True
        self._apply(result.get("status", {}))

    async def _refresh_webcam(self) -> None:
        webcams = (await self.call("server.webcams.list")).get("webcams", [])
        enabled = [w for w in webcams if w.get("enabled", True) and w.get("snapshot_url")]
        self.webcam = enabled[0] if enabled else None
        self.on_change()

    def _dispatch(self, msg: dict) -> None:
        if "id" in msg:
            future = self._pending.pop(msg["id"], None)
            if future and not future.done():
                if "error" in msg:
                    future.set_exception(MoonrakerError(msg["error"].get("message", str(msg["error"]))))
                else:
                    future.set_result(msg.get("result"))
            return
        method = msg.get("method")
        if method == "notify_status_update":
            self._apply(msg["params"][0])
        elif method == "notify_klippy_ready":
            asyncio.ensure_future(self._guard(self._subscribe()))
        elif method in ("notify_klippy_disconnected", "notify_klippy_shutdown"):
            self.ready = False
            self.state = "offline"
            self.on_change()
        elif method == "notify_webcams_changed":
            asyncio.ensure_future(self._guard(self._refresh_webcam()))

    async def _guard(self, coro) -> None:
        try:
            await coro
        except (MoonrakerError, asyncio.TimeoutError) as exc:
            log.warning("Moonraker: %s", exc)

    def _apply(self, status: dict) -> None:
        stats = status.get("print_stats", {})
        self.state = stats.get("state", self.state)
        self.filename = stats.get("filename", self.filename) or ""
        self.progress = status.get("virtual_sdcard", {}).get("progress", self.progress)
        self.on_change()

    def _disconnected(self) -> None:
        self.ws = None
        self.ready = False
        self.state = "offline"
        for future in self._pending.values():
            if not future.done():
                future.set_exception(MoonrakerError("Moonraker connection lost"))
        self._pending.clear()
        self.on_change()

    async def call(self, method: str, params: dict | None = None, timeout: float = CALL_TIMEOUT_S):
        if self.ws is None or self.ws.closed:
            raise MoonrakerError("not connected to Moonraker")
        msg_id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._pending[msg_id] = future
        await self.ws.send_str(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}, "id": msg_id}))
        try:
            return await asyncio.wait_for(future, timeout)
        finally:
            self._pending.pop(msg_id, None)

    async def pause(self) -> None:
        """PAUSE runs once the G-code queue reaches it (after a running macro), hence the long wait."""
        await self.call("printer.print.pause", timeout=600)

    async def console(self, message: str) -> None:
        """A line in the Mainsail / Fluidd console (and HelixScreen's notifications)."""
        text = message.replace('"', "'")
        await self.call("printer.gcode.script", {"script": f'RESPOND TYPE=error MSG="{text}"'}, timeout=600)

    def camera(self) -> dict | None:
        """The first enabled webcam, its relative URLs made absolute against this host's nginx."""
        if not self.webcam:
            return None
        resolve = lambda url: urllib.parse.urljoin("http://127.0.0.1/", url) if url else None  # noqa: E731
        return {
            "name": self.webcam.get("name"),
            "stream_url": self.webcam.get("stream_url") or None,
            "snapshot_url": resolve(self.webcam.get("snapshot_url")),
        }
