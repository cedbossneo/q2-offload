"""Render PRINTER_INIT and CLEAR_LAST_FILE the way Klipper does and check the Z motors hold the
bed only while a power-loss resume is pending. Usage: python3 tests/macros/test_z_hold.py"""
import configparser
import pathlib

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[2]
ENABLE_Z = ["SET_STEPPER_ENABLE STEPPER=stepper_z enable=1", "SET_STEPPER_ENABLE STEPPER=stepper_z1 enable=1"]
RELEASE_Z = ["SET_STEPPER_ENABLE STEPPER=stepper_z enable=0", "SET_STEPPER_ENABLE STEPPER=stepper_z1 enable=0"]


def template(filename, section):
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(ROOT / "config/klipper" / filename)
    return jinja2.Environment("{%", "%}", "{", "}").from_string(cfg[section]["gcode"])


def stepper_lines(rendered):
    return [line.strip() for line in rendered.splitlines() if "SET_STEPPER_ENABLE" in line]


def boot(variables):
    tpl = template("gcode_macro_mmu.cfg", "delayed_gcode PRINTER_INIT")
    return stepper_lines(tpl.render(printer={"save_variables": {"variables": variables}}))


def clear(state, homed_axes):
    tpl = template("plr.cfg", "gcode_macro CLEAR_LAST_FILE")
    return stepper_lines(tpl.render(printer={"print_stats": {"state": state}, "toolhead": {"homed_axes": homed_axes}}))


def test_boot_without_pending_resume_leaves_z_off():
    assert boot({"was_interrupted": False}) == []


def test_boot_with_pending_resume_holds_z():
    assert boot({"was_interrupted": True}) == ENABLE_Z


def test_boot_with_unknown_state_holds_z():
    assert boot({}) == ENABLE_Z


def test_declining_the_resume_releases_z():
    assert clear("standby", "") == RELEASE_Z


def test_clear_never_releases_z_during_a_print():
    assert clear("printing", "") == [] and clear("paused", "") == []


def test_clear_never_releases_z_once_homed():
    assert clear("standby", "xyz") == [] and clear("complete", "xyz") == []


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d Z hold tests passed" % len(tests))
