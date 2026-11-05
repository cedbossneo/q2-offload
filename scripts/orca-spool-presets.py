#!/usr/bin/env python3
"""Generate one OrcaSlicer filament preset per Spoolman spool, so the slicer can tell two spools
of the same material apart when it syncs the Box.

OrcaSlicer only matches a slot to a "base" preset by filament_id, and a preset with `inherits`
takes the id of its parent. So each preset here has no parent: it holds the flattened settings of
the Generic preset of its material and its own id, QD_1_0_<10000 + spool id>, which is the id the
"qidi" printer agent builds from filament_slot (host/extras/qidi_box_compat.py).

Writes index.json (every preset and a hash of the content), which the "Q2 Spool Presets"
OrcaSlicer plugin downloads. The file only changes when its content does.

Usage: orca-spool-presets.py --spoolman URL --orca-ref TAG --out DIR [--cache DIR] [--spool ID ...]
"""
import argparse
import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

SPOOL_ID_OFFSET = 10000
SERIES_ID = 1  # QidiPrinterAgent::infer_series_id for a Q2
LIBRARY = "https://raw.githubusercontent.com/OrcaSlicer/OrcaSlicer/%s/resources/profiles/OrcaFilamentLibrary/filament/%s.json"
PRESET_VERSION = "2.5.0.0"  # Orca refuses to load a preset without a version
BASE_BY_MATERIAL = {"PLA+": "PLA", "ABS+": "ABS"}


def fetch_json(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        return json.load(response)


def flatten(name, load):
    """The settings of a preset with its `inherits` chain resolved, parents first."""
    profile = load(name)
    parent = profile.get("inherits")
    return {**(flatten(parent, load) if parent else {}), **profile}


def base_name(filament):
    """The preset named in Spoolman (orca_base_preset), else the Generic one of the material."""
    chosen = extra_value(filament, "orca_base_preset")
    return chosen or "Generic %s @System" % BASE_BY_MATERIAL.get(filament["material"], filament["material"])


def extra_value(filament, key):
    """Spoolman stores extra fields as JSON text."""
    raw = (filament.get("extra") or {}).get(key)
    if raw in (None, ""):
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def option_values(value):
    """OrcaSlicer's serialized form: per-extruder list of strings, booleans as 1 and 0."""
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, bool):
        return ["1" if value else "0"]
    text = str(value)
    if text in ("true", "false"):
        return ["1" if text == "true" else "0"]
    if text.startswith("nil,"):
        return text.split(",")
    return [text.strip('"')]


def spoolman_overrides(filament):
    """Every orca_<option> extra field, as OrcaSlicer's per-extruder list of strings."""
    overrides = {}
    for key in (filament.get("extra") or {}):
        if key.startswith("orca_") and key != "orca_base_preset":
            value = extra_value(filament, key)
            if value is None:
                continue
            overrides[key[len("orca_"):]] = option_values(value)
    return overrides


def preset_name(spool):
    filament = spool["filament"]
    vendor = (filament.get("vendor") or {}).get("name", "")
    parts = [vendor, filament.get("name") or filament.get("material") or "Filament"]
    return "#%d %s" % (spool["id"], " ".join(part for part in parts if part))


def filament_id(spool_id):
    return "QD_%d_0_%d" % (SERIES_ID, SPOOL_ID_OFFSET + spool_id)


def build_preset(spool, base):
    filament = spool["filament"]
    preset = {key: value for key, value in base.items() if key not in ("setting_id", "inherits", "type")}
    name = preset_name(spool)
    preset.update({
        "name": name,
        "from": "User",
        "inherits": "",
        "instantiation": "true",
        "version": PRESET_VERSION,
        "filament_id": filament_id(spool["id"]),
        "filament_settings_id": [name],
        "filament_type": [filament["material"]],
    })
    vendor = (filament.get("vendor") or {}).get("name")
    if vendor:
        preset["filament_vendor"] = [vendor]
    if filament.get("color_hex"):
        color = "#" + filament["color_hex"].lstrip("#").upper()[:6]
        # filament_colour belongs to the project, and Orca rejects a local bundle that has it
        preset["default_filament_colour"] = [color]
    for field, keys in (("density", ["filament_density"]), ("diameter", ["filament_diameter"]),
                        ("settings_extruder_temp", ["nozzle_temperature", "nozzle_temperature_initial_layer"])):
        if filament.get(field):
            for key in keys:
                preset[key] = [str(filament[field])]
    # Tuned values win over the generic Spoolman columns
    preset.update(spoolman_overrides(filament))
    return preset


def library_paths(name):
    """Where a profile can live in OrcaFilamentLibrary: top level, base/ or a vendor folder."""
    quoted = urllib.parse.quote(name)
    return [quoted, "base/" + quoted, urllib.parse.quote(name.split(" ")[0]) + "/" + quoted]


