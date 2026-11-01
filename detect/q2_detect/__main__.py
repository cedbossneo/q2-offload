"""Run the failure detection service: python -m q2_detect --data <dir> [options]."""
from __future__ import annotations

import argparse
import asyncio
import logging
import pathlib

import aiohttp
from aiohttp import web

from . import __version__, api, obico
from .mlapi import MlApi
from .moonraker import Moonraker
from .store import Store
from .watcher import Watcher

log = logging.getLogger("q2_detect")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="q2_detect", description=__doc__)
    parser.add_argument("--data", type=pathlib.Path, required=True, help="where settings and prints are kept")
    parser.add_argument("--moonraker", default="ws://127.0.0.1:7125/websocket")
    parser.add_argument("--ml-api", default="http://127.0.0.1:3333")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7130)
    parser.add_argument("--frame-base", help="this service as Obico's ML API reaches it (default: http://127.0.0.1:PORT)")
    parser.add_argument("--frame-s", type=float, default=obico.FRAME_S,
                        help="seconds between frames (Obico's rules are tuned for 10)")
    return parser.parse_args(argv)


async def serve(args: argparse.Namespace) -> None:
    async with aiohttp.ClientSession() as session:
        store = Store(args.data)
        watcher = Watcher(store, session, MlApi(args.ml_api, session),
                          args.frame_base or f"http://127.0.0.1:{args.port}", frame_s=args.frame_s)
        watcher.printer = Moonraker(args.moonraker, session, watcher.on_printer_change)
        runner = web.AppRunner(api.build(watcher), access_log=None)
        await runner.setup()
        await web.TCPSite(runner, args.host, args.port).start()
        log.info("q2-detect %s on http://%s:%d, data in %s", __version__, args.host, args.port, args.data)
        try:
            await asyncio.gather(watcher.printer.run(), watcher.run())
        finally:
            await runner.cleanup()


def main(argv=None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    asyncio.run(serve(parse_args(argv)))


if __name__ == "__main__":
    main()
