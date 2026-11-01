// Failure detection page: turns GET /detect/api/status into what the page says, in plain words.
// Pure functions (no DOM), so the wording of every state can be checked in one place.
import { fmtClock, fmtNum, isNum } from "/q2-assets/core.js";

export const KIND_LABEL = { warning: "Warning", pause: "Paused the print", "would-pause": "Would have paused" };
export const KIND_TONE = { warning: "caution", pause: "halt", "would-pause": "halt" };
export const PRINT_STATUS = {
  printing: ["Printing", "accent"],
  paused: ["Paused", "caution"],
  completed: ["Completed", "neutral"],
  cancelled: ["Cancelled", "neutral"],
  error: ["Error", "halt"],
};
export const ACTIVE = ["printing", "paused"];

// The score is "above this printer's usual level": below usual reads as 0.00
export const fmtScore = (v) => fmtNum(isNum(v) ? Math.max(0, v) : v);

export function lastDecision(print) {
  const list = (print && print.decisions) || [];
  return list.length ? list[list.length - 1] : null;
}

export function isActive(status) {
  const print = status && status.print;
  const printer = (status && status.printer && status.printer.state) || "offline";
  return Boolean(print && ACTIVE.includes(print.status) && ACTIVE.includes(printer));
}

// What happens above the pause level, depending on the mode
export function pauseOutcome(mode) {
  return mode === "pause" ? "the print is paused" : "you're told it would have paused (Observe mode never pauses)";
}

export function modeText(mode) {
  return mode === "pause"
    ? "Pause mode: above the pause level the print is paused and you're notified."
    : "Observe mode: you're notified, the print is never paused.";
}

export function safeMinutes(print) {
  return Math.round(((print && print.safe_frames) || 30) * ((print && print.frame_s) || 10) / 60);
}

function state(key, tone, label, title, why, extra = {}) {
  return { key, tone, label, title, why, detail: null, pulse: false, ...extra };
}

// The levels in force when a decision was taken (older stored decisions lack them)
export function decisionLevels(decision, print) {
  return (decision && decision.levels) || (print && print.levels) || {};
}

// "At 14:12, the score reached 0.81, above the pause level 0.70"
function alertSentence(last, print) {
  const lv = decisionLevels(last, print);
  const level = last.kind === "warning" ? "the warning level " + fmtNum(lv.warning) : "the pause level " + fmtNum(lv.pause);
  return "At " + fmtClock(last.t) + ", the score reached " + fmtScore(last.score) + ", above " + level;
}

function pausedState(print, last) {
  if (print.paused_by_detection) {
    const when = last ? alertSentence(last, print) + ", so the print was paused." : "Detection paused the print.";
    return print.alert_pending
      ? state("paused-detect", "halt", "Paused by detection", "Print paused",
        when + " Check it: if it's fine, press Looks fine or resume the print.", { pulse: true })
      : state("paused-acked", "neutral", "Paused", "Print paused",
        "Detection paused the print and you marked it as fine. Resume it when you're ready: watching continues with the print.");
  }
  return state("paused", "neutral", "Paused", "Print paused",
    "The print was paused from Mainsail or the printer, not by detection." +
    (print.alert_pending && last ? " The alert from " + fmtClock(last.t) + " is still open: press Looks fine if the print is OK." : "") +
    " Watching resumes with the print.");
}

