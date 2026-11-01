# Failure detection

The `detect` component watches every print through the printer camera with
[Obico](https://github.com/TheSpaghettiDetective/obico-server)'s spaghetti detector, and
can pause a print that is failing. Its page is `http://<host>/detect/`, linked from
Mainsail's sidebar.

It replaced PrintGuard: on the Q2's wide chamber camera, PrintGuard's model missed real
spaghetti and raised false alarms at print start. Obico's detector caught the same
spaghetti on every frame and stayed at 0 on those false alarms.

## How it decides

While Klipper prints, the `q2-detect` service takes a camera frame every 10 seconds and
sends it to Obico's ML API, which returns boxes around what looks like spaghetti. The
frame's raw score `p` is the sum of their confidences: 0 when nothing is seen, 1 to 2 for a
real spaghetti mess.

The decision is Obico's own, unchanged (`detect/q2_detect/obico.py`):

- the score is smoothed over the last few frames, and compared with this printer's usual
  level, learnt over every print it has watched (a fresh install learns it during the
  first prints);
- above the **warning** level it sends a warning; above the **pause** level (1.75 times
  higher) it pauses the print in pause mode, or says it would have in observe mode;
- the first 5 minutes of a print never alert;
- one alert until you acknowledge it (**Looks fine**), never two within 90 seconds, and
  **Mute for this print** silences the rest of the print. A pause happens once per print,
  with one more try if the printer still prints 90 seconds later.

A spaghetti mess like the ones seen on the Q2 raises a warning within about 20 seconds
and a pause within about 40 seconds. Small dark debris on the dark plate is hard to see
for the camera and is usually missed.

## The page

- **Live**: the state, the last analysed frame with Obico's boxes (or the live stream), the
  score against the two levels, the print's chart, and the actions.
- **History**: every watched print with its chart, its decisions with their pictures, and a
  frame every 10 minutes. Mark each decision **False alarm** or **Real failure** to see
  over time how reliable it is on your printer.
- **Settings**:
  - **Mode**: *observe* (the default) notifies only; *pause* also pauses the print. Start
    in observe mode for a few prints.
  - **Sensitivity**: low (0.8), normal (1.0) or high (1.2) multiplies the score.
  - **Notifications**: [Apprise URLs](https://github.com/caronc/apprise/wiki), the same as
    Moonraker's `[notifier]`, with the picture attached if you want. For example:
    - `ntfy://ntfy.sh/your-topic`
    - `tgram://bot-token/chat-id` (Telegram)
    - `discord://webhook-id/webhook-token`
    - `pover://user-key@app-token` (Pushover)
    - `hassio://homeassistant.local/long-lived-token` (Home Assistant)
  - **Keep prints**: how many prints the history keeps (50 by default).

Warnings and pauses also show in the Mainsail / Fluidd console.

## What runs where

| Part | Where | Notes |
|---|---|---|
| `q2-detect` | systemd service, `~/q2-detect-env`, code in `detect/` | port 7130 on localhost, served by nginx at `/detect/api/`; nice 10 |
| Obico's ML API | Docker container `obico-ml-api`, host network | port 3333 on localhost only; built on the host from obico-server's `ml_api/Containerfile.cpu` at the commit pinned in `VERSIONS`; one CPU at the lowest weight; about 1 GB of image |
| Data | `~/printer_data/detect/` | settings, the printer's usual level, and one folder per print |

Frames never leave the host. Obico's model is downloaded from obico.io when the image is
built, not redistributed by q2-offload.

## Troubleshooting

- `./install.sh check` checks the service, the ML API and the page.
- `systemctl status q2-detect` and `journalctl -u q2-detect -f` show what the service does.
- `sudo docker logs obico-ml-api` shows the ML API.
- The page names the problem: ML API down, camera not reachable, or no webcam in
  Moonraker (the frames come from the first webcam with a snapshot URL, `[webcam q2]` in
  `moonraker.conf`).

## Coming from PrintGuard

The first update after PrintGuard was replaced removes its container and switches the
component to `detect`. PrintGuard's data stays in `/srv/printguard` (remove it with
`sudo rm -r /srv/printguard` once you no longer need it).

## API

The page uses the service's HTTP API at `/detect/api/`: `status` and `events` (Server-Sent
Events) for the live state, `prints` for the history, `settings`, `ack`, `mute` and
`notify/test`. `detect/q2_detect/api.py` lists every route.
