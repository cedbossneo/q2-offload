"""Check the Qidi layout published for the slicer and the slot map applied at print start.
Usage: python3 tests/macros/test_qidi_compat.py"""
import configparser
import importlib.util
import pathlib

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("qidi_box_compat", ROOT / "host/extras/qidi_box_compat.py")
compat = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compat)

MMU = {"gate_status": [2, 1, 0, 2], "gate_color": ["f4efeb", "#de1619", "", "1d1d1d"],
       "gate_material": ["PLA", "PETG", "", "PLA"], "gate_filament_name": ["White", "", "", "Black"]}


class Printer:
    def __init__(self, mmu):
        self.objects = {}
        self.mmu = mmu


def test_variables_match_what_the_agent_reads():
    variables = compat.qidi_variables(compat.read_gates(MMU))
    assert variables["box_count"] == 1
    assert variables["color_slot1"] == ["DE1619"] and variables["filament_slot1"] == "PETG"
    assert variables["vendor_slot3"] == 0


def test_a_gate_with_a_spool_publishes_its_spoolman_id():
    gates = compat.read_gates({**MMU, "gate_spool_id": [26, -1, 0, 29]})
    variables = compat.qidi_variables(gates)
    assert variables["filament_slot0"] == 10026 and variables["filament_slot3"] == 10029
    assert variables["filament_slot1"] == "PETG"


def test_filament_list_names_each_numbered_spool():
    gates = compat.read_gates({**MMU, "gate_material": ["PETG", "PLA", "", "TPU"], "gate_spool_id": [26, -1, 0, 29]})
    text = compat.filament_list(gates)
    assert "[colordict]\n1 = FFFFFF" in text
    assert "[fila10026]\nfilament = PETG" in text and "[fila10029]\nfilament = TPU" in text
    assert "fila-1" not in text


def test_empty_gate_reports_no_filament():
    gates = compat.read_gates(MMU)
    views = [compat.BoxStepperView(type("C", (), {"gates": gates}), slot) for slot in range(5)]
    assert [view.get_status(0)["runout_button"] for view in views] == [0, 0, 1, 0, 1]


def test_controller_uses_the_paths_of_the_agent_and_qidi_studio():
    box = compat.controller_status(compat.read_gates(MMU))["box"]
    assert box["box0_filament_info_1_filament_type"] == "PETG"
    assert box["box0_filament_info_3_color_rgb_str"] == ["1D1D1D"]
    assert box["box0_box_inserted_2"] == 0 and box["box0_filament_info_0_filament_str"] == "White"


def test_eight_gates_make_two_boxes():
    gates = compat.read_gates({"gate_status": [1] * 8})
    assert compat.box_count(gates) == 2
    assert "box1_filament_info_3_filament_type" in compat.controller_status(gates)["box"]


def slot_map(variables, ttg=(0, 1, 2, 3)):
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(ROOT / "config/klipper/gcode_macro_mmu.cfg")
    template = jinja2.Environment("{%", "%}", "{", "}").from_string(cfg["gcode_macro _BOX_APPLY_SLOT_MAP"]["gcode"])
    printer = {"save_variables": {"variables": variables}, "mmu": {"ttg_map": list(ttg)}}
    return [line.strip() for line in template.render(printer=printer).splitlines() if line.strip()]


def test_chosen_slots_become_the_tool_map_and_are_used_once():
    lines = slot_map({"value_t0": "slot3", "value_t1": "slot0"})
    assert lines[0] == "MMU_TTG_MAP MAP=3,0,2,3 QUIET=1"
    assert 'SAVE_VARIABLE VARIABLE=value_t0 VALUE="\'\'"' in lines
    assert 'SAVE_VARIABLE VARIABLE=value_t1 VALUE="\'\'"' in lines
    assert "SAVE_VARIABLE VARIABLE=q2_slot_map_active VALUE=True" in lines


def test_next_print_without_a_choice_restores_the_map():
    lines = slot_map({"q2_slot_map_active": True, "value_t0": ""}, ttg=(3, 0, 2, 3))
    assert lines == ["MMU_TTG_MAP MAP=0,1,2,3 QUIET=1", "SAVE_VARIABLE VARIABLE=q2_slot_map_active VALUE=False"]


def test_print_from_mainsail_leaves_a_custom_map_alone():
    assert slot_map({}, ttg=(1, 0, 2, 3)) == []


def test_invalid_slot_is_ignored():
    assert slot_map({"value_t0": "slot9", "value_t1": "other"}) == []


def test_print_start_applies_the_map_first():
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(ROOT / "config/klipper/gcode_macro_mmu.cfg")
    gcode = cfg["gcode_macro PRINT_START"]["gcode"]
    assert gcode.index("_BOX_APPLY_SLOT_MAP") < gcode.index("MMU_START_SETUP")


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d Qidi compat tests passed" % len(tests))
