# q2-offload: pressure advance calibration of a spool created from an NFC tag.
#
# Happy Hare calls _MMU_EVENT EVENT=spool_created (patch 0006) when a scanned tag creates a
# Spoolman spool, and q2_pa_calibrate.cfg forwards it here. If the spool's filament has no
# pressure advance yet, this component works out the settings the slicer prints it with (the
# same OrcaSlicer preset scripts/orca-spool-presets.py generates: the filament's temperature,
# from SpoolmanDB when the tag matched it (patch 0007), and its flow ratio) and asks Klipper to
# offer a calibration (_SPOOL_PA_OFFER). After a valid measurement, Klipper calls q2_pa_store and
# the value goes to the filament in Spoolman, where the next spool of that filament and the
# OrcaSlicer presets pick it up.
#
# Installed as a symlink into Moonraker's components; enabled by a [q2_calibration] section.
#
# This file may be distributed under the terms of the GNU GPLv3 license.
from __future__ import annotations

import importlib.util
import json
import logging
import pathlib
import re
from typing import Any, Dict, Optional

REPO = pathlib.Path(__file__).resolve().parents[2]
PA_FIELD = "orca_pressure_advance"
PA_ENABLE_FIELD = "orca_enable_pressure_advance"
NEW_FIELDS = {PA_FIELD: "Orca pressure advance", PA_ENABLE_FIELD: "Orca enable pressure advance"}
DEFAULT_FLOW_RATIO = 1.0
PA_DECIMALS = 4


