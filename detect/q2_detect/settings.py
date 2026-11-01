"""User settings: defaults, validation of a partial update, and the JSON shape the page edits."""
from __future__ import annotations

import copy

DEFAULTS = {
    "enabled": True,
    "mode": "observe",
    "sensitivity": 1.0,
    "notify": {"urls": [], "on_warning": True, "on_pause": True, "attach_image": True},
    "keep_prints": 50,
}
MODES = ("observe", "pause")
SENSITIVITY_RANGE = (0.5, 2.0)
KEEP_PRINTS_RANGE = (1, 500)
URLS_MAX = 10
URL_MAX_LEN = 1000


def _bool(value, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be true or false")
    return value


def _number(value, name: str, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
        raise ValueError(f"{name} must be a number from {low} to {high}")
    return value


def _urls(value) -> list[str]:
    if not isinstance(value, list) or len(value) > URLS_MAX:
        raise ValueError(f"notify.urls must be a list of at most {URLS_MAX} Apprise URLs")
    for url in value:
        if not isinstance(url, str) or "://" not in url or len(url) > URL_MAX_LEN:
            raise ValueError("each notification URL looks like scheme://... (an Apprise URL)")
    return [url.strip() for url in value]


def merge(current: dict, patch: dict) -> dict:
    """current with patch applied, every value checked. Raises ValueError naming the bad field."""
    if not isinstance(patch, dict):
        raise ValueError("settings must be a JSON object")
    unknown = set(patch) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"unknown setting: {sorted(unknown)[0]}")
    out = copy.deepcopy(current)
    if "enabled" in patch:
        out["enabled"] = _bool(patch["enabled"], "enabled")
    if "mode" in patch:
        if patch["mode"] not in MODES:
            raise ValueError("mode is observe or pause")
        out["mode"] = patch["mode"]
    if "sensitivity" in patch:
        out["sensitivity"] = float(_number(patch["sensitivity"], "sensitivity", *SENSITIVITY_RANGE))
    if "keep_prints" in patch:
        out["keep_prints"] = int(_number(patch["keep_prints"], "keep_prints", *KEEP_PRINTS_RANGE))
    if "notify" in patch:
        notify = patch["notify"]
        if not isinstance(notify, dict) or set(notify) - set(DEFAULTS["notify"]):
            raise ValueError("notify takes urls, on_warning, on_pause and attach_image")
        for key in ("on_warning", "on_pause", "attach_image"):
            if key in notify:
                out["notify"][key] = _bool(notify[key], f"notify.{key}")
        if "urls" in notify:
            out["notify"]["urls"] = _urls(notify["urls"])
    return out


def load(raw) -> dict:
    """Stored settings over the defaults; a stored value that no longer validates is dropped."""
    out = copy.deepcopy(DEFAULTS)
    if not isinstance(raw, dict):
        return out
    for key, value in raw.items():
        try:
            out = merge(out, {key: value})
        except ValueError:
            continue
    return out
