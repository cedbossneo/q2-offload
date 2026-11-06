"""Render the pressure advance calibration macros (config/klipper/q2_pa_calibrate.cfg) the way
Klipper does, and parse their output the way Klipper's G-code parser does.
Usage: python3 tests/macros/test_pa_calibrate.py"""
import ast
import configparser
import copy
import pathlib
import re
import shlex

import jinja2

ROOT = pathlib.Path(__file__).resolve().parents[2]
CFG = ROOT / "config/klipper/q2_pa_calibrate.cfg"
MMU_CFG = ROOT / "config/klipper/gcode_macro_mmu.cfg"

ENTRY = {'filament': 16, 'temp': 255, 'flow': 0.965, 'material': 'PETG', 'name': 'Sunlu Green', 'tries': 0}


def sections(path):
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(path)
    return cfg


def macro_vars():
    cfg = sections(CFG)["gcode_macro _SPOOL_PA_VARS"]
    return {key[len("variable_"):]: ast.literal_eval(value)
            for key, value in cfg.items() if key.startswith("variable_")}


def printer(state="standby", pending=None, gate=-1, filament="Unloaded", k_opt=None, enabled=True):
    vars_ = dict(macro_vars(), enabled=enabled)
    return {
        "print_stats": {"state": state},
        "save_variables": {"variables": {"q2_pa_pending": copy.deepcopy(pending or {})}},
        "mmu": {"gate": gate, "filament": filament, "gate_spool_id": [26, 22, 23, 29],
                "ttg_map": [0, 1, 2, 3]},
        "toolhead": {"homed_axes": "xyz"},
        "autopa": {"last": {"sweep": {"k_opt": k_opt}}},
        "gcode_macro _SPOOL_PA_VARS": vars_,
    }


class Run:
    """Renders one macro and records action_call_remote_method calls."""

    def __init__(self, section, params, state, path=CFG):
        self.remote = []
        env = jinja2.Environment("{%", "%}", "{", "}",
                                 extensions=["jinja2.ext.do", "jinja2.ext.loopcontrols"])
        template = env.from_string(sections(path)[section]["gcode"])
        out = template.render(printer=state, params=params,
                              action_call_remote_method=self.call_remote)
        self.lines = [line.strip() for line in out.splitlines() if line.strip()]
        self.commands = [klipper_parse(line) for line in self.lines if not line.startswith("#")]

    def call_remote(self, method, **kwargs):
        self.remote.append((method, kwargs))
        return ""


def klipper_parse(line):
    """Klipper's extended command parsing (gcode.py): the command ends at '#', ';' or '*',
    then shlex splits KEY=VALUE pairs."""
    m = re.match(r'^\s*(?P<cmd>[a-zA-Z_][a-zA-Z0-9_]+)(?:\s+|$)(?P<args>[^#*;]*?)\s*(?:[#*;].*)?$', line)
    assert m, line
    args = dict(arg.split("=", 1) for arg in shlex.split(m.group("args")) if "=" in arg)
    return m.group("cmd").upper(), args


def saved_pending(run):
    values = [args["VALUE"] for cmd, args in run.commands if cmd == "SAVE_VARIABLE"]
    assert len(values) == 1, run.lines
    return ast.literal_eval(values[0])


def names(run):
    return [cmd for cmd, _ in run.commands]


def test_new_spool_event_asks_the_component():
    run = Run("gcode_macro _SPOOL_PA_MMU_EVENT", {"EVENT": "spool_created", "SPOOLID": "22", "GATE": "1"}, printer())
    assert run.remote == [("q2_pa_spool_created", {"spool_id": 22, "gate": 1})]


def test_other_events_or_no_component_do_nothing():
    run = Run("gcode_macro _SPOOL_PA_MMU_EVENT", {"EVENT": "gate_map_changed", "GATE": "1"}, printer())
    assert run.remote == []
    run = Run("gcode_macro _SPOOL_PA_MMU_EVENT", {"EVENT": "spool_created", "SPOOLID": "22", "GATE": "1"},
              printer(enabled=False))
    assert run.remote == []