function activeState(status, ctx) {
  const { print, last, levels, mode } = ctx;
  const w = fmtNum(levels.warning), p = fmtNum(levels.pause);
  if (status.printer.state === "paused") return pausedState(print, last);
  if (print.alert_pending && last) {
    const lv = decisionLevels(last, print);
    if (last.kind === "pause") {
      return state("resumed-open", "caution", "Alert open", "Resumed after a pause",
        alertSentence(last, print) + " and detection paused the print. It was resumed without Looks fine, so no new alert is sent until you press it.", { pulse: true });
    }
    if (last.kind === "would-pause") {
      return state("would-pause", "halt", "Would have paused", "Likely failure",
        alertSentence(last, print) + ". Observe mode only notifies, so the print is still running: check it now.", { pulse: true });
    }
    return state("warning", "caution", "Warning", "Possible failure",
      alertSentence(last, print) + ". If it passes " + fmtNum(lv.pause) + ", " + pauseOutcome(mode) + ".", { pulse: true });
  }
  if (status.camera && status.camera.error) {
    return state("camera", "caution", "Camera problem", "Can't see the print",
      "The service can't get a frame from the camera, so nothing is analysed until it answers.", { detail: status.camera.error });
  }
  if (status.ml_api && status.ml_api.ok === false) {
    return state("ml-down", "caution", "Can't analyse", "Detector not answering",
      "Obico's detector doesn't answer, so frames aren't analysed and a failure would go unnoticed.", { detail: status.ml_api.error });
  }
  if (print.muted) {
    return state("muted", "neutral", "Muted", "Muted for this print",
      "Frames are still analysed and shown here, but nothing alerts or pauses until this print ends.");
  }
  if (isNum(print.frame) && print.frame < (print.safe_frames || 0)) {
    const from = print.started + print.safe_frames * (print.frame_s || 10);
    return state("warmup", "clear", "Watching", "Warming up",
      "The first " + safeMinutes(print) + " minutes never alert: first layers and purge lines can look like spaghetti to the camera. Alerts are possible from " + fmtClock(from) + ".");
  }
  if (isNum(print.score) && isNum(levels.warning) && print.score >= levels.warning) {
    return state("elevated", "caution", "Watching", "Above the warning level",
      "The score " + fmtScore(print.score) + " is above the warning level " + w +
      (last ? ", but the last alert was dismissed with Looks fine." : ".") + " Above " + p + ", " + pauseOutcome(mode) + ".");
  }
  return state("watching", "clear", "Watching", "All clear",
    "Score " + fmtScore(print.score) + ": nothing unusual. Above " + w + " you get a warning; above " + p + ", " + pauseOutcome(mode) + ".");
}

// -> { key, tone, label, title, why, pulse, active, canAck, canMute }
export function deriveState(status) {
  const settings = status.settings || {};
  const print = status.print || null;
  const printer = (status.printer && status.printer.state) || "offline";
  const mode = settings.mode === "pause" ? "pause" : "observe";
  const active = isActive(status);
  const ctx = { print, last: lastDecision(print), levels: (print && print.levels) || {}, mode };
  let result;
  if (settings.enabled === false) {
    result = state("disabled", "off", "Off", "Detection is off",
      "Nothing is analysed and no print will be paused. Turn it on in Settings.");
  } else if (printer === "offline") {
    result = state("offline", "off", "Printer offline", "Printer not connected",
      "Klipper or Moonraker doesn't answer the detection service, so there is nothing to watch.");
  } else if (active) {
    result = activeState({ ...status, printer: { ...status.printer, state: printer } }, ctx);
  } else if (!print) {
    result = state("fresh", "neutral", "Ready", "Waiting for a first print",
      "Nothing watched yet. When a print starts, a camera frame is analysed every 10 seconds and the score shows up here.");
  } else {
    result = state("idle", "neutral", "Idle", "Waiting for a print",
      "Detection starts by itself with the next print.");
  }
  return {
    ...result,
    mode,
    active,
    // A print runs and detection looks at it: the meter and the actions make sense
    watching: active && settings.enabled !== false,
    canAck: active && Boolean(print.alert_pending),
    canMute: active && !print.muted && settings.enabled !== false,
    // Any paused print can be resumed from here; a detection pause asks first
    canResume: printer === "paused",
    confirmResume: printer === "paused" && Boolean(print && print.paused_by_detection),
  };
}

// Problems worth a banner when they are not already the main state
export function notices(status, current) {
  const list = [];
  const camError = status.camera && status.camera.error;
  if (camError && current.key !== "camera" && current.key !== "disabled") {
    list.push({ tone: "caution", icon: "cameraOff", title: "Camera problem", text: camError + ". The next print can't be watched until the camera answers." });
  }
  if (status.ml_api && status.ml_api.ok === false && current.key !== "ml-down" && current.key !== "disabled") {
    list.push({ tone: "caution", icon: "chip", title: "Detector not answering", text: (status.ml_api.error || "no answer") + ". Frames can't be analysed until it's back." });
  }
  return list;
}

// One line per link of the chain camera -> detector -> printer, for the health row
export function chain(status) {
  const cam = status.camera;
  const ml = status.ml_api || {};
  const printer = (status.printer && status.printer.state) || "offline";
  return [
    cam == null ? ["Camera", "not connected yet", "neutral"]
      : cam.error ? ["Camera", "not reachable", "caution"]
        : ["Camera", cam.name || "OK", "clear"],
    ml.ok === true ? ["Detector", isNum(ml.ms) ? Math.round(ml.ms) + " ms" : "OK", "clear"]
      : ml.ok === false ? ["Detector", "not answering", "caution"]
        : ["Detector", "not checked yet", "neutral"],
    ["Printer", printer, printer === "offline" || printer === "error" ? "caution" : printer === "printing" ? "accent" : "neutral"],
  ];
}
