"""Notifications through Apprise, the library behind Moonraker's [notifier] (ntfy, Telegram,
Discord, Pushover, Home Assistant, email...). Apprise blocks, so it runs in a thread."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile

log = logging.getLogger(__name__)


class NotifyError(Exception):
    pass


def _send(urls: list[str], title: str, body: str, image: bytes | None) -> None:
    import apprise  # imported here: only the service needs it, not the tests

    sender = apprise.Apprise()
    for url in urls:
        if not sender.add(url):
            raise NotifyError(f"not an Apprise URL Apprise knows: {url.split('://', 1)[0]}://...")
    path = None
    try:
        if image:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp.write(image)
                path = tmp.name
        if not sender.notify(title=title, body=body, attach=path):
            raise NotifyError("Apprise could not deliver to at least one URL (see the q2-detect log)")
    finally:
        if path:
            os.unlink(path)


async def send(urls: list[str], title: str, body: str, image: bytes | None = None) -> None:
    if not urls:
        raise NotifyError("no notification URL set")
    await asyncio.get_running_loop().run_in_executor(None, _send, urls, title, body, image)
