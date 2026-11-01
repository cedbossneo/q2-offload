"""The camera frames: fetching one, Obico's boxes in frame fractions, thumbnails and the
picture attached to a notification."""
from __future__ import annotations

import asyncio
import io

import aiohttp
from PIL import Image, ImageDraw

from . import obico

FETCH_TIMEOUT_S = 5
THUMB_WIDTH = 640
BOX_COLOR = (248, 81, 73)


class CameraError(Exception):
    pass


async def fetch(session: aiohttp.ClientSession, url: str) -> bytes:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT_S)) as resp:
            if resp.status != 200:
                raise CameraError(f"camera answered HTTP {resp.status}")
            data = await resp.read()
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise CameraError(f"camera not reachable: {exc or type(exc).__name__}") from exc
    if not data.startswith(b"\xff\xd8"):
        raise CameraError("camera did not send a JPEG")
    return data


def size(jpeg: bytes) -> tuple[int, int]:
    with Image.open(io.BytesIO(jpeg)) as img:
        return img.size


def boxes(detections: list, width: int, height: int) -> list[list[float]]:
    """Obico's [label, confidence, (x, y, w, h)] in pixels to [confidence, x, y, w, h] in frame
    fractions, keeping the boxes worth drawing. Obico scales the box height by the frame width
    (obico-server ml_api/lib/onnx.py), so the width undoes it."""
    out = []
    for _, conf, (x, y, w, h) in detections:
        if conf > obico.VISUALIZATION_THRESH:
            out.append([round(conf, 3), round(x / width, 4), round(y / height, 4),
                        round(w / width, 4), round(h / width, 4)])
    return out


def thumbnail(jpeg: bytes) -> bytes:
    with Image.open(io.BytesIO(jpeg)) as img:
        img = img.convert("RGB")
        if img.width > THUMB_WIDTH:
            img = img.resize((THUMB_WIDTH, round(img.height * THUMB_WIDTH / img.width)), Image.Resampling.BILINEAR)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=80)
        return out.getvalue()


def annotated(jpeg: bytes, frac_boxes: list) -> bytes:
    """The frame with its boxes drawn, as sent with a notification."""
    with Image.open(io.BytesIO(jpeg)) as img:
        img = img.convert("RGB")
        draw = ImageDraw.Draw(img)
        line = max(2, img.width // 320)
        for conf, x, y, w, h in frac_boxes:
            left, top = (x - w / 2) * img.width, (y - h / 2) * img.height
            draw.rectangle([left, top, left + w * img.width, top + h * img.height], outline=BOX_COLOR, width=line)
            draw.text((left + line, max(0, top - 12)), f"{conf:.2f}", fill=BOX_COLOR)
        out = io.BytesIO()
        img.save(out, "JPEG", quality=85)
        return out.getvalue()
