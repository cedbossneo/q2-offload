"""Drive Heater.set_pwm of the patched heaters.py with fakes. Usage:
python3 tests/klipper/test_heater_soft_start.py <klipper tree>"""
import importlib.util
import pathlib
import sys


class Pwm:
    def __init__(self):
        self.values = []

    def set_pwm(self, time, value):
        self.values.append(value)


def load(tree):
    spec = importlib.util.spec_from_file_location("heaters", pathlib.Path(tree) / "klippy/extras/heaters.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def heater(module, soft_start_time):
    item = module.Heater.__new__(module.Heater)
    item.target_temp = 60.
    item.verify_mainthread_time = 1e9
    item.next_pwm_time = 0.
    item.last_pwm_value = 0.
    item.min_pwm_change = 0.01
    item.pwm_delay = 0.01
    item.max_power = 1.
    item.soft_start_time = soft_start_time
    item.soft_start_power = 0.3
    item.soft_start_begin = None
    item.mcu_pwm = Pwm()
    return item


def run(module):
    item = heater(module, 5.)
    item.set_pwm(10., 1.)
    item.set_pwm(14.9, 1.)
    item.set_pwm(15.1, 1.)
    # Limited for 5 s (the 14.9 s value is the keep-alive refresh), then full power
    assert item.mcu_pwm.values == [0.3, 0.3, 1.], item.mcu_pwm.values
    # Limited again after the heater turned off
    item.set_pwm(20., 0.)
    item.set_pwm(21., 1.)
    assert item.mcu_pwm.values[-1] == 0.3
    # Off by default
    plain = heater(module, 0.)
    plain.set_pwm(10., 1.)
    assert plain.mcu_pwm.values == [1.]


if __name__ == "__main__":
    run(load(sys.argv[1]))
    print("heater soft start tests passed")
