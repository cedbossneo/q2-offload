"""Render _MMU_PARK_MOVE (config/klipper/q2_purge.cfg) the way Klipper does and check the
toolhead only enters or leaves the chute (Y > 270) along Y. Usage: python3 tests/macros/test_park_move.py"""
import configparser
import pathlib

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = ROOT / "config/klipper/q2_purge.cfg"


def load():
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(CFG)
    section = cfg["gcode_macro _MMU_PARK_MOVE"]
    env = jinja2.Environment("{%", "%}", "{", "}")
    variables = {k[len("variable_"):]: int(v) for k, v in section.items() if k.startswith("variable_")}
    return env.from_string(section["gcode"]), variables


PARK_MOVE, VARIABLES = load()


def render(cur_x, cur_y, **params):
    printer = {
        "gcode_macro PURGE_VARIABLES": {"entry_speed": 50},
        "gcode_move": {"gcode_position": {"x": cur_x, "y": cur_y}},
    }
    out = PARK_MOVE.render(printer=printer, params={k: str(v) for k, v in params.items()}, **VARIABLES)
    return [line.strip() for line in out.splitlines()
            if line.strip() and not line.strip().startswith("#")]


def test_park_into_chute_stages_at_the_limit_then_moves_along_y():
    assert render(150, 100, X=85, Y=287.5, F=9000) == ["G90", "G1 X85.0 Y270 F9000.0", "G1 Y287.5 F3000.0"]


def test_park_into_chute_from_another_chute_x_leaves_first():
    assert render(110, 287.5, X=85, Y=287.5, F=9000) == ["G90", "G1 Y270 F3000.0", "G1 X85.0 Y270 F9000.0",
                                                         "G1 Y287.5 F3000.0"]


def test_park_into_chute_already_at_chute_x_moves_along_y_only():
    assert render(85, 280, X=85, Y=287.5, F=9000) == ["G90", "G1 Y287.5 F3000.0"]


def test_restore_from_chute_leaves_along_y_first():
    assert render(85, 287.5, RESTORE=1, X=120, Y=140, F=9000) == ["G90", "G1 Y270 F3000.0", "G1 X120.0 Y140.0 F9000.0"]


def test_in_place_park_does_not_move():
    assert render(120, 140, X=-999, Y=-999, F=9000) == ["G90"]


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d park move tests passed" % len(tests))
