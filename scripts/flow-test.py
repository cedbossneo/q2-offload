#!/usr/bin/env python3
"""Max flow test: the highest volumetric flow (mm³/s) the printer sustains with a filament,
measured with the load cell, without pushing the extruder hard.

The hotend extrudes in the air over the chute, in steps of increasing flow, and the load cell
measures the force the filament pushes with. While the hotend melts the filament fully, the
force rises in step with the flow. Past the knee the filament no longer melts fully: the force
climbs much faster, then the extruder skips. The max flow is the last step before the knee, or
before the force would pass the limit, whichever comes first; the recommended max volumetric
speed for the slicer keeps RECOMMEND_SHARE of it.

Protecting the extruder gears and motor (--max-force, default 2000 g):
- before each step, the next flow is chosen so that a force rising PESSIMISM times faster than
  so far still stays under CEILING of the limit: steps shrink as the force gets closer, and the
  ramp ends when the next one would be too small;
- while extruding, Klipper's raw load cell stream (640 samples/s, about 0.1 s late) is checked
  every 50 ms. The extrusion goes out in 0.25 s pieces, at most QUEUE_AHEAD_S ahead of the
  printer, so a stop takes effect within HORIZON_S. The test stops as soon as the force plus its
  rise over that time would pass CEILING of the limit, when the extruder skips, when the melt
  can't keep up, when the hotend can't hold its temperature, and when the load cell data stops;
- what is already sent can't be taken back: a sudden jam could still overshoot. With
  --emergency-stop, reaching the limit itself shuts Klipper down at once (FIRMWARE_RESTART after).

Run it on the host, filament loaded, printer idle:  python3 flow-test.py --temp 220
Results: ~/printer_data/logs/flow-test-<time>.txt, data in -force.csv and -status.csv."""
import argparse
import collections
import csv
import json
import math
import os
import statistics
import time

from loadcell import (FILAMENT_AREA, KLIPPY_SOCK, LOG_DIR, ForceStream, StatusSampler, confirm,
                      emergency_stop, gcode, query, rate, spread)


PRIME_MM3 = 50          # fills the melt zone before the ramp
PRIME_FLOW = 3          # mm³/s
RETRACT_MM = 2          # more can jam the filament on the Q2
MAX_VOLUME_MM3 = 2400   # filament for a whole test, about 1 m

# Results
RECOMMEND_SHARE = 0.9   # recommended max volumetric speed: this share of the max flow
RESULT_PREFIX = "Q2_FLOW_RESULT "   # --result: the line with the result as JSON
SETTLE_FRACTION = 0.6   # first part of each step left out: pressure and melt settle
BASELINE_STEPS = 3      # steps that set the trend and the noise level
MIN_SIGNAL_G = 30       # a weaker first step: the load cell doesn't see the extrusion

# Force limit
DEFAULT_MAX_FORCE_G = 2000
MAX_FORCE_RANGE = (500, 3000)
CEILING = 0.9           # share of the limit the test stays under
PESSIMISM = 3.0         # the next step's force may rise this many times faster than so far
MIN_STEP = 0.5          # mm³/s: a smaller next step (or under MIN_STEP_SHARE) ends the ramp
MIN_STEP_SHARE = 0.05

# Motion: pieces kept just ahead of the printer, so the moves stay continuous
CHUNK_S = 0.25
QUEUE_AHEAD_S = 0.75
START_DELAY_S = 0.35    # an idle Klipper starts a move about 0.35 s after receiving it
DATA_DELAY_S = 0.15     # load cell batches (0.1 s) and 50 ms blocks
# Extrusion still to come when a stop is decided
HORIZON_S = QUEUE_AHEAD_S + CHUNK_S + START_DELAY_S + DATA_DELAY_S

# Live checks
POLL_S = 0.05
RATE_WINDOW_S = 0.5
PREDICT_AFTER_S = 0.7   # the pressure jumps at the start of a step: no extrapolation before
SKIP_AFTER_S = 1.0
PREVIOUS_AFTER_S = 2.0
STREAM_TIMEOUT_S = 0.5
SKIP_RATIO = 0.85       # force falls under this share of the step's peak: the extruder skips
KNEE_RATIO = 3.0        # force rising this many times faster per mm³/s than over the steps
                        # before: the filament no longer melts fully (the knee of the curve)
