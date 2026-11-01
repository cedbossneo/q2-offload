#!/usr/bin/env bash
# CI for failure detection: build Obico's ML API as the installer does (build_obico_ml_api),
# install q2-detect's requirements in a venv like host_detect_env, and run the end-to-end test
# on a plain frame (the ML API must answer and frames must be analysed; no failure to find).
# Usage: tests/detect/ci.sh
set -Eeuo pipefail
# shellcheck source=../../scripts/lib.sh
. "$(dirname "$0")/../../scripts/lib.sh"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT
image=q2-offload/obico-ml-api:ci

info "Building Obico's ML API at ${OBICO_SERVER_REF:0:12}"
obico_ml_api_source "${work}/src"
build_obico_ml_api "${work}/src" "$image"
python3 -m venv "${work}/env"
"${work}/env/bin/pip" install -q -r "${Q2_ROOT}/detect/requirements.txt"
"${work}/env/bin/python" -c 'import sys; from PIL import Image; Image.new("RGB", (1280, 720), (90, 90, 90)).save(sys.argv[1])' \
    "${work}/frame.jpg"
PYTHON="${work}/env/bin/python" "${Q2_ROOT}/tests/detect/e2e.sh" "$image" "${work}/frame.jpg"
