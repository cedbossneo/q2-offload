---
title: Failure detection internals
description: What runs where, the Intel GPU and CPU images, and the service's API.
---

How to use it: [Failure detection](../use/failure-detection.md).

## What runs where

| Part | Where | Notes |
|---|---|---|
| `q2-detect` | systemd service, `~/q2-detect-env`, code in `detect/` | port 7130 on localhost, served by nginx at `/detect/api/`; nice 10 |
| Obico's ML API | Docker container `obico-ml-api`, host network | port 3333 on localhost only; on the Intel GPU when there is one, else on one CPU core; lowest CPU weight; about 1 GB on disk |
| Data | `~/printer_data/detect/` | settings, the printer's usual level, and one folder per print |

While Klipper prints, `q2-detect` takes a camera frame every 10 seconds and sends it to the ML
API, which returns boxes around what looks like spaghetti. The frame's raw score is the sum of
their confidences: 0 when nothing is seen, 1 to 2 for a real mess. The decision is Obico's own,
unchanged (`detect/q2_detect/obico.py`); the pause level is 1.75 times the warning level. A
pause happens once per print, with one more try if the printer still prints 90 seconds later.

Sensitivity low, normal and high multiply the score by 0.8, 1.0 and 1.2.

Frames never leave the host. A new ML API reaches users through the daily upstream update, once
CI has run it.

## Intel GPU or CPU

The installer picks the ML API image for the host:

- **x86_64 with an Intel GPU** (most mini PCs: N100, N5095, NUC…): q2-offload's build,
  `ghcr.io/cedbossneo/q2-offload/obico-ml-api-intel`. It is the same obico-server commit and the
  same model, with ONNX Runtime's OpenVINO provider, so the model runs on the GPU. CI builds it
  from `detect/ml-api/Containerfile.intel` and runs it before publishing it. The first start
  compiles the model for the GPU (about 20 s, up to 1.1 GB of memory); a Docker volume
  (`q2-openvino-cache`) keeps the result, so later starts take a few seconds.
- **Anything else** (arm64, no Intel GPU, or the GPU image doesn't start): Obico's own image,
  `ghcr.io/thespaghettidetective/obico-ml-api-cpu`, pinned by digest in `VERSIONS`.

On a Celeron N5095 the model takes about 6 s of CPU per frame with a one-CPU quota (ONNX
Runtime's threads wait on each other), 2 s on one dedicated core, and 0.13 s on the GPU with
the same detections. The container therefore gets one core (the last one) at the lowest weight,
rather than a CPU quota. The installer says which image it started ("Obico ML API on the Intel
GPU" or "Obico ML API (CPU)").

## API

The page uses the service's HTTP API at `/detect/api/`: `status` and `events` (Server-Sent
Events) for the live state, `prints` for the history, `settings`, `ack`, `mute` and
`notify/test`. `detect/q2_detect/api.py` lists every route.
