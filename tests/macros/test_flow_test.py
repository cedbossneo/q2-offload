"""The decisions of scripts/flow-test.py that don't need a printer: the result, the next step
under the force limit, and the progress sent to a dialog.
Usage: python3 tests/macros/test_flow_test.py"""
import importlib.util
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
spec = importlib.util.spec_from_file_location("flow_test", ROOT / "scripts/flow-test.py")
ft = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ft)


def step(flow, force, complete=True, flags=()):
    return {"flow": flow, "force": force, "complete": complete, "flags": list(flags)}


STEPS = [step(4, 349), step(6, 508), step(8, 647), step(10, 801), step(18, 1495),
         step(19, 1535, complete=False, flags=["stopped"])]


def test_max_is_the_last_good_step_and_the_recommendation_keeps_a_margin():
    max_flow, recommended, at_least = ft.results(ft.Stop("force", "x"), STEPS)
    assert (max_flow, recommended, at_least) == (18, 16.0, False)       # 0.9 x 18 = 16.2 -> 16.0
    max_flow, recommended, at_least = ft.results(ft.Stop("limit", "x"),
                                                 STEPS[:4] + [step(12, 1400, flags=["knee"])])
    assert (max_flow, recommended) == (10, 9.0)


def test_end_of_the_ramp_gives_a_lower_bound_and_errors_give_nothing():
    assert ft.results(ft.Stop("end", "x"), STEPS[:4]) == (10, 9.0, True)
    assert ft.results(ft.Stop("error", "x"), STEPS) == (None, None, False)
    assert ft.results(ft.Stop("force", "x"), []) == (None, None, False)


def test_steps_shrink_as_the_force_nears_the_limit():
    args = types.SimpleNamespace(step=2)
    assert ft.next_flow([step(4, 170), step(6, 280)], args, 2000) == 8.0
    near = [step(16, 1240), step(18, 1450)]
    nxt = ft.next_flow(near, args, 2000)
    assert nxt is not None and 18 < nxt < 20             # less than a full step (20)
    assert ft.next_flow([step(18, 1700), step(19, 1790)], args, 2000) is None


def test_progress_goes_to_the_dialog_without_breaking_the_command():
    sent = []
    ft.gcode = sent.append
    ft.notify(types.SimpleNamespace(status='_SPOOL_PA_STATUS SPOOL=22 TITLE="Max flow"'), 'Heating "220" C; #1')
    assert sent == ['_SPOOL_PA_STATUS SPOOL=22 TITLE="Max flow" STEP="Heating 220 C 1"']
    sent.clear()
    ft.notify(types.SimpleNamespace(status=""), "Priming")
    assert sent == []


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d flow test checks passed" % len(tests))
