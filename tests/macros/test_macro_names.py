"""Klipper's G-code parser splits a command at its first digit, so a macro named _X2_NAME loads
fine and then fails at run time with 'Unknown command:"_X2"'. Usage: python3 tests/macros/test_macro_names.py"""
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
# A name is callable when it has no digit, or when its digits only come at the very end
CALLABLE = re.compile(r"^[A-Za-z_]+[0-9]*$")
# Inherited from the stock Qidi and Happy Hare macros
ALLOWED = set()


def macro_names():
    for path in sorted((ROOT / "config/klipper").glob("*.cfg")):
        for name in re.findall(r"^\[gcode_macro ([^\]]+)\]", path.read_text(), re.M):
            yield path.name, name.strip()


def test_every_macro_can_be_called():
    broken = [(file, name) for file, name in macro_names() if not CALLABLE.match(name) and name not in ALLOWED]
    assert not broken, broken


if __name__ == "__main__":
    test_every_macro_can_be_called()
    print("macro names are callable")
