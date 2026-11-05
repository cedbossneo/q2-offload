"""Check when the link watchdog steps in. Usage: python3 tests/macros/test_link_watch.py"""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("watch", ROOT / "host/q2-link-watch.py")
watch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(watch)


def act(state, message="", printer_up=True, seconds=0, attempts=0):
    return watch.next_action(state, message, printer_up, seconds, attempts)


def test_connection_error_restarts_the_link_then_the_proxies():
    assert act("error", "mcu 'mcu': Unable to connect") == "link"
    assert act("shutdown", "Lost communication with MCU 'THR'", attempts=1) == "full"


def test_faults_a_person_must_see_are_left_alone():
    for message in ("Heater extruder not heating at expected rate", "MCU 'mcu' shutdown: ADC out of range",
                    "Option 'x' is not valid in section 'y'", ""):
        assert act("shutdown", message) is None and act("error", message) is None


def test_nothing_while_the_printer_is_off():
    assert act("error", "mcu 'mcu': Unable to connect", printer_up=False) is None


def test_startup_gets_time_to_connect():
    assert act("startup", seconds=30) is None
    assert act("startup", seconds=watch.STARTUP_GRACE_SECONDS) == "link"


def test_a_working_printer_is_left_alone():
    assert act("ready", seconds=9999) is None


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d link watch tests passed" % len(tests))
