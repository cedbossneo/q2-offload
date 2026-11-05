"""Render the guided recovery macros and check RESUME only follows a confirmed load.
Usage: python3 tests/macros/test_recovery.py"""
import configparser
import pathlib

import jinja2

CFG = pathlib.Path(__file__).resolve().parents[2] / "config/klipper/gcode_macro_mmu.cfg"
UNLOADED, IN_BOWDEN, LOADED = 0, 3, 10


def render(section, mmu, **params):
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(CFG)
    out = jinja2.Environment("{%", "%}", "{", "}").from_string(cfg["gcode_macro " + section]["gcode"])
    text = out.render(printer={"mmu": mmu}, params=params)
    return [line.strip() for line in text.splitlines() if line.strip()]


def test_retry_targets_the_tool_that_failed():
    lines = render("_BOX_RETRY_LOAD", {"next_tool": 3, "tool": 1})
    assert "_BOX_RETRY_RELOAD TOOL=3" in lines


def test_retry_falls_back_to_the_selected_tool():
    lines = render("_BOX_RETRY_LOAD", {"next_tool": -1, "tool": 2})
    assert "_BOX_RETRY_RELOAD TOOL=2" in lines


def test_retry_refuses_without_a_tool():
    lines = render("_BOX_RETRY_LOAD", {"next_tool": -1, "tool": -1})
    assert not [line for line in lines if line.startswith(("MMU_", "_Q2"))]


def test_unload_only_when_filament_is_in_the_path():
    assert render("_BOX_RETRY_UNLOAD", {"filament_pos": IN_BOWDEN}) == ["MMU_UNLOAD"]
    assert render("_BOX_RETRY_UNLOAD", {"filament_pos": UNLOADED}) == []


def test_reload_only_after_a_clean_unload():
    assert render("_BOX_RETRY_RELOAD", {"filament_pos": UNLOADED}, TOOL="3") == ["MMU_CHANGE_TOOL TOOL=3"]
    assert render("_BOX_RETRY_RELOAD", {"filament_pos": IN_BOWDEN}, TOOL="3") == []


def test_resume_only_when_loaded():
    assert render("_BOX_RESUME_IF_LOADED", {"filament_pos": LOADED}) == ["RESUME"]
    for position in (UNLOADED, IN_BOWDEN):
        assert "RESUME" not in render("_BOX_RESUME_IF_LOADED", {"filament_pos": position})


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d recovery tests passed" % len(tests))
