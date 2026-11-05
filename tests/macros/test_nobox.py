"""On a Q2 without a Box the Happy Hare includes are off: q2_nobox.cfg has to stand in for every
Box command that the Orca profile and the print macros send. An unknown command is only a console
message in Klipper, so nothing else would catch a gap. Usage: python3 tests/macros/test_nobox.py"""
import configparser
import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
KLIPPER = ROOT / "config/klipper"
# Only called behind a printer.mmu check
GUARDED = {"MMU_ERROR_DIALOG", "MMU_TTG_MAP"}
BOX_ONLY = ("q2_box.cfg", "mmu_keep_dry.cfg")


def config(path):
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(path)
    return cfg


def commands(text):
    return set(re.findall(r"^\s*(_?MMU_[A-Z_]+|_BOX_PRINT_HEAT|DISABLE_BOX_HEATER)\b", text, re.M))


def available():
    names = set()
    for path in KLIPPER.glob("*.cfg"):
        if path.name not in BOX_ONLY:
            names |= {s.split(" ", 1)[1].upper() for s in config(path).sections() if s.startswith("gcode_macro ")}
    return names


def test_print_macros_have_a_stand_in():
    macros = config(KLIPPER / "gcode_macro_mmu.cfg")
    sent = commands(macros["gcode_macro PRINT_START"]["gcode"]) | commands(macros["gcode_macro PRINT_END"]["gcode"])
    missing = sent - available() - GUARDED
    assert not missing, missing


def test_orca_profile_has_a_stand_in():
    machine = json.loads((ROOT / "slicer/orca/machine/Q2 Offload 0.4 nozzle.json").read_text())
    sent = set()
    for key in ("machine_start_gcode", "machine_end_gcode", "layer_change_gcode", "change_filament_gcode"):
        sent |= commands(machine.get(key, ""))
    missing = sent - available() - GUARDED
    assert not missing, missing


def test_guarded_commands_are_guarded():
    gcode = config(KLIPPER / "gcode_macro_mmu.cfg")["gcode_macro PRINT_START"]["gcode"]
    assert re.search(r"printer\.mmu is defined %}\s*MMU_ERROR_DIALOG", gcode)


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d no-Box tests passed" % len(tests))
