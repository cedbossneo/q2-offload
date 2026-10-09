"""Render the Box print-heating macros (config/klipper/mmu_keep_dry.cfg) the way Klipper
does and check the commands they emit. Usage: python3 tests/macros/test_box_heat.py"""
import ast
import configparser
import pathlib

import jinja2

CFG = pathlib.Path(__file__).resolve().parents[2] / "config/klipper/mmu_keep_dry.cfg"
MAX_TEMP = 55.0


def load():
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(CFG)
    env = jinja2.Environment("{%", "%}", "{", "}", extensions=["jinja2.ext.do"])
    sec = cfg["gcode_macro _BOX_PRINT_HEAT"]
    variables = {k[len("variable_"):]: ast.literal_eval(v)
                 for k, v in sec.items() if k.startswith("variable_")}
    return (env.from_string(sec["gcode"]),
            env.from_string(cfg["gcode_macro DISABLE_BOX_HEATER"]["gcode"]),
            variables)


HEAT, OFF, VARIABLES = load()


def render(template, gates, params=None, drying="", active=False, settings=None):
    if settings is None:
        settings = {"mmu_unit_parameters unit0": {"heater_max_temp": MAX_TEMP}}
    printer = {
        "gcode_macro _BOX_PRINT_HEAT": {**VARIABLES, "active": active},
        "mmu": {"gate_status": [1 if m is not None else 0 for m in gates],
                "gate_material": [m or "" for m in gates],
                "drying_state": [drying]},
        "configfile": {"settings": settings},
    }
    out = template.render(printer=printer, params=params or {})
    return [line.strip() for line in out.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def heater_cmd(lines):
    return [line for line in lines if line.startswith("MMU_HEATER")]


def test_heats_to_material_temperature():
    assert heater_cmd(render(HEAT, ["PETG", "PETG", None, None])) == ["MMU_HEATER TEMP=45"]
    assert heater_cmd(render(HEAT, ["ABS", None, None, None])) == ["MMU_HEATER TEMP=55"]


def test_lowest_loaded_material_wins():
    assert heater_cmd(render(HEAT, ["PETG", "PLA", None, None])) == []


def test_slicer_material_of_used_tool_counts():
    lines = render(HEAT, ["PETG", None, None, None],
                   {"TOOL_MATERIALS": "PETG,TPU", "REFERENCED_TOOLS": "0,1"})
    assert heater_cmd(lines) == []


def test_capped_by_heater_max_temp():
    assert heater_cmd(render(HEAT, ["PA-CF", None, None, None])) == ["MMU_HEATER TEMP=55.0"]
    assert heater_cmd(render(HEAT, ["PA-CF", None, None, None], settings={})) == ["MMU_HEATER TEMP=55.0"]


def test_variant_falls_back_to_base_material():
    assert heater_cmd(render(HEAT, ["PETG Translucent", None, None, None])) == ["MMU_HEATER TEMP=45"]


def test_unknown_or_missing_material_does_not_heat():
    assert heater_cmd(render(HEAT, ["HIPS", None, None, None])) == []
    assert heater_cmd(render(HEAT, ["", None, None, None])) == []
    assert heater_cmd(render(HEAT, [None, None, None, None])) == []


def test_running_drying_cycle_is_left_alone():
    assert heater_cmd(render(HEAT, ["ABS", None, None, None], drying="active")) == []
    assert heater_cmd(render(OFF, ["ABS", None, None, None], drying="active", active=True)) == []


def test_disable_stops_only_print_heating():
    assert heater_cmd(render(OFF, ["ABS", None, None, None], active=True)) == ["MMU_HEATER STOP=1"]
    assert render(OFF, ["ABS", None, None, None], active=False) == []


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d box heat tests passed" % len(tests))