NOISE_RATIO = 3.0       # force jumps over the first steps' by this factor
NOISE_MIN_G = 40
TEMP_DROP_C = 5
POWER_SATURATED = 0.97
ON_FLOW_MIN = 0.7       # share of a step's end really at its flow, else the data isn't reliable

# kind: error (can't measure or watch), limit (the melt can't keep up), force (force limit),
#       end (end of the ramp, filament cap)
Stop = collections.namedtuple("Stop", "kind message")


class Watch:
    """What the checks need: the data, the force limit and the steps done."""

    def __init__(self, stream, status, limit, emergency):
        self.stream, self.status, self.limit, self.emergency = stream, status, limit, emergency
        self.steps = []
        self.shut_down = False
        self.tared_at = time.time()
        self.rest = None


def knee_force(steps, flow):
    """Highest force expected at a flow before the knee: the last step's force plus KNEE_RATIO
    times the median rise per mm³/s so far. None until three steps are done."""
    done = [s for s in steps if s["complete"]]
    slopes = [(b["force"] - a["force"]) / (b["flow"] - a["flow"])
              for a, b in zip(done, done[1:]) if b["flow"] > a["flow"]]
    if len(slopes) < 2:
        return None
    last = done[-1]
    return last["force"] + KNEE_RATIO * max(statistics.median(slopes), 0) * (flow - last["flow"])


def live_check(watch, flow, started, melt=True):
    """A Stop when the extrusion under way must end, else None."""
    now = time.time()
    stream = watch.stream
    if stream.failure or now - stream.last_time > STREAM_TIMEOUT_S:
        return Stop("error", "no load cell data (%s): the force can't be watched" % (
            stream.failure or "the stream stopped"))
    if stream.errors:
        return Stop("error", "the load cell reports errors")
    recent = stream.since(now - RATE_WINDOW_S)
    if not recent:
        return None
    stop = force_check(watch, recent, now - started)
    if stop is None and melt and now - started >= SKIP_AFTER_S:
        stop = melt_check(watch, flow, started, now)
    return stop or temperature_check(watch)


def limit_check(watch, recent):
    """The force limit itself: never reached in a normal run, the extrapolated force stops
    first. Also checked while the extrusion already sent finishes after a stop."""
    peak = recent[-1][3] if recent else 0.0
    if peak < watch.limit or watch.shut_down:
        return None
    if watch.emergency:
        emergency_stop()
        watch.shut_down = True
        return Stop("force", "force %.0f g reached the %d g limit: emergency stop" % (
            peak, watch.limit))
    return Stop("force", "force %.0f g reached the %d g limit" % (peak, watch.limit))


def force_check(watch, recent, elapsed):
    """The force, extrapolated over the extrusion already sent, must stay under CEILING."""
    stop = limit_check(watch, recent)
    if stop or elapsed < PREDICT_AFTER_S or len(recent) < 4:
        return stop
        return None
    force, rising = recent[-1][1], max(0.0, rate(recent))
    ceiling = CEILING * watch.limit
    if force >= ceiling:
        return Stop("force", "force %.0f g, over %.0f g" % (force, ceiling))
    if force + rising * HORIZON_S >= ceiling:
        return Stop("force", "force %.0f g rising %.0f g/s: it would pass %.0f g before the "
                    "extrusion already sent ends" % (force, rising, ceiling))
    return None


def melt_check(watch, flow, started, now):
    """The extruder skips, or the filament no longer melts fully."""
    settled = watch.stream.since(started + PREDICT_AFTER_S)
    if len(settled) < 6:
        return None
    smooth = [(a[1] + b[1]) / 2 for a, b in zip(settled, settled[1:])]     # 100 ms means
    current, peak = smooth[-1], max(smooth)
    if peak > NOISE_MIN_G and current < SKIP_RATIO * peak:
        return Stop("limit", "force fell to %.0f g from %.0f g: the extruder skips" % (
            current, peak))
    steps = [s for s in watch.steps if s["complete"]]
    if steps and now - started >= PREVIOUS_AFTER_S and current < SKIP_RATIO * steps[-1]["force"]:
        return Stop("limit", "force %.0f g, under the previous step's %.0f g: the extruder "
                    "skips" % (current, steps[-1]["force"]))
    knee = knee_force(steps, flow)
    if knee is not None and min(smooth[-6:]) > knee:
        return Stop("limit", "force %.0f g, rising %.0f times faster per mm³/s than before: the "
                    "filament no longer melts fully" % (current, KNEE_RATIO))
    if len(steps) < BASELINE_STEPS:
        return None
    base = steps[:BASELINE_STEPS]
    jumps = max(NOISE_RATIO * statistics.median(s["spread"] for s in base), NOISE_MIN_G)
    last = [b for b in settled if b[0] >= now - 0.5]
    before = [b for b in settled if now - 1.0 <= b[0] < now - 0.5]
    # twice the usual jumps in half a second, or over the usual for a whole second
    if last and (spread(last) > 2 * jumps or before and min(spread(last), spread(before)) > jumps):
        return Stop("limit", "the force jumps by %.0f g: the extruder skips or the filament no "
                    "longer melts" % spread(last))
    return None


