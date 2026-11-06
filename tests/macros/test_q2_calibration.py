"""The q2_calibration Moonraker component (host/components/q2_calibration.py) against a fake
Moonraker, Spoolman and OrcaSlicer profile library.
Usage: python3 tests/macros/test_q2_calibration.py"""
import asyncio
import importlib.util
import json
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("q2_calibration", ROOT / "host/components/q2_calibration.py")
comp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comp)

# OrcaSlicer's library, as profile_loader would return it (inherits resolved by flatten)
PROFILES = {
    "fdm_filament_common": {"nozzle_temperature": ["200"], "filament_flow_ratio": ["1"]},
    "Generic PETG @System": {"inherits": "fdm_filament_common", "nozzle_temperature": ["255"],
                             "filament_flow_ratio": ["0.95"]},
    "Generic PLA @System": {"inherits": "fdm_filament_common", "nozzle_temperature": ["220"],
                            "filament_flow_ratio": ["0.98"]},
}


def load(name):
    return PROFILES[name]


def spool(spool_id=22, material="PETG", temp: "int | None" = 255, extra=None, vendor="Sunlu", name="Green #2"):
    return {"id": spool_id, "filament": {
        "id": 16, "name": name, "material": material, "settings_extruder_temp": temp,
        "vendor": {"name": vendor}, "extra": extra or {}}}


class Response:
    def __init__(self, payload=None, status=200):
        self.payload, self.status_code = payload, status
        self.error = None if status < 400 else "HTTP %d" % status

    def has_error(self):
        return self.error is not None

    def json(self):
        return self.payload


class FakeSpoolman:
    def __init__(self, spools, fields=()):
        self.spools = {s["id"]: s for s in spools}
        self.fields = list(fields)
        self.requests = []

    async def get(self, url):
        self.requests.append(("GET", url, None))
        if url.endswith("/v1/field/filament"):
            return Response([{"key": k} for k in self.fields])
        sid = int(url.rsplit("/", 1)[1])
        return Response(self.spools[sid]) if sid in self.spools else Response(status=404)

    async def post(self, url, body=None):
        self.requests.append(("POST", url, body))
        self.fields.append(url.rsplit("/", 1)[1])
        return Response({})

    async def request(self, method, url, body=None):
        self.requests.append((method, url, body))
        return Response({})


class FakeKlippy:
    def __init__(self):
        self.gcode = []

    async def run_gcode(self, script):
        self.gcode.append(script)
        return "ok"


class FakeLoop:
    def __init__(self):
        self.tasks = []

    def create_task(self, coro):
        self.tasks.append(asyncio.ensure_future(coro))

    async def run_in_thread(self, fn, *args):
        return fn(*args)


class FakeServer:
    def __init__(self, http, data_path):
        self.components = {"http_client": http, "klippy_apis": FakeKlippy(),
                           "spoolman": type("S", (), {"spoolman_url": "http://sm/api"})()}
        self.data_path, self.loop, self.remote, self.events = data_path, FakeLoop(), {}, {}

    def lookup_component(self, name):
        return self.components[name]

    def get_app_args(self):
        return {"data_path": self.data_path}

    def register_remote_method(self, name, cb):
        self.remote[name] = cb

    def register_event_handler(self, name, cb):
        self.events[name] = cb

    def get_event_loop(self):
        return self.loop


def component(spools, fields=()):
    http = FakeSpoolman(spools, fields)
    server = FakeServer(http, tempfile.mkdtemp())
    config = type("C", (), {"get_server": lambda self: server})()
    q2 = comp.load_component(config)
    q2._settings = lambda s: comp.print_settings(s, q2.presets, load)
    return q2, server, http


def run(server, name, **kwargs):
    async def go():
        await server.remote[name](**kwargs)
        await asyncio.gather(*server.loop.tasks)
    server.loop.tasks = []
    asyncio.run(go())


def test_settings_follow_the_preset_the_slicer_prints_with():
    presets = comp.load_presets_module()
    plain = comp.print_settings(spool(temp=250), presets, load)
    assert plain == {"temperature": 250, "flow_ratio": 0.95, "pressure_advance": None, "material": "PETG"}
    tuned = comp.print_settings(spool(extra={"orca_filament_flow_ratio": "0.965", "orca_pressure_advance": '"0.04"'}),
                                presets, load)
    assert tuned["flow_ratio"] == 0.965 and tuned["pressure_advance"] == 0.04


def test_new_filament_gets_an_offer_with_its_temperature_and_flow_ratio():
    q2, server, http = component([spool(extra={"orca_filament_flow_ratio": "0.965"})])
    run(server, "q2_pa_spool_created", spool_id=22, gate=1)
    assert server.components["klippy_apis"].gcode == [
        '_SPOOL_PA_OFFER SPOOL=22 FILAMENT=16 GATE=1 TEMP=255 FLOW=0.965 MATERIAL="PETG" NAME="Sunlu Green 2"']


def test_a_filament_already_measured_is_reused():
    q2, server, http = component([spool(extra={"orca_pressure_advance": '"0.0451"'})])
    run(server, "q2_pa_spool_created", spool_id=22, gate=1)
    gcode = server.components["klippy_apis"].gcode
    assert len(gcode) == 1 and gcode[0].startswith("RESPOND") and "0.0451 already measured" in gcode[0]


def test_no_temperature_or_unknown_spool_means_no_offer():
    q2, server, http = component([spool(material="XYZ", temp=None)])
    run(server, "q2_pa_spool_created", spool_id=22, gate=1)
    run(server, "q2_pa_spool_created", spool_id=99, gate=1)
    gcode = server.components["klippy_apis"].gcode
    assert len(gcode) == 2 and all(g.startswith("RESPOND") for g in gcode), gcode


def test_store_writes_the_filament_and_creates_missing_fields():
    q2, server, http = component([spool()], fields=["orca_filament_flow_ratio"])
    run(server, "q2_pa_store", spool_id=22, pa=0.04512)
    posts = [url.rsplit("/", 1)[1] for method, url, _ in http.requests if method == "POST"]
    assert posts == ["orca_pressure_advance", "orca_enable_pressure_advance"]
    patch = [(url, body) for method, url, body in http.requests if method == "PATCH"]
    assert patch == [("http://sm/api/v1/filament/16",
                      {"extra": {"orca_pressure_advance": json.dumps("0.0451"),
                                 "orca_enable_pressure_advance": json.dumps("1")}})]
    assert "0.0451 saved" in server.components["klippy_apis"].gcode[-1]


def test_klippy_ready_turns_the_offers_on():
    q2, server, http = component([])
    asyncio.run(server.events["server:klippy_ready"]())
    assert server.components["klippy_apis"].gcode == [
        "SET_GCODE_VARIABLE MACRO=_SPOOL_PA_VARS VARIABLE=enabled VALUE=True"]


def test_names_cannot_break_a_gcode_command():
    assert comp.quote('A "b" #1; c*') == "A b 1 c"


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d q2_calibration tests passed" % len(tests))
