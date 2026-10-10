"""Render the Box heater guard (config/klipper/mmu_keep_dry.cfg) the way Klipper does and
check the commands it emits. Usage: python3 tests/macros/test_box_heater_guard.py"""
import ast
import configparser
import pathlib

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = ROOT / "config/klipper/mmu_keep_dry.cfg"


def load():
    cfg = configparser.RawConfigParser(strict=False, inline_comment_prefixes=("#",))
    cfg.read(CFG)
    env = jinja2.Environment("{%", "%}", "{", "}")
    variables = {k[len("variable_"):]: ast.literal_eval(v)
                 for k, v in cfg["gcode_macro _BOX_HEATER_GUARD_VARS"].items()
                 if k.startswith("variable_")}
    return env.from_string(cfg["delayed_gcode _BOX_HEATER_GUARD"]["gcode"]), variables


GUARD, VARIABLES = load()


def run(elements, target, paused=0, drying=False, print_heat=False):
    printer = {
        "gcode_macro _BOX_HEATER_GUARD_VARS": {**VARIABLES, "paused_target": paused},
        "temperature_sensor unit0_heater_temp_a": {"temperature": elements[0]},
        "temperature_sensor unit0_heater_temp_b": {"temperature": elements[1]},
        "heater_generic unit0_heater": {"target": target},
        "mmu": {"drying_state": ["active" if drying else ""] * 4},
        "gcode_macro _BOX_PRINT_HEAT": {"active": print_heat},
    }
    lines = [line.strip() for line in GUARD.render(printer=printer).splitlines()]
    return [line for line in lines
            if line and not line.startswith("#") and not line.startswith("UPDATE_DELAYED_GCODE")]


def paused_to(lines):
    found = [line.split("VALUE=")[1] for line in lines if "VARIABLE=paused_target" in line]
    return float(found[-1]) if found else None


def heater_target(lines):
    found = [line.split("TARGET=")[1] for line in lines if line.startswith("SET_HEATER_TEMPERATURE")]
    return float(found[-1]) if found else None


def test_limits_match_the_agreed_values():
    assert (VARIABLES["element_limit"], VARIABLES["element_resume"],
            VARIABLES["element_hard_limit"]) == (80, 72, 95)


def test_nothing_while_elements_are_below_the_limit():
    assert run((70, 79.9), 45, drying=True) == []


def test_hot_element_cuts_the_heater_and_keeps_the_cycle():
    lines = run((75, 80.5), 45, drying=True)
    assert paused_to(lines) == 45 and heater_target(lines) == 0
    assert not any(line.startswith("MMU_HEATER") for line in lines)


def test_waits_until_the_elements_cool_down():
    assert run((74, 73), 0, paused=45, drying=True) == []


def test_restores_the_target_once_cool():
    lines = run((71, 70), 0, paused=45, drying=True)
    assert paused_to(lines) == 0 and heater_target(lines) == 45


def test_restores_print_heating_too():
    assert heater_target(run((60, 60), 0, paused=55, print_heat=True)) == 55


def test_cycle_ended_while_cut_is_not_restarted():
    lines = run((60, 60), 0, paused=45)
    assert paused_to(lines) == 0 and heater_target(lines) is None


def test_new_target_while_cut_is_kept_for_later():
    lines = run((78, 78), 50, paused=45, drying=True)
    assert paused_to(lines) == 50 and heater_target(lines) == 0


def test_hard_limit_stops_everything():
    lines = run((96, 70), 45, drying=True)
    assert "MMU_HEATER STOP=1" in lines and heater_target(lines) == 0
    assert any(line.startswith("RESPOND TYPE=error") for line in lines)
    assert "SET_GCODE_VARIABLE MACRO=_BOX_PRINT_HEAT VARIABLE=active VALUE=False" in lines


def test_hard_limit_also_applies_while_cut():
    lines = run((97, 97), 0, paused=45, drying=True)
    assert "MMU_HEATER STOP=1" in lines and paused_to(lines) == 0


def test_heater_off_and_hot_is_left_alone():
    # Elements still warm after a cycle: nothing to cut
    assert run((96, 96), 0) == []


if __name__ == "__main__":
    tests = [(name, fn) for name, fn in sorted(globals().items()) if name.startswith("test_")]
    for name, fn in tests:
        fn()
        print("ok", name)
    print("%d tests passed" % len(tests))
