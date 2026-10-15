"""Render BUCKET_PURGE (config/klipper/q2_purge.cfg) the way Klipper does and check the fan
is restored to its previous speed, homed or not. Usage: python3 tests/macros/test_bucket_purge.py"""
import ast
import configparser
import pathlib

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = ROOT / "config/klipper/q2_purge.cfg"


def load():
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(CFG)
    env = jinja2.Environment("{%", "%}", "{", "}", extensions=["jinja2.ext.do"])
    variables = {k[len("variable_"):]: ast.literal_eval(v)
                 for k, v in cfg["gcode_macro PURGE_VARIABLES"].items() if k.startswith("variable_")}
    return env.from_string(cfg["gcode_macro BUCKET_PURGE"]["gcode"]), variables


PURGE, VARIABLES = load()


def render(homed_axes, fan_speed=0.4):
    printer = {
        "gcode_macro PURGE_VARIABLES": VARIABLES,
        "gcode_macro _MMU_SEQUENCE_VARS": {"retract_speed": 30},
        "gcode_macro _MMU_PARK": {"retracted_length": 0},
        "toolhead": {"homed_axes": homed_axes, "max_accel": 5000,
                     "position": {"x": 0, "y": 0}, "axis_maximum": {"x": 270, "y": 300}},
        "gcode_move": {"speed_factor": 1.0, "gcode_position": {"x": 0, "y": 0}},
        "configfile": {"config": {"extruder": {"filament_diameter": "1.75"}}},
        "mmu": {"last_tool": -2, "tool": -2, "extruder_filament_remaining": 0,
                "slicer_tool_map": {"purge_volumes": []}},
        "extruder": {"temperature": 250, "target": 250},
        "fan_generic cooling_fan": {"speed": fan_speed},
    }
    out = PURGE.render(printer=printer, params={}, action_respond_info=lambda msg: "")
    return [line.strip() for line in out.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def fan_cmds(lines):
    return [line for line in lines if line.startswith("SET_FAN_SPEED")]


def test_unhomed_restores_fan_speed():
    assert fan_cmds(render("")) == ["SET_FAN_SPEED FAN=cooling_fan SPEED=0.4"]


def test_homed_cools_blob_then_restores_fan_speed():
    assert fan_cmds(render("xyz")) == ["SET_FAN_SPEED FAN=cooling_fan SPEED=1.0",
                                       "SET_FAN_SPEED FAN=cooling_fan SPEED=0.4"]


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d bucket purge tests passed" % len(tests))