def temperature_check(watch):
    s = watch.status.latest()
    if s and s["target"] and s["temp"] < s["target"] - TEMP_DROP_C:
        return Stop("limit", "the hotend is %.0f °C under its target: the heater can't follow" %
                    (s["target"] - s["temp"]))
    return None


def extrude_watched(watch, flow, seconds, melt=True):
    """Extrude at a flow for some seconds, in CHUNK_S pieces kept at most QUEUE_AHEAD_S ahead
    of the printer, checking every POLL_S until the motion ends. Nothing more is sent after a
    stop. Returns (started, ended, Stop or None)."""
    speed = flow / FILAMENT_AREA                        # mm/s of filament
    gcode("M83")
    sent = time.time()
    started = sent + START_DELAY_S
    queued, stop = 0.0, None

    def check():
        return live_check(watch, flow, started, melt)

    while queued < seconds - 1e-6 and stop is None:
        piece = min(CHUNK_S, seconds - queued)
        gcode("G1 E%.4f F%.1f" % (speed * piece, speed * 60))
        queued += piece
        while stop is None and time.time() - sent < queued - QUEUE_AHEAD_S:
            stop = check()
            time.sleep(POLL_S)
    while stop is None and time.time() < started + queued:    # the last pieces are watched too
        stop = check()
        time.sleep(POLL_S)
    late = None
    while not watch.shut_down and time.time() < started + queued:  # after a stop: the limit
        late = late or limit_check(watch, watch.stream.since(time.time() - RATE_WINDOW_S))
        time.sleep(POLL_S)
    if late:
        stop = Stop(late.kind, "%s; then %s, while the extrusion already sent finished" % (
            stop.message, late.message)) if stop else late
    if not watch.shut_down:
        gcode("M400")
    return started, time.time(), stop