def profile_loader(ref, cache_dir):
    memory = {}

    def load(name):
        if name in memory:
            return memory[name]
        cached = cache_dir / ref / (name + ".json") if cache_dir else None
        if cached and cached.exists():
            memory[name] = json.loads(cached.read_text())
            return memory[name]
        for path in library_paths(name):
            try:
                memory[name] = fetch_json(LIBRARY % (ref, path))
                break
            except urllib.error.HTTPError:
                continue
        else:
            raise KeyError("profile not found: %s" % name)
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(json.dumps(memory[name]))
        return memory[name]
    return load


def file_name(preset):
    return preset["name"].replace("/", "-") + ".json"


def serialize(preset):
    return json.dumps(preset, indent=4, ensure_ascii=False, sort_keys=True) + "\n"


def write_if_changed(path, text):
    if path.exists() and path.read_text() == text:
        return
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text)
    temporary.replace(path)


MMU_FIELDS = "gate_spool_id,gate_color,gate_material,gate_status,gate,filament,drying"
ENVIRONMENT = "temperature_sensor%20unit0_Env=temperature&aht10%20unit0_Env=humidity"


def read_printer(moonraker, spools):
    """The Box as the slicer's page shows it. An offline printer just shows nothing."""
    url = "%s/printer/objects/query?mmu=%s&%s" % (moonraker.rstrip("/"), MMU_FIELDS, ENVIRONMENT)
    try:
        status = fetch_json(url)["result"]["status"]
        return box_from(status), gates_from(status["mmu"], spools)
    except (OSError, KeyError, ValueError):
        return {}, []


def box_from(status):
    mmu = status["mmu"]
    drying = mmu.get("drying") or []
    return {
        "temperature": (status.get("temperature_sensor unit0_Env") or {}).get("temperature"),
        "humidity": (status.get("aht10 unit0_Env") or {}).get("humidity"),
        "drying": any(drying),
        "loaded_slot": mmu["gate"] + 1 if mmu.get("filament") == "Loaded" and mmu.get("gate", -1) >= 0 else None,
    }


def spool_details(spool):
    filament = spool["filament"]
    initial = spool.get("initial_weight") or filament.get("weight")
    remaining = spool.get("remaining_weight")
    pressure_advance = extra_value(filament, "orca_pressure_advance")
    temperature = extra_value(filament, "orca_nozzle_temperature") or filament.get("settings_extruder_temp")
    return {
        "spool_id": spool["id"],
        "vendor": (filament.get("vendor") or {}).get("name") or "",
        "filament": filament.get("name") or filament.get("material") or "",
        "remaining_g": round(remaining) if remaining is not None else None,
        "percent": round(100 * remaining / initial) if remaining is not None and initial else None,
        "nozzle": temperature,
        "pressure_advance": pressure_advance,
        "last_used": (spool.get("last_used") or "")[:10],
    }


def gates_from(mmu, spools=()):
    by_id = {spool["id"]: spool for spool in spools}
    gates = []
    for index, status in enumerate(mmu["gate_status"]):
        spool = by_id.get(mmu["gate_spool_id"][index])
        gate = {
            "slot": index + 1,
            "empty": status == 0,
            "color": (mmu["gate_color"][index] or "FFFFFF").lstrip("#").upper()[:6],
            "material": mmu["gate_material"][index] if status != 0 else "",
        }
        if spool and status != 0:
            gate.update(spool_details(spool))
        gates.append(gate)
    return gates


def publish(presets, out, box=None, gates=(), spoolman=""):
    """Write index.json with every preset inside: OrcaSlicer asks the user to allow each URL a
    plugin opens, so one file means one question."""
    out.mkdir(parents=True, exist_ok=True)
    files = {file_name(preset): serialize(preset) for preset in presets}
    for old in out.glob("*.json"):
        if old.name != "index.json":
            old.unlink()
    digest = hashlib.sha256("".join(name + files[name] for name in sorted(files)).encode()).hexdigest()
    index = {"hash": digest, "box": box or {}, "gates": list(gates), "spoolman": spoolman, "files": files}
    write_if_changed(out / "index.json", json.dumps(index, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--spoolman", required=True)
    parser.add_argument("--orca-ref", required=True)
    parser.add_argument("--out", required=True, type=pathlib.Path)
    parser.add_argument("--cache", type=pathlib.Path)
    parser.add_argument("--moonraker", default="http://localhost:7125")
    parser.add_argument("--public-spoolman-port", type=int, default=7912)
    parser.add_argument("--spool", type=int, action="append")
    args = parser.parse_args()
    load = profile_loader(args.orca_ref, args.cache)
    spools = fetch_json(args.spoolman.rstrip("/") + "/api/v1/spool?allow_archived=false")
    presets, failed = [], 0
    for spool in spools:
        if args.spool and spool["id"] not in args.spool:
            continue
        try:
            presets.append(build_preset(spool, flatten(base_name(spool["filament"]), load)))
        except (KeyError, urllib.error.URLError) as error:
            print("spool #%d skipped: %s" % (spool["id"], error), file=sys.stderr)
            failed += 1
    # A Spoolman or network failure must not empty the slicer's list
    if presets or not failed:
        box, gates = read_printer(args.moonraker, spools)
        publish(presets, args.out, box, gates, args.public_spoolman_port)
    print("%d preset(s), %d failed" % (len(presets), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