def load_presets_module(repo: pathlib.Path = REPO):
    """scripts/orca-spool-presets.py, which knows how a spool's OrcaSlicer preset is built."""
    spec = importlib.util.spec_from_file_location("q2_orca_spool_presets",
                                                  repo / "scripts" / "orca-spool-presets.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def orca_ref(repo: pathlib.Path = REPO) -> str:
    match = re.search(r'^ORCA_PROFILES_REF=(\S+)', (repo / "VERSIONS").read_text(), re.M)
    if not match:
        raise KeyError("ORCA_PROFILES_REF missing from VERSIONS")
    return match.group(1)


def first_number(values: Any) -> Optional[float]:
    """An OrcaSlicer option (a per-extruder list of strings) as a number."""
    if isinstance(values, list):
        values = values[0] if values else None
    try:
        return float(values)
    except (TypeError, ValueError):
        return None


def print_settings(spool: Dict[str, Any], presets, load) -> Dict[str, Any]:
    """Temperature and flow ratio of the preset the slicer prints this spool with, and the
    filament's pressure advance if it has one."""
    filament = spool["filament"]
    preset = presets.build_preset(spool, presets.flatten(presets.base_name(filament), load))
    temperature = first_number(preset.get("nozzle_temperature"))
    flow_ratio = first_number(preset.get("filament_flow_ratio"))
    return {
        "temperature": int(round(temperature)) if temperature else None,
        "flow_ratio": flow_ratio if flow_ratio and flow_ratio > 0 else DEFAULT_FLOW_RATIO,
        "pressure_advance": first_number(presets.extra_value(filament, PA_FIELD)),
        "material": str(filament.get("material") or ""),
    }


def quote(text: str) -> str:
    """A G-code parameter value: Klipper ends a command at '#', ';' or '*' (comments) and
    splits on quotes, so those go, with newlines."""
    return re.sub(r'["\'\n\r#;*]', '', text).strip()


def spool_name(spool: Dict[str, Any]) -> str:
    filament = spool["filament"]
    vendor = (filament.get("vendor") or {}).get("name", "")
    parts = [vendor, filament.get("name") or filament.get("material") or "filament"]
    return quote(" ".join(part for part in parts if part)) or f"spool {spool['id']}"


class Q2Calibration:
    def __init__(self, config) -> None:
        self.server = config.get_server()
        self.http = self.server.lookup_component("http_client")
        self.klippy = self.server.lookup_component("klippy_apis")
        data_path = pathlib.Path(self.server.get_app_args()["data_path"])
        self.cache_dir = data_path / "web" / ".spool-profile-cache"
        self.presets = load_presets_module()
        self.server.register_remote_method("q2_pa_spool_created", self._spool_created)
        self.server.register_remote_method("q2_pa_store", self._store)
        self.server.register_event_handler("server:klippy_ready", self._klippy_ready)

    async def _klippy_ready(self) -> None:
        # _SPOOL_PA_VARS only offers calibrations once this component is there to answer
        try:
            await self.klippy.run_gcode("SET_GCODE_VARIABLE MACRO=_SPOOL_PA_VARS VARIABLE=enabled VALUE=True")
        except Exception as e:
            logging.info(f"q2_calibration: calibration offers stay off ({e})")

    def _spoolman_url(self) -> str:
        return self.server.lookup_component("spoolman").spoolman_url

    async def _console(self, msg: str) -> None:
        logging.info(f"q2_calibration: {msg}")
        await self.klippy.run_gcode(f"RESPOND PREFIX=q2 MSG=\"{quote(msg)}\"")

    async def _get_spool(self, spool_id: int) -> Dict[str, Any]:
        resp = await self.http.get(f"{self._spoolman_url()}/v1/spool/{spool_id}")
        if resp.has_error():
            raise RuntimeError(f"Spoolman: spool {spool_id}: {resp.error}")
        return resp.json()

    def _settings(self, spool: Dict[str, Any]) -> Dict[str, Any]:
        # Blocking (may download OrcaSlicer profiles once): run off the event loop
        return print_settings(spool, self.presets, self.presets.profile_loader(orca_ref(), self.cache_dir))

    async def _spool_created(self, spool_id: int, gate: int = -1) -> None:
        self.server.get_event_loop().create_task(self._offer(int(spool_id), int(gate)))

    async def _offer(self, spool_id: int, gate: int) -> None:
        try:
            spool = await self._get_spool(spool_id)
            settings = await self.server.get_event_loop().run_in_thread(self._settings, spool)
        except Exception as e:
            await self._console(f"spool {spool_id}: no pressure advance calibration ({e})")
            return
        name = spool_name(spool)
        if settings["pressure_advance"] is not None:
            await self._console(f"{name}: pressure advance {settings['pressure_advance']} "
                                "already measured for this filament")
            return
        if not settings["temperature"]:
            await self._console(f"{name}: no nozzle temperature in Spoolman, calibration skipped")
            return
        await self.klippy.run_gcode(
            f"_SPOOL_PA_OFFER SPOOL={spool_id} FILAMENT={spool['filament']['id']} GATE={gate} TEMP={settings['temperature']} "
            f"FLOW={settings['flow_ratio']:.3f} MATERIAL=\"{quote(settings['material'])}\" "
            f"NAME=\"{name}\"")

    async def _store(self, spool_id: int, pa: float) -> None:
        self.server.get_event_loop().create_task(self._save(int(spool_id), float(pa)))

    async def _ensure_fields(self) -> None:
        url = f"{self._spoolman_url()}/v1/field/filament"
        resp = await self.http.get(url)
        existing = {f.get("key") for f in resp.json()} if not resp.has_error() else set()
        for key, label in NEW_FIELDS.items():
            if key not in existing:
                created = await self.http.post(f"{url}/{key}", body={"name": label, "field_type": "text"})
                if created.has_error():
                    raise RuntimeError(f"Spoolman: field {key}: {created.error}")

    async def _save(self, spool_id: int, pa: float) -> None:
        try:
            spool = await self._get_spool(spool_id)
            await self._ensure_fields()
            value = f"{pa:.{PA_DECIMALS}f}"
            body = {"extra": {PA_FIELD: json.dumps(value), PA_ENABLE_FIELD: json.dumps("1")}}
            filament_id = spool["filament"]["id"]
            resp = await self.http.request("PATCH", f"{self._spoolman_url()}/v1/filament/{filament_id}", body=body)
            if resp.has_error():
                raise RuntimeError(f"Spoolman: filament {filament_id}: {resp.error}")
        except Exception as e:
            logging.info(f"q2_calibration: spool {spool_id}: pressure advance {pa} not saved ({e})")
            await self._notice("Pressure advance not saved",
                               f"Spool {spool_id}: {pa:.{PA_DECIMALS}f} could not be saved in Spoolman ({e})", error=True)
            return
        await self._notice("Pressure advance saved",
                           f"{spool_name(spool)}: pressure advance {value} saved in Spoolman. "
                           "OrcaSlicer presets follow within a minute")

    async def _notice(self, title: str, msg: str, error: bool = False) -> None:
        """The result dialog and notification (_SPOOL_PA_NOTICE in q2_pa_calibrate.cfg)."""
        await self.klippy.run_gcode(f"_SPOOL_PA_NOTICE ERROR={int(error)} TITLE=\"{quote(title)}\" MSG=\"{quote(msg)}\"")


def load_component(config) -> Q2Calibration:
    return Q2Calibration(config)
