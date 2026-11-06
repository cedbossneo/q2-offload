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
    assert plain == {"temperature": 250, "flow_ratio": 0.95, "pressure_advance": None, "max_flow": None,
                     "material": "PETG"}
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
    assert posts == ["orca_pressure_advance", "orca_enable_pressure_advance", "orca_filament_max_volumetric_speed"]
    patch = [(url, body) for method, url, body in http.requests if method == "PATCH"]
    assert patch == [("http://sm/api/v1/filament/16",
                      {"extra": {"orca_pressure_advance": json.dumps("0.0451"),
                                 "orca_enable_pressure_advance": json.dumps("1")}})]
    assert server.components["klippy_apis"].gcode[-1] == (
        '_SPOOL_PA_NOTICE ERROR=0 TITLE="Pressure advance saved" MSG="Sunlu Green 2: pressure advance 0.0451 '
        'saved in Spoolman. OrcaSlicer presets follow within a minute"')


def test_a_failed_save_shows_an_error_notice():
    q2, server, http = component([])
    run(server, "q2_pa_store", spool_id=99, pa=0.04)
    last = server.components["klippy_apis"].gcode[-1]
    assert last.startswith('_SPOOL_PA_NOTICE ERROR=1 TITLE="Pressure advance not saved" MSG="Spool 99: 0.0400')


def test_klippy_ready_turns_the_offers_on():
    q2, server, http = component([])
    asyncio.run(server.events["server:klippy_ready"]())
    assert server.components["klippy_apis"].gcode == [
        "SET_GCODE_VARIABLE MACRO=_SPOOL_PA_VARS VARIABLE=enabled VALUE=True"]


FLOW_OK = ("...steps...\n" + comp.FLOW_RESULT_PREFIX + json.dumps({
    "max_flow": 18.8, "recommended": 16.5, "at_least": False, "stop": "force",
    "message": "the next step could pass 1800 g", "highest_force": 1575}) + "\n")


def flow_component(output=FLOW_OK, **extra):
    q2, server, http = component([spool(**extra)], fields=list(comp.NEW_FIELDS))
    calls = []

    async def fake_run(temp, status):
        calls.append((temp, status))
        return output
    q2._run_flow_test = fake_run
    return q2, server, http, calls


def test_flow_prepares_the_spool_runs_the_test_and_saves_the_recommended_speed():
    q2, server, http, calls = flow_component()
    run(server, "q2_flow_calibrate", spool_id=22, gate=1, then_pa=0)
    gcode = server.components["klippy_apis"].gcode
    assert gcode[0] == '_SPOOL_PREPARE SPOOL=22 GATE=1 TEMP=255 TITLE="Max flow" NAME="Sunlu Green 2"'
    assert calls == [(255, '_SPOOL_PA_STATUS SPOOL=22 TITLE="Max flow" NAME="Sunlu Green 2"')]
    patch = [(url, body) for method, url, body in http.requests if method == "PATCH"]
    assert patch == [("http://sm/api/v1/filament/16",
                      {"extra": {"orca_filament_max_volumetric_speed": json.dumps("16.5")}})]
    assert "_SPOOL_PA_WIPE TEMP=255\nM104 S0" in gcode
    assert gcode[-1].startswith('_SPOOL_PA_NOTICE ERROR=0 TITLE="Max flow saved" MSG="Sunlu Green 2: max '
                                'volumetric speed 16.5 mm3/s saved in Spoolman (max flow 18.8 mm3/s, the force')


def test_flow_then_pressure_advance_sweeps_under_the_max():
    q2, server, http, calls = flow_component()
    run(server, "q2_flow_calibrate", spool_id=22, gate=1, then_pa=1)
    gcode = server.components["klippy_apis"].gcode
    assert gcode[-1] == "SPOOL_PA_CALIBRATE SPOOL=22 VFR=13.2"
    assert not any(g.startswith(("_SPOOL_PA_NOTICE", "_SPOOL_PA_WIPE")) for g in gcode), gcode


def test_a_failed_flow_test_is_shown_and_still_lets_pressure_advance_run():
    q2, server, http, calls = flow_component(output="Priming\nNo data from the load cell stream.\n")
    run(server, "q2_flow_calibrate", spool_id=22, gate=1, then_pa=0)
    gcode = server.components["klippy_apis"].gcode
    assert not [m for m, *_ in http.requests if m == "PATCH"]
    assert gcode[-1] == ('_SPOOL_PA_NOTICE ERROR=1 TITLE="Max flow not measured" MSG="Sunlu Green 2: max flow '
                         'not measured (No data from the load cell stream.)"')
    q2, server, http, calls = flow_component(output="garbage")
    run(server, "q2_flow_calibrate", spool_id=22, gate=1, then_pa=1)
    assert server.components["klippy_apis"].gcode[-1] == "SPOOL_PA_CALIBRATE SPOOL=22"


def test_one_flow_test_at_a_time():
    q2, server, http, calls = flow_component()
    q2._flow_busy = True
    run(server, "q2_flow_calibrate", spool_id=22, gate=1, then_pa=0)
    gcode = server.components["klippy_apis"].gcode
    assert len(gcode) == 1 and "already running" in gcode[0] and calls == []


def test_pressure_advance_flow_after_a_max_flow_test():
    assert comp.pa_flow(None) is None and comp.pa_flow(0) is None
    assert comp.pa_flow(16.5) == 13.2 and comp.pa_flow(30) == comp.PA_MAX_VFR
    assert comp.parse_flow_result("x\n" + comp.FLOW_RESULT_PREFIX + "{bad") is None


def test_names_cannot_break_a_gcode_command():
    assert comp.quote('A "b" #1; c*') == "A b 1 c"


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d q2_calibration tests passed" % len(tests))
