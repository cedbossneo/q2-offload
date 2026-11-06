"""Check the generated OrcaSlicer spool presets. Usage: python3 tests/macros/test_orca_spool_presets.py"""
import importlib.util
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("spools", ROOT / "scripts/orca-spool-presets.py")
spools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(spools)

PROFILES = {
    "fdm_filament_common": {"filament_density": ["1.24"], "filament_cost": ["20"], "filament_multitool_ramming": ["1"]},
    "fdm_filament_pla": {"inherits": "fdm_filament_common", "filament_type": ["PLA"]},
    "Generic PLA @System": {"inherits": "fdm_filament_pla", "filament_id": "OFDSrzZ8", "setting_id": "abc", "type": "filament"},
}
SPOOL = {"id": 29, "filament": {"name": "PLA", "material": "PLA", "color_hex": "1d1d1d", "density": 1.31,
                                "diameter": 1.75, "settings_extruder_temp": 220, "vendor": {"name": "Polymaker"}}}


def build(spool=SPOOL):
    return spools.build_preset(spool, spools.flatten("Generic PLA @System", PROFILES.__getitem__))


def test_preset_has_no_parent_and_its_own_id():
    preset = build()
    assert preset["inherits"] == "" and preset["filament_id"] == "QD_1_0_10029"
    assert preset["version"]


def test_settings_of_the_whole_chain_are_flattened():
    assert build()["filament_cost"] == ["20"]


def test_slicer_tool_change_is_off_for_happy_hare():
    preset = build()
    assert preset["filament_multitool_ramming"] == ["0"]
    for key in ("filament_cooling_moves", "filament_loading_speed", "filament_unloading_speed_start"):
        assert preset[key] == ["0"], key


def test_tool_change_fields_match_the_filament_templates():
    import json
    for path in sorted((ROOT / "slicer/orca/filament").glob("*.json")):
        template = json.loads(path.read_text())
        fields = {key: value for key, value in template.items() if key in spools.HAPPY_HARE_TOOL_CHANGE}
        assert fields == spools.HAPPY_HARE_TOOL_CHANGE, path.name


def test_spoolman_values_win():
    preset = build()
    assert preset["filament_density"] == ["1.31"] and preset["default_filament_colour"] == ["#1D1D1D"] and "filament_colour" not in preset
    assert preset["nozzle_temperature"] == ["220"] and preset["filament_vendor"] == ["Polymaker"]


def test_missing_spoolman_values_keep_the_base():
    spool = {"id": 3, "filament": {"material": "PLA"}}
    preset = build(spool)
    assert preset["filament_density"] == ["1.24"] and "nozzle_temperature" not in preset
    assert preset["name"] == "#3 PLA"


def test_ids_match_the_box_compat_module():
    source = (ROOT / "host/extras/qidi_box_compat.py").read_text()
    assert int(re.search(r"SPOOL_ID_OFFSET = (\d+)", source).group(1)) == spools.SPOOL_ID_OFFSET


def test_base_of_variants():
    assert spools.base_name({"material": "PLA+"}) == "Generic PLA @System"
    assert spools.base_name({"material": "PETG"}) == "Generic PETG @System"
    assert spools.base_name({"material": "PETG", "extra": {"orca_base_preset": '"SUNLU PETG @System"'}}) == "SUNLU PETG @System"


def test_base_preset_cannot_be_a_path():
    for bad in ("../../etc/secret", "a/b", "a\\\\b"):
        try:
            spools.base_name({"material": "PLA", "extra": {"orca_base_preset": '"%s"' % bad}})
        except KeyError:
            continue
        raise AssertionError(bad)


def test_file_names_are_safe_everywhere():
    assert spools.file_name({"name": 'a/b:c?"d'}) == "a-b-c--d.json"


def test_tuned_values_in_spoolman_win():
    filament = {**SPOOL["filament"], "extra": {"orca_pressure_advance": "0.0418", "orca_nozzle_temperature": "210",
                                               "orca_overhang_fan_threshold": '"50%"', "orca_base_preset": '"X"'}}
    preset = build({"id": 29, "filament": filament})
    assert preset["pressure_advance"] == ["0.0418"] and preset["nozzle_temperature"] == ["210"]
    assert preset["overhang_fan_threshold"] == ["50%"] and "base_preset" not in preset


def test_values_use_orca_serialized_form():
    assert spools.option_values(True) == ["1"] and spools.option_values("false") == ["0"]
    assert spools.option_values("nil,nil") == ["nil", "nil"] and spools.option_values('"120 100"') == ["120 100"]
    assert spools.option_values(210) == ["210"]


def test_vendor_profiles_are_searched_in_their_folder():
    assert "SUNLU/SUNLU%20PETG%20%40System" in spools.library_paths("SUNLU PETG @System")
    assert "base/fdm_filament_pla" in spools.library_paths("fdm_filament_pla")


def test_publish_is_stable_and_removes_gone_spools():
    import json
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out = pathlib.Path(tmp)
        (out / "#9 gone.json").write_text("{}")
        spools.publish([build()], out)
        index = json.loads((out / "index.json").read_text())
        assert list(index["files"]) == ["#29 Polymaker PLA.json"] and not (out / "#9 gone.json").exists()
        assert json.loads(index["files"]["#29 Polymaker PLA.json"])["filament_id"] == "QD_1_0_10029"
        spools.publish([build()], out)
        assert json.loads((out / "index.json").read_text())["hash"] == index["hash"]


def test_gates_describe_the_spool_and_empty_slots():
    mmu = {"gate_status": [2, 0], "gate_spool_id": [29, -1], "gate_color": ["1d1d1d", ""], "gate_material": ["PLA", ""]}
    spool = {**SPOOL, "remaining_weight": 644.2, "initial_weight": 1000.0, "last_used": "2026-11-04T13:41:00Z"}
    gates = spools.gates_from(mmu, [spool])
    assert gates[0]["spool_id"] == 29 and gates[0]["percent"] == 64 and gates[0]["remaining_g"] == 644
    assert gates[0]["vendor"] == "Polymaker" and gates[0]["last_used"] == "2026-11-04" and gates[0]["nozzle"] == 220
    assert gates[1]["empty"] and gates[1]["color"] == "FFFFFF" and "spool_id" not in gates[1]


def test_unknown_spool_keeps_the_gate_colour():
    mmu = {"gate_status": [1], "gate_spool_id": [99], "gate_color": ["ff0000"], "gate_material": ["PLA"]}
    gate = spools.gates_from(mmu, [])[0]
    assert gate["color"] == "FF0000" and not gate["empty"] and "spool_id" not in gate


def test_box_reports_environment_and_loaded_slot():
    box = spools.box_from({"mmu": {"gate": 3, "filament": "Loaded", "drying": [None]},
                           "temperature_sensor unit0_Env": {"temperature": 29.1}, "aht10 unit0_Env": {"humidity": 41.0}})
    assert box == {"temperature": 29.1, "humidity": 41.0, "drying": False, "loaded_slot": 4}
    assert spools.box_from({"mmu": {"gate": 3, "filament": "Unloaded"}})["loaded_slot"] is None


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d spool preset tests passed" % len(tests))