def test_pending_set_adds_and_removes_with_values_klipper_can_save():
    add = Run("gcode_macro _SPOOL_PA_PENDING_SET",
              {"SPOOL": "22", "FILAMENT": "16", "TEMP": "255", "FLOW": "0.965", "MATERIAL": "PETG",
               "NAME": "Sunlu Green"},
              printer(pending={23: dict(ENTRY, name="Other")}))
    assert saved_pending(add) == {23: dict(ENTRY, name="Other"), 22: ENTRY}
    remove = Run("gcode_macro _SPOOL_PA_PENDING_SET", {"SPOOL": "23"},
                 printer(pending={23: ENTRY, 22: ENTRY}))
    assert saved_pending(remove) == {22: ENTRY}


def test_a_saved_value_drops_the_other_spools_of_that_filament():
    pending = {22: ENTRY, 30: dict(ENTRY, name="Second spool"), 23: dict(ENTRY, filament=17)}
    run = Run("gcode_macro _SPOOL_PA_PENDING_SET", {"SPOOL": "22", "DROP_FILAMENT": "16"}, printer(pending=pending))
    assert saved_pending(run) == {23: dict(ENTRY, filament=17)}


def test_offer_saves_the_spool_and_asks_with_three_choices_when_idle():
    params = {"SPOOL": "22", "FILAMENT": "16", "GATE": "1", "TEMP": "255", "FLOW": "0.965", "MATERIAL": "PETG",
              "NAME": "Sunlu Green"}
    run = Run("gcode_macro _SPOOL_PA_OFFER", params, printer())
    assert ("_SPOOL_PA_PENDING_SET", {"SPOOL": "22", "FILAMENT": "16", "TEMP": "255", "FLOW": "0.965", "MATERIAL": "PETG",
                                   "NAME": "Sunlu Green"}) in run.commands
    buttons = [args["MSG"] for cmd, args in run.commands
               if cmd == "RESPOND" and "prompt_footer_button" in args.get("MSG", "")]
    assert [b.split("|")[1] for b in buttons] == ["SPOOL_PA_CALIBRATE SPOOL=22", "_SPOOL_PA_LATER SPOOL=22",
                                                   "_SPOOL_PA_SKIP SPOOL=22"]
    assert run.commands[-1] == ("RESPOND", {"TYPE": "command", "MSG": "action:prompt_show"})


def test_offer_during_a_print_has_no_calibrate_now():
    params = {"SPOOL": "22", "GATE": "1", "TEMP": "255", "FLOW": "0.965", "MATERIAL": "PETG", "NAME": "x"}
    run = Run("gcode_macro _SPOOL_PA_OFFER", params, printer(state="printing"))
    assert not any("SPOOL_PA_CALIBRATE" in line for line in run.lines)


def test_calibrate_runs_on_the_spool_gate_with_the_material_range():
    run = Run("gcode_macro SPOOL_PA_CALIBRATE", {"SPOOL": "22"}, printer(pending={22: ENTRY}))
    assert run.commands[-1] == ("_SPOOL_PA_RUN", {"SPOOL": "22", "GATE": "1", "TEMP": "255", "FLOW": "0.965",
                                               "KSTART": "0.02", "KEND": "0.12", "KSTEP": "0.01", "APPLY": "0"})


def test_calibrate_refuses_during_a_print_unknown_spools_and_spools_out_of_the_box():
    for state, params, pending in (("printing", {"SPOOL": "22"}, {22: ENTRY}),
                                   ("standby", {"SPOOL": "22"}, {}),
                                   ("standby", {"SPOOL": "40"}, {40: ENTRY})):
        run = Run("gcode_macro SPOOL_PA_CALIBRATE", params, printer(state=state, pending=pending))
        assert "_SPOOL_PA_RUN" not in names(run)
        assert run.commands[-1][1].get("TYPE") == "error", run.lines


def test_run_loads_the_gate_and_sweeps_at_the_flow_ratio():
    params = {"SPOOL": "22", "GATE": "1", "TEMP": "255", "FLOW": "0.965", "KSTART": "0.02", "KEND": "0.12",
              "KSTEP": "0.01", "APPLY": "0"}
    run = Run("gcode_macro _SPOOL_PA_RUN", params, printer(gate=0, filament="Loaded"))
    order = names(run)
    assert order.index("MMU_UNLOAD") < order.index("MMU_SELECT") < order.index("MMU_LOAD") \
        < order.index("MOVE_TO_TRASH") < order.index("M109") < order.index("AUTOPA_SWEEP")
    assert ("MMU_SELECT", {"GATE": "1"}) in run.commands
    assert "M221 S96.5" in run.lines and run.lines.index("M221 S96.5") < order.index("AUTOPA_SWEEP")
    assert run.commands[order.index("AUTOPA_SWEEP")][1] == {"APPLY": "0", "KSTART": "0.02", "KEND": "0.12",
                                                            "KSTEP": "0.01"}
    assert order[-2:] == ["M221", "_SPOOL_PA_RESULT"]


