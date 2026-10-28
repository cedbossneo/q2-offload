"""Render PRINT_START and the XY homing override (config/klipper/gcode_macro_mmu.cfg) the way
Klipper does and check that the nozzle heats over the chute and that the configured
acceleration is left behind. Also checks the Orca start G-code travel speeds.
Usage: python3 tests/macros/test_print_start.py"""
import configparser
import json
import pathlib
import re

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = ROOT / "config/klipper/gcode_macro_mmu.cfg"
MACHINE = ROOT / "slicer/orca/machine/Q2 Offload 0.4 nozzle.json"
MAX_ACCEL = 7000.0
MAX_START_TRAVEL_F = 12000


def load(section):
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(CFG)
    env = jinja2.Environment("{%", "%}", "{", "}", extensions=["jinja2.ext.do"])
    return env.from_string(cfg[section]["gcode"])


PRINTER = {
    "configfile": {"settings": {"printer": {"max_accel": MAX_ACCEL}}},
    "toolhead": {"axis_maximum": {"z": 270}},
    "gcode_macro PRINTER_PARAM": {"max_x_position": 270, "max_y_position": 270},
}


def render(section, params):
    out = load(section).render(printer=PRINTER, params=params)
    lines = (line.split(";")[0].split("#")[0].strip() for line in out.splitlines())
    return [line for line in lines if line]


def accel_cmds(lines):
    return [line for line in lines if line.startswith(("M204", "SET_VELOCITY_LIMIT"))]


PRINT_START = render("gcode_macro PRINT_START", {
    "BED": "60", "HOTEND": "220", "CHAMBER": "0", "EXTRUDER": "0", "INITIAL_TOOL": "0",
    "TOTAL_TOOLCHANGES": "0", "REFERENCED_TOOLS": "0", "TOOL_COLORS": "FFFFFF",
    "TOOL_TEMPS": "220", "TOOL_MATERIALS": "PLA", "FILAMENT_NAMES": "x", "PURGE_VOLUMES": "0"})


def test_print_start_heats_nozzle_over_the_chute():
    assert not any(line.startswith("G0 X260") for line in PRINT_START)
    trash = PRINT_START.index("MOVE_TO_TRASH")
    assert trash < PRINT_START.index("M109 S220") < PRINT_START.index("MMU_START_LOAD_INITIAL_TOOL")


def test_print_start_loads_with_the_configured_acceleration():
    load = PRINT_START.index("MMU_START_LOAD_INITIAL_TOOL")
    assert accel_cmds(PRINT_START[:load])[-1] == f"SET_VELOCITY_LIMIT ACCEL={MAX_ACCEL}"


def test_homing_leaves_the_configured_acceleration():
    for params in ({}, {"X": "0", "Y": "0"}, {"X": "0"}, {"Y": "0"}):
        assert accel_cmds(render("homing_override", params))[-1] == f"SET_VELOCITY_LIMIT ACCEL={MAX_ACCEL}"


def test_orca_start_gcode_travels_are_not_too_fast():
    start = json.loads(MACHINE.read_text())["machine_start_gcode"]
    speeds = [int(f) for f in re.findall(r"^G1 X[^\n]*F(\d+)$", start, re.M)]
    assert speeds and max(speeds) <= MAX_START_TRAVEL_F


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d print start tests passed" % len(tests))