def measure_step(watch, flow, started, ended, stop):
    """Steady values of a step: its last part, once pressure and melt have settled."""
    duration = ended - started
    begin = ended - (1 - SETTLE_FRACTION) * duration
    blocks = [b for b in watch.stream.since(begin) if b[0] <= ended - 0.05]
    if duration < 1.0 or len(blocks) < 6:
        return None
    force = [b[1] for b in blocks]
    first, second = force[:len(force) // 2], force[len(force) // 2:]
    windows = [blocks[i:i + 10] for i in range(0, len(blocks) - 9, 10)] or [blocks]
    status = [s for s in watch.status.since(begin) if s["t"] <= ended]
    on_flow = [s for s in status if abs(s["flow"] - flow) <= 0.05 * flow]
    return {
        "flow": flow, "force": statistics.fmean(force),
        "spread": statistics.fmean(spread(w) for w in windows),
        "drift": statistics.fmean(second) / statistics.fmean(first) - 1
                 if statistics.fmean(first) > 0 else 0.0,
        "temp_min": min((s["temp"] for s in status), default=None),
        "target": status[-1]["target"] if status else None,
        "power": statistics.fmean(s["power"] for s in status) if status else 0.0,
        "on_flow": len(on_flow) / len(status) if status else 1.0,
        "complete": stop is None}


def step_flags(step, steps):
    """Signs of the limit in a finished step, given the steps before it."""
    flags = []
    if step["temp_min"] is not None and step["temp_min"] < step["target"] - TEMP_DROP_C:
        flags.append("hotend -%.0f °C" % (step["target"] - step["temp_min"]))
    if step["power"] > POWER_SATURATED:
        flags.append("heater %.0f%%" % (step["power"] * 100))
    knee = knee_force(steps, step["flow"])
    if knee is not None and step["force"] > knee:
        flags.append("knee")
    done = [s for s in steps if s["complete"]]
    if len(done) >= BASELINE_STEPS:
        base = done[:BASELINE_STEPS]
        if step["spread"] > max(NOISE_RATIO * statistics.median(s["spread"] for s in base),
                                NOISE_MIN_G):
            flags.append("jumps %.0f g" % step["spread"])
    return flags


def next_flow(steps, args, limit):
    """The next flow, or None when even a small step could push the force over CEILING."""
    last = steps[-1]
    slope = last["force"] / last["flow"]
    if len(steps) >= 2 and last["flow"] > steps[-2]["flow"]:
        prev = steps[-2]
        slope = max(slope, (last["force"] - prev["force"]) / (last["flow"] - prev["flow"]))
    room = (CEILING * limit - last["force"]) / (PESSIMISM * slope)
    step = min(args.step, room)
    if step < max(MIN_STEP, MIN_STEP_SHARE * last["flow"]):
        return None
    return round(last["flow"] + step, 1)


def after_step(args, watch):
    """Whether the ramp ends after the step just done."""
    steps = watch.steps
    step = steps[-1]
    if len(steps) == 1 and step["force"] < MIN_SIGNAL_G:
        return Stop("error", "the load cell barely sees the extrusion (%.0f g at %g mm³/s): the "
                    "force can't be watched, check the load cell" % (step["force"], step["flow"]))
    if step["on_flow"] < ON_FLOW_MIN:
        return Stop("error", "the extrusion stuttered at %g mm³/s: the data isn't reliable" %
                    step["flow"])
    if step["flags"]:
        return Stop("limit", "limit reached at %g mm³/s (%s)" % (
            step["flow"], ", ".join(step["flags"])))
    return None


def print_step(step):
    print("  %6.1f   %7.0f   %11.0f   %+6.0f%%   %8.0f   %7s   %s" % (
        step["flow"], step["force"], step["force"] / step["flow"], step["drift"] * 100,
        step["spread"], "%.1f" % step["temp_min"] if step["temp_min"] is not None else "-",
        ", ".join(step["flags"])))


def notify(args, text):
    """Progress on the console and, with --status, through that G-code (a dialog)."""
    print(text)
    if args.status:
        gcode('%s STEP="%s"' % (args.status, "".join(c for c in text if c not in '"\'#;*\n')))


def ramp(args, watch):
    """Steps of increasing flow until a Stop, which it returns."""
    flow, volume = args.start, 0.0
    print("\n flow mm³/s   force g   g per mm³/s   settled   jumps g   hotend")
    while True:
        if flow > args.stop + 1e-9:
            return Stop("end", "end of the ramp (%g mm³/s)" % args.stop)
        if volume + flow * args.seconds > MAX_VOLUME_MM3:
            return Stop("end", "filament cap reached (%.0f cm)" % (
                MAX_VOLUME_MM3 / FILAMENT_AREA / 10))
        if args.status:
            notify(args, "Measuring at %g mm3/s" % flow)
        started, ended, stop = extrude_watched(watch, flow, args.seconds)
        volume += flow * args.seconds
        step = measure_step(watch, flow, started, ended, stop)
        if step is None:
            return stop or Stop("error", "too little load cell data at %g mm³/s" % flow)
        flags = step_flags(step, watch.steps) + (["stopped"] if stop else [])
        watch.steps.append(dict(step, flags=flags))
        print_step(watch.steps[-1])
        stop = stop or after_step(args, watch)
        if stop:
            return stop
        flow = next_flow(watch.steps, args, watch.limit)
        if flow is None:
            return Stop("force", "the next step could pass %.0f g (%d%% of the %d g limit)" % (
                CEILING * watch.limit, CEILING * 100, watch.limit))


def prepare(args, watch, homed):
    """Home, heat over the chute, prime (watched: a clogged nozzle stops it) and tare."""
    if not homed:
        print("Homing")
        gcode("G28")
    notify(args, "Heating to %d C over the chute" % args.temp)
    gcode("M104 S%d\nMOVE_TO_TRASH\nM109 S%d" % (args.temp, args.temp))
    time.sleep(args.soak)
    gcode("LOAD_CELL_TARE")
    watch.tared_at = time.time()
    notify(args, "Priming")
    _, _, stop = extrude_watched(watch, PRIME_FLOW, PRIME_MM3 / PRIME_FLOW, melt=False)
    if stop:
        return Stop(stop.kind, "while priming: " + stop.message)
    time.sleep(3)
    gcode("LOAD_CELL_TARE")
    time.sleep(0.5)
    return None


def finish(args, watch):
    if watch.shut_down:
        print("Klipper is shut down (emergency stop): FIRMWARE_RESTART when ready")
        return
    gcode("M83\nG1 E-%d F1800\nM400" % RETRACT_MM)
    time.sleep(2)
    rest = watch.stream.since(time.time() - 1.0)
    watch.rest = statistics.fmean(b[1] for b in rest) if rest else None
    if not args.keep_hot:
        # Like the calibrations: the nozzle wiped on the brush (without the bed mesh), then off.
        # With --keep-hot the caller goes on and wipes at its end.
        notify(args, "Wiping the nozzle")
        gcode("_SPOOL_PA_WIPE TEMP=%d\nM104 S0" % args.temp)


def preflight(args):
    s = query("print_stats=state&toolhead=homed_axes&mmu=filament,gate,gate_material,sync_drive"
              "&load_cell_probe=is_calibrated")
    if s["print_stats"]["state"] in ("printing", "paused"):
        raise SystemExit("A print is running: run the test when the printer is idle.")
    if not s["load_cell_probe"].get("is_calibrated"):
        raise SystemExit("The load cell is not calibrated: run ./install.sh calibrate first.")
    mmu = s.get("mmu")
    if mmu is not None and mmu.get("filament") != "Loaded":
        raise SystemExit("No filament loaded in the toolhead: load the slot to test first "
                         "(MMU_LOAD), the test does not change slots.")
    material = ""
    if mmu is not None and mmu.get("gate", -1) >= 0:
        material = mmu["gate_material"][mmu["gate"]]
    print("Flow test at %d °C%s, from %g mm³/s, %g s per step" % (
        args.temp, " (slot %d, %s)" % (mmu["gate"] + 1, material) if material else "",
        args.start, args.seconds))
    print("Force limit %d g: the test stays under %.0f g. At most %.0f cm of filament, into the "
          "bucket." % (args.max_force, CEILING * args.max_force,
                       (PRIME_MM3 + MAX_VOLUME_MM3) / FILAMENT_AREA / 10))
    if mmu is not None and not mmu.get("sync_drive"):
        print("Note: the Box motor is not synced to the extruder; the extruder pulls the filament "
              "through the bowden alone.")
    return material, "xyz" in s["toolhead"]["homed_axes"]


def start_data():
    stream, status = ForceStream(), StatusSampler()
    stream.start()
    status.start()
    deadline = time.time() + 3
    while not stream.since(time.time() - 1) and time.time() < deadline:
        time.sleep(0.1)
    if not stream.since(time.time() - 1):
        raise SystemExit("No data from the load cell stream (%s): the force can't be watched." % (
            stream.failure or KLIPPY_SOCK))
    return stream, status


def run(args):
    material, homed = preflight(args)
    stream, status = start_data()
    if not args.yes and not confirm("The bucket is in place and the chute is clear. Start?"):
        raise SystemExit("Stopped.")
    watch = Watch(stream, status, args.max_force, args.emergency_stop)
    try:
        stop = prepare(args, watch, homed) or ramp(args, watch)
    except KeyboardInterrupt:
        stop = Stop("error", "interrupted")
    finally:
        finish(args, watch)
        status.stopped.set()
    return stop, material, watch


def results(stop, steps):
    """(max flow, recommended max volumetric speed, whether the max is only a lower bound).
    The max is the last step without a sign of the limit, when the ramp ended on a limit, or
    at its end (then the real max is higher)."""
    good = [s for s in steps if s["complete"] and not s["flags"]]
    if not good or stop.kind not in ("limit", "force", "end"):
        return None, None, False
    max_flow = good[-1]["flow"]
    return max_flow, math.floor(max_flow * RECOMMEND_SHARE * 2) / 2, stop.kind == "end"


def summary(args, stop, material, watch):
    steps = watch.steps
    max_flow, recommended, at_least = results(stop, steps)
    top = max((s["force"] for s in steps), default=0)
    lines = ["Flow test at %d °C%s, force limit %d g" % (
        args.temp, ", " + material if material else "", args.max_force), ""]
    for s in steps:
        bar = "#" * int(round(40 * s["force"] / top)) if top > 0 else ""
        lines.append("  %5.1f mm³/s %6.0f g  %4.0f g per mm³/s  %s %s" % (
            s["flow"], s["force"], s["force"] / s["flow"], bar, ", ".join(s["flags"])))
    peak = max((b[3] for b in watch.stream.since(watch.tared_at)), default=0)
    lines += ["", "Stopped: " + stop.message,
              "Highest force: %.0f g (limit %d g)" % (peak, args.max_force)]
    if watch.rest is not None:
        lines.append("Load cell at rest afterwards: %.0f g (drift since the tare)" % watch.rest)
    if max_flow is None:
        lines.append("Max flow: not measured")
    else:
        lines.append("Max flow: %s%g mm³/s (%s)" % (
            "at least " if at_least else "", max_flow,
            {"force": "the force limit, higher flows not tried",
             "limit": "above it the filament no longer melts fully",
             "end": "the end of the ramp"}[stop.kind]))
        lines.append("Recommended max volumetric speed: %g mm³/s" % recommended)
    unsettled = [s["flow"] for s in steps if s["complete"] and abs(s["drift"]) > 0.05]
    if unsettled:
        lines.append("The force was still changing at %s mm³/s: longer steps (--seconds) give "
                     "steadier values" % ", ".join("%g" % q for q in unsettled))
    return lines


def save(args, stop, material, watch):
    os.makedirs(LOG_DIR, exist_ok=True)
    base = os.path.join(LOG_DIR, time.strftime("flow-test-%Y%m%d-%H%M%S"))
    t0 = watch.tared_at
    with open(base + "-force.csv", "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["t", "force", "force_min", "force_max"])
        writer.writerows([round(b[0] - t0, 3), round(b[1], 1), round(b[2], 1), round(b[3], 1)]
                         for b in watch.stream.since(t0))
    with open(base + "-status.csv", "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["t", "flow", "temp", "target", "power"])
        writer.writerows([round(s["t"] - t0, 3), round(s["flow"], 2), s["temp"], s["target"],
                          round(s["power"], 3)] for s in watch.status.since(t0))
    lines = summary(args, stop, material, watch) + ["Data: %s-force.csv, -status.csv" % base]
    with open(base + ".txt", "w") as out:
        out.write("\n".join(lines) + "\n")
    print("\n" + "\n".join(lines))
    return base + ".txt"


def result_line(stop, watch, report):
    """--result: everything a caller needs, as one JSON line."""
    max_flow, recommended, at_least = results(stop, watch.steps)
    peak = max((b[3] for b in watch.stream.since(watch.tared_at)), default=None)
    return RESULT_PREFIX + json.dumps({
        "max_flow": max_flow, "recommended": recommended, "at_least": at_least,
        "stop": stop.kind, "message": stop.message, "highest_force": peak,
        "steps": [{"flow": s["flow"], "force": round(s["force"]), "flags": s["flags"]}
                  for s in watch.steps], "report": report})


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--temp", type=int, required=True, help="hotend temperature, °C")
    parser.add_argument("--start", type=float, default=4, help="first flow, mm³/s")
    parser.add_argument("--step", type=float, default=2, help="largest flow increment, mm³/s")
    parser.add_argument("--stop", type=float, default=40, help="highest flow tried, mm³/s")
    parser.add_argument("--seconds", type=float, default=12, help="duration of each step")
    parser.add_argument("--soak", type=float, default=20, help="wait after heating, seconds")
    parser.add_argument("--max-force", type=int, default=DEFAULT_MAX_FORCE_G,
                        help="force the extruder must never reach, g (default %(default)s)")
    parser.add_argument("--emergency-stop", action="store_true",
                        help="shut Klipper down at once if the force limit is reached")
    parser.add_argument("--keep-hot", action="store_true", help="leave the hotend on at the end")
    parser.add_argument("--yes", action="store_true", help="don't ask before starting")
    parser.add_argument("--status", default="",
                        help="G-code that shows progress, given STEP=\"...\" (e.g. a dialog macro)")
    parser.add_argument("--result", action="store_true",
                        help="print the result as one JSON line starting with " + RESULT_PREFIX.strip())
    args = parser.parse_args()
    if not 170 <= args.temp <= 320:
        parser.error("--temp must be between 170 and 320 °C")
    if not MAX_FORCE_RANGE[0] <= args.max_force <= MAX_FORCE_RANGE[1]:
        parser.error("--max-force must be between %d and %d g" % MAX_FORCE_RANGE)
    if not 0 < args.start <= args.stop or args.step <= 0 or args.seconds < 4:
        parser.error("check --start, --stop, --step (> 0) and --seconds (>= 4)")
    stop, material, watch = run(args)
    report = save(args, stop, material, watch)
    if args.result:
        print(result_line(stop, watch, report), flush=True)


if __name__ == "__main__":
    main()
