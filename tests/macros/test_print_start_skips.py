"""PRINT_START steps HelixScreen 1.1 can turn off for one print (SKIP_NOZZLE_CLEAN,
SKIP_BED_MESH), and that HelixScreen's PRINT_START analysis finds them: a port of
PrintStartAnalyzer::detect_operations / detect_skip_conditional (src/print/print_start_analyzer.cpp
and include/operation_patterns.h, HelixScreen v1.1.0).
Usage: python3 tests/macros/test_print_start_skips.py"""
import configparser
import pathlib
import re

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = ROOT / "config/klipper/gcode_macro_mmu.cfg"
PARAMS = {"BED": "60", "HOTEND": "220", "CHAMBER": "0", "INITIAL_TOOL": "0", "REFERENCED_TOOLS": "0",
          "TOOL_MATERIALS": "PLA"}
NO_MESH = {"profile_name": "", "profiles": {}}

# HelixScreen v1.1.0: (keyword, category, exact match), in its order, and the opt-out parameters
KEYWORDS = [("BED_MESH", "bed_mesh", False), ("AUTO_BED_LEVEL", "bed_mesh", False), ("G29", "bed_mesh", True),
            ("QUAD_GANTRY_LEVEL", "qgl", False), ("QGL", "qgl", False),
            ("Z_TILT_ADJUST", "z_tilt", False), ("Z_TILT", "z_tilt", False),
            ("CLEAN_NOZZLE", "nozzle_clean", False), ("NOZZLE_CLEAN", "nozzle_clean", False),
            ("NOZZLE_WIPE", "nozzle_clean", False), ("WIPE_NOZZLE", "nozzle_clean", False),
            ("BRUSH_NOZZLE", "nozzle_clean", False), ("NOZZLE_BRUSH", "nozzle_clean", False),
            ("PURGE", "purge", False), ("PRIME", "purge", False), ("INTRO_LINE", "purge", False),
            ("G28", "homing", True), ("SAFE_HOME", "homing", False)]
SKIPS = {"bed_mesh": ["SKIP_BED_MESH", "SKIP_MESH", "SKIP_BED_LEVELING", "NO_BED_MESH", "SKIP_LEVEL"],
         "z_tilt": ["SKIP_Z_TILT", "SKIP_TILT", "NO_Z_TILT", "SKIP_Z_TILT_ADJUST"],
         "nozzle_clean": ["SKIP_NOZZLE_CLEAN", "SKIP_CLEAN", "NO_CLEAN"],
         "purge": ["SKIP_PURGE", "SKIP_PRIME", "NO_PURGE", "NO_PRIME", "DISABLE_PRIMING"]}
LOOKBACK = 500


def macro():
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(CFG)
    return cfg["gcode_macro PRINT_START"]["gcode"]


def render(mesh=NO_MESH, **params):
    env = jinja2.Environment("{%", "%}", "{", "}", extensions=["jinja2.ext.do"])
    printer = {"configfile": {"settings": {"printer": {"max_accel": 7000.0}}}, "bed_mesh": mesh}
    out = env.from_string(macro()).render(printer=printer, params={**PARAMS, **params})
    lines = (line.split(";")[0].split("#")[0].strip() for line in out.splitlines())
    return [line for line in lines if line]


def category(cmd):
    for keyword, cat, exact in KEYWORDS:
        if (cmd.upper() == keyword) if exact else (keyword in cmd.upper()):
            return cat
    return None


def operations(gcode):
    ops = []
    for line in gcode.splitlines():
        text = line.strip()
        if not text or text[0] in "#;" or "{%" in line or text[0] == "{":
            continue
        cmd = re.split(r"[ \t{]", text, maxsplit=1)[0]
        if category(cmd) and cmd not in ops:
            ops.append(cmd)
    return ops


def skip_param(gcode, op):
    pos = gcode.find(op)
    context = gcode[max(0, pos - LOOKBACK):pos]
    for param in SKIPS.get(category(op), []):
        p = param.lower()
        if p in context.lower() and (re.search(r"\{%\s*if\s+.*" + p + r".*%\}", context, re.I)
                                     or re.search(r"\{%\s*set\s+\w+\s*=\s*params\." + p, context, re.I)):
            return param
    return None


def test_helixscreen_offers_nozzle_clean_and_bed_mesh():
    gcode = macro()
    found = {category(op): skip_param(gcode, op) for op in operations(gcode)}
    assert found["nozzle_clean"] == "SKIP_NOZZLE_CLEAN"
    assert found["bed_mesh"] == "SKIP_BED_MESH"


def test_every_bed_mesh_and_cleaning_step_follows_its_option():
    # One uncontrolled command of a category would make HelixScreen's option a lie
    gcode = macro()
    for op in operations(gcode):
        if category(op) in ("bed_mesh", "nozzle_clean"):
            assert skip_param(gcode, op), op


def test_default_print_start_cleans_and_probes():
    lines = render()
    assert "NOZZLE_WIPE HOTEND=220" in lines and lines.count("G28") == 2
    assert lines.index("BED_MESH_CALIBRATE ADAPTIVE=1 ADAPTIVE_MARGIN=10") < lines.index("BED_MESH_PROFILE SAVE=ADAPTIVE")


def test_skip_nozzle_clean_drops_the_wipe_and_the_second_homing():
    lines = render(SKIP_NOZZLE_CLEAN="1")
    assert not [line for line in lines if line.startswith("NOZZLE_WIPE")]
    assert lines.count("G28") == 1 and "M104 S150" in lines
    assert "BED_MESH_CALIBRATE ADAPTIVE=1 ADAPTIVE_MARGIN=10" in lines


def test_skip_bed_mesh_reuses_the_active_mesh():
    lines = render(mesh={"profile_name": "default", "profiles": {"default": {}}}, SKIP_BED_MESH="1")
    assert "BED_MESH_PROFILE LOAD=default" in lines
    assert not [line for line in lines if line.startswith(("BED_MESH_CALIBRATE", "BED_MESH_PROFILE SAVE"))]


def test_skip_bed_mesh_reuses_the_last_prints_mesh():
    lines = render(mesh={"profile_name": "", "profiles": {"ADAPTIVE": {}}}, SKIP_BED_MESH="1")
    assert "BED_MESH_PROFILE LOAD=ADAPTIVE" in lines
    assert not [line for line in lines if line.startswith("BED_MESH_CALIBRATE")]


def test_skip_bed_mesh_without_a_mesh_probes_anyway():
    lines = render(SKIP_BED_MESH="1")
    assert "BED_MESH_CALIBRATE ADAPTIVE=1 ADAPTIVE_MARGIN=10" in lines
    assert [line for line in lines if "probing one anyway" in line]


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d print start skip tests passed" % len(tests))
