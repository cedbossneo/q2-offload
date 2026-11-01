"""Everything kept on disk, under one data directory:

    settings.json           the page's settings
    baseline.json           this printer's long-term mean (Obico carries it across prints)
    prints/<id>/print.json  one print, rewritten after every frame
    prints/<id>/tNNN.jpg    timeline frames, every 10 minutes and at the end
    prints/<id>/dNNN.jpg    the frame behind each decision

Writes go to a temporary file renamed over the old one, so a crash never leaves half a file.
"""
from __future__ import annotations

import dataclasses
import json
import logging
import os
import pathlib
import shutil

from . import obico, records, settings

log = logging.getLogger(__name__)


def _write(path: pathlib.Path, data: bytes) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _read_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        log.warning("ignoring unreadable %s: %s", path, exc)
        return None


class Store:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.prints_dir = root / "prints"
        self.prints_dir.mkdir(parents=True, exist_ok=True)

    # settings and baseline

    def load_settings(self) -> dict:
        return settings.load(_read_json(self.root / "settings.json"))

    def save_settings(self, value: dict) -> None:
        _write(self.root / "settings.json", json.dumps(value, indent=1).encode())

    def load_baseline(self) -> obico.Baseline:
        raw = _read_json(self.root / "baseline.json") or {}
        try:
            return obico.Baseline(int(raw.get("lifetime", 0)), float(raw.get("long", 0.0)))
        except (TypeError, ValueError):
            return obico.Baseline()

    def save_baseline(self, baseline: obico.Baseline) -> None:
        _write(self.root / "baseline.json", json.dumps(dataclasses.asdict(baseline)).encode())

    # prints

    def _dir(self, print_id: str) -> pathlib.Path:
        if not records.ID_PATTERN.match(print_id):
            raise LookupError(f"no print {print_id}")
        return self.prints_dir / print_id

    def save_print(self, record: records.Print) -> None:
        folder = self._dir(record.id)
        folder.mkdir(exist_ok=True)
        _write(folder / "print.json", json.dumps(records.to_json(record), separators=(",", ":")).encode())

    def load_print(self, print_id: str) -> records.Print:
        raw = _read_json(self._dir(print_id) / "print.json")
        if raw is None:
            raise LookupError(f"no print {print_id}")
        return records.from_json(raw)

    def print_ids(self) -> list[str]:
        """Newest first (ids start with the start time)."""
        return sorted((p.name for p in self.prints_dir.iterdir() if records.ID_PATTERN.match(p.name)), reverse=True)

    def load_prints(self) -> list[records.Print]:
        out = []
        for print_id in self.print_ids():
            try:
                out.append(self.load_print(print_id))
            except (LookupError, KeyError, TypeError, ValueError) as exc:
                log.warning("skipping print %s: %s", print_id, exc)
        return out

    def save_image(self, print_id: str, name: str, jpeg: bytes) -> None:
        _write(self._dir(print_id) / name, jpeg)

    def image_path(self, print_id: str, name: str) -> pathlib.Path:
        if not records.FILE_PATTERN.match(name):
            raise LookupError(f"no file {name}")
        path = self._dir(print_id) / name
        if not path.is_file():
            raise LookupError(f"no file {name}")
        return path

    def delete_print(self, print_id: str) -> None:
        shutil.rmtree(self._dir(print_id), ignore_errors=True)

    def prune(self, keep: int, current: str | None) -> list[str]:
        """Forget the oldest finished prints beyond `keep`; never the current one."""
        dropped = [i for i in self.print_ids() if i != current][max(0, keep - (1 if current else 0)):]
        for print_id in dropped:
            self.delete_print(print_id)
        return dropped