def test_run_keeps_a_spool_already_loaded():
    params = {"SPOOL": "22", "GATE": "1", "TEMP": "255", "FLOW": "1", "KSTART": "0.02", "KEND": "0.12",
              "KSTEP": "0.01"}
    run = Run("gcode_macro _SPOOL_PA_RUN", params, printer(gate=1, filament="Loaded"))
    assert not {"MMU_UNLOAD", "MMU_SELECT", "MMU_LOAD"} & set(names(run))


def test_valid_result_is_stored_and_the_spool_leaves_the_list():
    params = {"SPOOL": "22", "KSTART": "0.02", "KEND": "0.12", "KSTEP": "0.01", "APPLY": "1"}
    run = Run("gcode_macro _SPOOL_PA_RESULT", params, printer(pending={22: ENTRY}, k_opt=0.0451))
    assert run.remote == [("q2_pa_store", {"spool_id": 22, "pa": 0.0451})]
    assert ("_SPOOL_PA_PENDING_SET", {"SPOOL": "22", "DROP_FILAMENT": "16"}) in run.commands
    assert ("SET_PRESSURE_ADVANCE", {"ADVANCE": "0.0451"}) in run.commands


def test_edge_or_missing_result_is_not_stored_and_counts_a_try():
    for k in (0.12, 0.02, None):
        params = {"SPOOL": "22", "KSTART": "0.02", "KEND": "0.12", "KSTEP": "0.01"}
        run = Run("gcode_macro _SPOOL_PA_RESULT", params, printer(pending={22: ENTRY}, k_opt=k))
        assert run.remote == []
        assert ("_SPOOL_PA_PENDING_SET", {"SPOOL": "22", "FILAMENT": "16", "TEMP": "255", "FLOW": "0.965", "MATERIAL": "PETG",
                                       "NAME": "Sunlu Green", "TRIES": "1"}) in run.commands, run.lines
        assert "SET_PRESSURE_ADVANCE" not in names(run)


def test_print_start_calibrates_used_spools_on_their_first_try_only():
    pending = {22: ENTRY, 23: dict(ENTRY, tries=1), 29: ENTRY}
    run = Run("gcode_macro _SPOOL_PA_PRINT_START", {"REFERENCED_TOOLS": "1,2", "HOTEND": "240"},
              printer(state="printing", pending=pending))
    assert [c for c in run.commands if c[0] == "SPOOL_PA_CALIBRATE"] == [
        ("SPOOL_PA_CALIBRATE", {"SPOOL": "22", "PRINT": "1", "APPLY": "0"})]
    assert names(run)[-2:] == ["MOVE_TO_TRASH", "M109"] and run.lines[-1] == "M109 S240"


def test_print_start_applies_the_value_when_the_print_uses_one_spool():
    run = Run("gcode_macro _SPOOL_PA_PRINT_START", {"REFERENCED_TOOLS": "1", "HOTEND": "240"},
              printer(state="printing", pending={22: ENTRY}))
    assert ("SPOOL_PA_CALIBRATE", {"SPOOL": "22", "PRINT": "1", "APPLY": "1"}) in run.commands


def test_print_start_does_nothing_without_pending_spools_in_use():
    for tools, pending in (("0", {22: ENTRY}), ("", {22: ENTRY}), ("1", {})):
        run = Run("gcode_macro _SPOOL_PA_PRINT_START", {"REFERENCED_TOOLS": tools, "HOTEND": "240"},
                  printer(state="printing", pending=pending))
        assert run.commands == [], run.lines


def test_print_start_macro_calibrates_before_the_initial_load():
    gcode = sections(MMU_CFG)["gcode_macro PRINT_START"]["gcode"]
    # A failed sweep leaves its flow ratio: the print starts back at 100 %
    assert gcode.index("M221 S100") < gcode.index("_SPOOL_PA_PRINT_START")
    assert gcode.index("_SPOOL_PA_PRINT_START") < gcode.index("MMU_START_LOAD_INITIAL_TOOL")
    assert gcode.index("MMU_START_SETUP") < gcode.index("_SPOOL_PA_PRINT_START")


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d pressure advance calibration tests passed" % len(tests))
