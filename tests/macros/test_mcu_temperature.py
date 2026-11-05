"""Check the main board and toolhead MCU temperatures are configured and visible in the clients
(a leading underscore would hide them). Usage: python3 tests/macros/test_mcu_temperature.py"""
import configparser
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def sensors():
    cfg = configparser.RawConfigParser(strict=False)
    cfg.read(ROOT / "config/klipper/q2_mainline_helpers.cfg")
    return {name.split()[1]: dict(cfg[name]) for name in cfg.sections() if name.startswith("temperature_sensor ")}


def test_main_board_and_toolhead_mcu_sensors_are_configured():
    found = sensors()
    assert found["Mainboard_MCU"] == {"sensor_type": "temperature_mcu"}
    assert found["Toolhead_MCU"] == {"sensor_type": "temperature_mcu", "sensor_mcu": "THR"}


def test_sensors_are_visible_in_the_clients():
    assert not [name for name in sensors() if name.startswith("_")]


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d MCU temperature tests passed" % len(tests))
