"""Render _BOX_PURGE_LINES and check where the lines go. Usage: python3 tests/macros/test_purge_lines.py"""
import configparser
import json
import pathlib
import re

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[2]
MESH_MARGIN = 10


def render(polygons, bounds=None):
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(ROOT / "config/klipper/q2_purge.cfg")
    section = cfg["gcode_macro _BOX_PURGE_LINES"]
    env = jinja2.Environment("{%", "%}", "{", "}")
    variables = {k[len("variable_"):]: float(v) for k, v in section.items() if k.startswith("variable_")}
    objects = [{"polygon": polygon} for polygon in polygons]
    text = env.from_string(section["gcode"]).render(
        printer={"exclude_object": {"objects": objects}}, params={"FLOW": "12", "HEIGHT": "0.2", **(bounds or {})}, **variables)
    return [line.strip() for line in text.splitlines() if line.strip()]


def box(x0, y0, x1, y1):
    return [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]


def travels(lines):
    return [(float(a), float(b)) for a, b in re.findall(r"^G1 X([\d.-]+) Y([\d.-]+) F12000$", "\n".join(lines), re.M)]


def test_lines_sit_in_front_of_the_part_and_inside_the_mesh():
    (x1, y1), (x2, y2) = travels(render([box(100, 100, 140, 150)]))
    assert x1 == x2 == 95 and y1 == 93.5 and y2 == 95
    assert y1 >= 100 - MESH_MARGIN


def test_part_at_the_front_edge_uses_the_back():
    assert [y for _, y in travels(render([box(100, 3, 140, 150)]))] == [155, 156.5]


def test_full_plate_skips_the_lines():
    lines = render([box(10, 3, 260, 266)])
    assert travels(lines) == [] and not [line for line in lines if " E" in line]


def test_line_stays_on_the_bed_near_the_side():
    assert travels(render([box(0, 100, 10, 150)]))[0][0] == 5
    assert travels(render([box(260, 100, 270, 150)]))[0][0] == 215


def test_no_objects_keeps_the_stock_position():
    assert travels(render([])) == [(108, 1), (108, 2.5)]


def test_extrusion_matches_the_stock_pattern():
    lines = render([])
    extrusions = [float(x) for x in re.findall(r" E([\d.]+) ", "\n".join(lines))]
    assert extrusions == [8] + [0.3742] * 5 + [10] + [0.3742] * 5


def test_slicer_bounds_with_brim_win_over_object_polygons():
    bounds = {"MIN_X": "90", "MIN_Y": "90", "MAX_X": "150", "MAX_Y": "160"}
    assert travels(render([box(100, 100, 140, 150)], bounds)) == [(95, 83.5), (95, 85)]


def test_start_gcode_calls_the_macro():
    machine = ROOT / "slicer/orca/machine/Q2 Offload 0.4 nozzle.json"
    start = json.loads(machine.read_text())["machine_start_gcode"]
    assert "_BOX_PURGE_LINES FLOW=" in start and "G1 X108" not in start


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d purge line tests passed" % len(tests))
