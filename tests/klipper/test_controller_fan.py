"""Apply the Klipper patch to controller_fan.py and drive its callback with fakes: the fan follows
steppers, heater targets and temperature limits. Usage: python3 tests/klipper/test_controller_fan.py <klipper tree>"""
import importlib.util
import pathlib
import sys
import types


class FakeFan:
    def __init__(self, config):
        self.speed = 0.

    def set_speed(self, speed):
        self.speed = speed

    def get_status(self, eventtime):
        return {"speed": self.speed}


class Sensor:
    def __init__(self, temperature):
        self.temperature = temperature

    def get_status(self, eventtime):
        return {"temperature": self.temperature}


class Stepper:
    enabled = False

    def is_motor_enabled(self):
        return self.enabled


class Enable:
    def __init__(self):
        self.stepper = Stepper()

    def lookup_enable(self, name):
        return self.stepper

    def get_steppers(self):
        return ["stepper_z"]


class Heater:
    target = 0.

    def get_temp(self, eventtime):
        return 20., self.target


class Printer:
    def __init__(self, objects):
        self.objects = objects
        self.objects["heaters"].lookup_heater = lambda name: self.objects["extruder"]

    def register_event_handler(self, name, callback):
        pass

    def load_object(self, config, name):
        return self.objects[name]

    def lookup_object(self, name, default=None):
        return self.objects.get(name, default)

    def config_error(self, message):
        return ValueError(message)


class Config:
    error = ValueError

    def __init__(self, printer, limits):
        self.printer, self.limits = printer, limits

    def get_printer(self):
        return self.printer

    def get_name(self):
        return "controller_fan board_fan"

    def getfloat(self, name, default=None, **kw):
        return {"fan_speed": 1., "idle_speed": 1.}.get(name, default)

    def getint(self, name, default=None, **kw):
        return {"idle_timeout": 2}.get(name, default)

    def getlist(self, name, default=None):
        return {"stepper": ["stepper_z"], "temperature_limits": self.limits}.get(name, default)


def load(tree):
    package = types.ModuleType("extras")
    package.__path__ = []
    package.fan = types.SimpleNamespace(Fan=FakeFan)
    sys.modules["extras"], sys.modules["extras.fan"] = package, package.fan
    path = pathlib.Path(tree) / "klippy/extras/controller_fan.py"
    spec = importlib.util.spec_from_file_location("extras.controller_fan", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def setup(module, limits=("temperature_sensor Mainboard_MCU:45", "heater_generic chamber:40")):
    objects = {"stepper_enable": Enable(), "heaters": types.SimpleNamespace(), "extruder": Heater(),
               "temperature_sensor Mainboard_MCU": Sensor(25.), "heater_generic chamber": Sensor(25.)}
    fan = module.ControllerFan(Config(Printer(objects), limits))
    fan.handle_connect()
    return fan, objects


def ticks(fan, count=1):
    for _ in range(count):
        fan.callback(0.)
    return fan.fan.speed


def run(module):
    fan, _ = setup(module)
    assert ticks(fan, 5) == 0., "cold and idle: fan off"

    fan, objects = setup(module)
    objects["stepper_enable"].stepper.enabled = True
    assert ticks(fan) == 1., "enabled stepper: fan on"

    fan, objects = setup(module)
    objects["temperature_sensor Mainboard_MCU"].temperature = 45.
    assert ticks(fan) == 1., "main board at its limit: fan on with motors off"

    fan, objects = setup(module)
    objects["heater_generic chamber"].temperature = 60.
    assert ticks(fan) == 1., "hot chamber without target: fan on"
    objects["heater_generic chamber"].temperature = 30.
    assert ticks(fan, 2) == 1., "idle timeout still applies once it cools"
    assert ticks(fan) == 0., "then the fan stops"

    fan, objects = setup(module)
    objects["heater_generic chamber"].temperature = None
    assert ticks(fan) == 0., "a sensor without value is ignored"

    for bad in (("no limit here",), ("temperature_sensor Mainboard_MCU:hot",)):
        try:
            setup(module, bad)
        except ValueError:
            continue
        raise AssertionError("invalid limit accepted: %s" % (bad,))
    try:
        setup(module, ("temperature_sensor Missing:45",))
    except ValueError:
        pass
    else:
        raise AssertionError("unknown sensor accepted")

    fan, _ = setup(module, ())
    assert ticks(fan, 3) == 0., "without the option nothing changes"


if __name__ == "__main__":
    run(load(sys.argv[1]))
    print("controller_fan tests passed")
