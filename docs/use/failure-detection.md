---
title: Failure detection
description: The camera watches every print for spaghetti, warns you, and can pause it.
---

While the printer prints, the host looks at a camera frame every 10 seconds with
[Obico](https://github.com/TheSpaghettiDetective/obico-server)'s spaghetti detector. When it
sees a print failing, it warns you, and it can pause the print. Everything runs on your host:
the frames never leave it.

Its page is `http://<host>/detect/`, linked from Mainsail's sidebar.

## Set it up

1. **Start in observe mode** (the default) for a few prints: it only notifies, so you see how
   it behaves on your printer before letting it pause anything.
2. **Add notifications** in **Settings → Notifications**, with
   [Apprise URLs](https://github.com/caronc/apprise/wiki) (the picture can be attached):
   - `ntfy://ntfy.sh/your-topic`
   - `tgram://bot-token/chat-id` (Telegram)
   - `discord://webhook-id/webhook-token`
   - `pover://user-key@app-token` (Pushover)
   - `hassio://homeassistant.local/long-lived-token` (Home Assistant)
3. **Switch to pause mode** once you trust it.

## How it decides

The decision rules are Obico's own:

- each frame gets a score; it is smoothed over the last few frames and compared with your
  printer's usual level, learnt over the prints it has watched;
- above the **warning** level it sends a warning; above the **pause** level it pauses the
  print in pause mode, or says it would have in observe mode;
- the first 5 minutes of a print never alert;
- one alert until you acknowledge it (**Looks fine**), never two within 90 seconds; **Mute for
  this print** silences the rest of the print.

A spaghetti mess raises a warning within about 20 seconds and a pause within about 40. Small
dark debris on the dark plate is hard for the camera to see, and usually missed.

## The page

- **Live**: the state, the last frame with what was detected, the score against the two
  levels, and the actions.
- **History**: every watched print, its decisions with their pictures, and a frame every 10
  minutes. Mark each decision **False alarm** or **Real failure** to see how reliable it is on
  your printer.
- **Settings**: mode, sensitivity (low, normal or high), notifications, and how many prints
  the history keeps (50).

Warnings and pauses also show in the Mainsail and Fluidd console.

<details>
<summary>It doesn't work</summary>

- `./install.sh check` checks the service, the detector and the page.
- `systemctl status q2-detect` and `journalctl -u q2-detect -f` show what the service does.
- `sudo docker logs obico-ml-api` shows the detector.
- The page names the problem: detector down, camera not reachable, or no webcam in Moonraker
  (frames come from the first webcam with a snapshot URL, `[webcam q2]` in `moonraker.conf`).

</details>

How it runs on the host (Intel GPU or CPU, ports, data, API) is in the
[failure detection reference](../reference/failure-detection.md).
