"""Run plr_save_mesh.py against a fake Moonraker and read the file back the way Klipper does.
Usage: python3 tests/macros/test_plr_mesh.py"""
import configparser
import http.server
import json
import os
import pathlib
import subprocess
import tempfile
import threading

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "config/plr/plr_save_mesh.py"
PARAMS = {"min_x": 40.5, "max_x": 200.0, "min_y": 10.0, "max_y": 260.0, "x_count": 2, "y_count": 2,
          "mesh_x_pps": 2, "mesh_y_pps": 2, "algo": "lagrange", "tension": 0.2}
POINTS = [[0.1, -0.2], [0.03, 0.04]]


def run(mesh, existing=None):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"result": {"status": {"bed_mesh": mesh}}}).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        target = pathlib.Path(tmp) / "plr_mesh.cfg"
        if existing:
            target.write_text(existing)
        env = dict(os.environ, PLR_MOONRAKER="http://127.0.0.1:%d" % server.server_port, PLR_MESH_FILE=str(target))
        code = subprocess.run(["python3", str(SCRIPT)], env=env, capture_output=True).returncode
        server.shutdown()
        return code, target.read_text() if target.exists() else None


def test_active_profile_is_written_in_klipper_format():
    code, text = run({"profile_name": "ADAPTIVE", "profiles": {"ADAPTIVE": {"points": POINTS, "mesh_params": PARAMS}}})
    cfg = configparser.RawConfigParser()
    cfg.read_string(text)
    section = cfg["bed_mesh PLR_JOB"]
    rows = [[float(z) for z in row.split(",")] for row in section["points"].strip().splitlines()]
    assert code == 0 and rows == POINTS and section.getint("version") == 1
    assert section.getfloat("min_x") == 40.5 and section["algo"] == "lagrange"


def test_adaptive_mesh_is_found_through_its_saved_profile():
    code, text = run({"profile_name": "adaptive-773EEE7C6260", "profiles": {"ADAPTIVE": {"points": POINTS, "mesh_params": PARAMS}}})
    assert code == 0 and "[bed_mesh PLR_JOB]" in text


def test_old_profile_is_not_used_without_an_active_mesh():
    code, text = run({"profile_name": "", "profiles": {"ADAPTIVE": {"points": POINTS, "mesh_params": PARAMS}}})
    assert code == 1 and text is None


def test_no_mesh_leaves_no_stale_file():
    code, text = run({"profile_name": "", "profiles": {}}, existing="[bed_mesh PLR_JOB]\n")
    assert code == 1 and text is None


if __name__ == "__main__":
    tests = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    for test in tests:
        test()
    print("%d PLR mesh tests passed" % len(tests))
