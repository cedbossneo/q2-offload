#!/usr/bin/env python3
"""Write the active bed mesh as a [bed_mesh PLR_JOB] profile for power-loss resume.
Klipper loses an unsaved profile on restart and SAVE_CONFIG would restart it mid-print.
The old file goes first: a failure must leave no mesh rather than another job's mesh."""
import json
import os
import pathlib
import sys
import urllib.request

URL = os.environ.get("PLR_MOONRAKER", "http://localhost:7125") + "/printer/objects/query?bed_mesh=profile_name,profiles"
TARGET = pathlib.Path(os.environ.get("PLR_MESH_FILE", "@HOME@/printer_data/config/plr_mesh.cfg"))
PROFILE_VERSION = 1
ADAPTIVE_PROFILE = "ADAPTIVE"


def render(profile):
    rows = "".join("\n  " + ", ".join("%.6f" % z for z in row) for row in profile["points"])
    params = "".join("%s = %s\n" % item for item in profile["mesh_params"].items())
    return "[bed_mesh PLR_JOB]\nversion = %d\npoints =%s\n%s" % (PROFILE_VERSION, rows, params)


def main():
    TARGET.unlink(missing_ok=True)
    with urllib.request.urlopen(URL, timeout=10) as response:
        mesh = json.load(response)["result"]["status"]["bed_mesh"]
    # An adaptive mesh is active under a generated name; PRINT_START saves it as ADAPTIVE
    profile = mesh["profile_name"] and mesh["profiles"].get(mesh["profile_name"], mesh["profiles"].get(ADAPTIVE_PROFILE))
    if not profile:
        print("PLR: no bed mesh profile active, resume will need a new one")
        return 1
    temporary = TARGET.with_suffix(".tmp")
    temporary.write_text(render(profile))
    temporary.replace(TARGET)
    print("PLR: saved mesh %s" % mesh["profile_name"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
