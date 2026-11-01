"""Obico's ML API (obico-server ml_api, run by the installer as the obico-ml-api container)."""
from __future__ import annotations

import asyncio

import aiohttp

DETECT_TIMEOUT_S = 60


class MlApiError(Exception):
    pass


class MlApi:
    def __init__(self, base: str, session: aiohttp.ClientSession):
        self.base = base.rstrip("/")
        self.session = session

    async def detect(self, image_url: str) -> list:
        """Obico's detections for the JPEG it fetches at image_url: [label, confidence, (x, y, w, h)]."""
        try:
            async with self.session.get(f"{self.base}/p/", params={"img": image_url},
                                        timeout=aiohttp.ClientTimeout(total=DETECT_TIMEOUT_S)) as resp:
                body = await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as exc:
            raise MlApiError(f"Obico's ML API not reachable: {exc or type(exc).__name__}") from exc
        if resp.status != 200 or not isinstance(body, dict) or not isinstance(body.get("detections"), list):
            message = body.get("message") if isinstance(body, dict) else None
            raise MlApiError(f"Obico's ML API answered HTTP {resp.status}{': ' + str(message)[:200] if message else ''}")
        return body["detections"]

    async def healthy(self) -> bool:
        try:
            async with self.session.get(f"{self.base}/hc/", timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return resp.status == 200 and (await resp.text()).strip() == "ok"
        except (aiohttp.ClientError, asyncio.TimeoutError):
            return False
