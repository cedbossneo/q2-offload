// Failure detection page: what it says for each state of GET /detect/api/status.
import { test } from "node:test";
import assert from "node:assert/strict";
import { importWeb } from "./setup.mjs";

const { deriveState, notices, chain, fmtScore, isActive, decisionLevels } = await importWeb("detect/verdict.js");
const { fmtDuration, fmtAgo, fmtNum, plural } = await importWeb("assets/core.js");

const NOW = 1793491230;

function status(overrides = {}, printOverrides = {}) {
  const print = printOverrides === null ? null : {
    id: "p1", filename: "Benchy.gcode", started: NOW - 3600, ended: null, status: "printing",
    frame: 120, frame_s: 10, safe_frames: 30, p: 0.05, score: 0.05,
    levels: { warning: 0.4, pause: 0.7 }, muted: false, alert_pending: false, paused_by_detection: false,
    last_frame: { t: NOW, detections: [] }, series: { step: 1, p: [], score: [] }, decisions: [], ...printOverrides,
  };
  return {
    settings: { enabled: true, mode: "observe" }, ml_api: { ok: true, error: null, ms: 200 },
    camera: { name: "q2", stream_url: "x", error: null }, printer: { state: "printing" }, print, ...overrides,
  };
}

const decision = (kind, extra = {}) => ({ n: 0, t: NOW - 30, kind, score: 0.8, snapshot: "d000.jpg", label: null, ...extra });
const pausedByDetection = (printExtra = {}) => status({ printer: { state: "paused" }, settings: { enabled: true, mode: "pause" } },
  { status: "paused", paused_by_detection: true, alert_pending: true, decisions: [decision("pause")], ...printExtra });

test("watching below the warning level says all clear", () => {
  const s = deriveState(status());
  assert.equal(s.key, "watching");
  assert.equal(s.tone, "clear");
  assert.equal(s.title, "All clear");
  assert.match(s.why, /would have paused/);
  assert.deepEqual([s.canAck, s.canMute, s.watching, s.canResume], [false, true, true, false]);
});

test("pause mode wording says the print is paused", () => {
  assert.match(deriveState(status({ settings: { enabled: true, mode: "pause" } })).why, /the print is paused/);
});

test("detection off wins over everything and hides the meter", () => {
  const s = deriveState(status({ settings: { enabled: false }, ml_api: { ok: false } },
    { alert_pending: true, decisions: [decision("warning")] }));
  assert.equal(s.key, "disabled");
  assert.equal(s.watching, false);
  assert.equal(s.canMute, false);
});

test("printer offline, fresh install, idle", () => {
  assert.equal(deriveState(status({ printer: { state: "offline" } })).key, "offline");
  assert.equal(deriveState(status({ printer: { state: "standby" } }, null)).key, "fresh");
  const idle = deriveState(status({ printer: { state: "complete" } }, { status: "completed", ended: NOW }));
  assert.equal(idle.key, "idle");
  assert.equal(idle.active, false);
});

test("warm-up during the first frames", () => {
  const s = deriveState(status({}, { frame: 12 }));
  assert.equal(s.key, "warmup");
  assert.match(s.why, /first 5 minutes/);
});

test("pending warning and would-pause, compared with the levels of that moment", () => {
  const w = deriveState(status({}, { alert_pending: true,
    decisions: [decision("warning", { score: 0.45, levels: { warning: 0.38, pause: 0.66 } })] }));
  assert.deepEqual([w.key, w.tone, w.canAck, w.pulse], ["warning", "caution", true, true]);
  assert.match(w.why, /above the warning level 0\.38/);
  assert.match(w.why, /If it passes 0\.66/);
  const wp = deriveState(status({}, { alert_pending: true, decisions: [decision("would-pause")] }));
  assert.deepEqual([wp.key, wp.tone], ["would-pause", "halt"]);
  assert.match(wp.why, /above the pause level 0\.70/);   // no stored levels: the print's
});

test("decision levels fall back to the print's for older decisions", () => {
  const print = { levels: { warning: 0.4, pause: 0.7 } };
  assert.deepEqual(decisionLevels({ levels: { warning: 0.5, pause: 0.9 } }, print), { warning: 0.5, pause: 0.9 });
  assert.deepEqual(decisionLevels({}, print), print.levels);
  assert.deepEqual(decisionLevels(null, null), {});
});

test("paused by detection: alert open, then marked fine; resume asks first", () => {
  const open = deriveState(pausedByDetection());
  assert.deepEqual([open.key, open.tone, open.canAck, open.canResume, open.confirmResume], ["paused-detect", "halt", true, true, true]);
  const fine = deriveState(pausedByDetection({ alert_pending: false }));
  assert.deepEqual([fine.key, fine.canAck, fine.canResume, fine.confirmResume], ["paused-acked", false, true, true]);
});

test("paused by the user is never blamed on detection, even with a pause decision", () => {
  const s = deriveState(status({ printer: { state: "paused" } }, { status: "paused", decisions: [decision("pause")] }));
  assert.equal(s.key, "paused");
  assert.match(s.why, /not by detection/);
  assert.deepEqual([s.canResume, s.confirmResume], [true, false]);
  const open = deriveState(status({ printer: { state: "paused" } },
    { status: "paused", alert_pending: true, decisions: [decision("would-pause")] }));
  assert.equal(open.key, "paused");
  assert.match(open.why, /still open/);
});

test("resume is offered for any paused print, even with detection off", () => {
  const s = deriveState(status({ printer: { state: "paused" }, settings: { enabled: false } }, { status: "paused" }));
  assert.equal(s.key, "disabled");
  assert.equal(s.canResume, true);
});

test("resumed after a detection pause without Looks fine", () => {
  const s = deriveState(status({}, { alert_pending: true, decisions: [decision("pause")] }));
  assert.equal(s.key, "resumed-open");
  assert.match(s.why, /resumed without Looks fine/);
});

test("score above warning without a pending alert", () => {
  const s = deriveState(status({}, { score: 0.5, decisions: [decision("warning", { score: 0.45 })] }));
  assert.equal(s.key, "elevated");
  assert.match(s.why, /dismissed/);
});

test("camera and detector problems while printing, raw error kept apart", () => {
  const cam = deriveState(status({ camera: { name: "q2", error: "camera not reachable: timeout" } }));
  assert.deepEqual([cam.key, cam.detail], ["camera", "camera not reachable: timeout"]);
  const ml = deriveState(status({ ml_api: { ok: false, error: "connection refused" } }));
  assert.deepEqual([ml.key, ml.detail], ["ml-down", "connection refused"]);
  assert.equal(deriveState(status({ ml_api: { ok: null } })).key, "watching");
});

test("an alert outranks a camera or detector problem", () => {
  const s = deriveState(status({ camera: { error: "x" }, ml_api: { ok: false } }, { alert_pending: true, decisions: [decision("warning")] }));
  assert.equal(s.key, "warning");
});

test("muted", () => {
  const s = deriveState(status({}, { muted: true }));
  assert.deepEqual([s.key, s.canMute], ["muted", false]);
});

test("notices only for problems that are not the main state", () => {
  const idle = status({ printer: { state: "standby" }, camera: { error: "camera not reachable" }, ml_api: { ok: false, error: "down" } }, null);
  assert.equal(notices(idle, deriveState(idle)).length, 2);
  const cam = status({ camera: { error: "camera not reachable" } });
  assert.equal(notices(cam, deriveState(cam)).length, 0);
  const off = status({ settings: { enabled: false }, ml_api: { ok: false } });
  assert.equal(notices(off, deriveState(off)).length, 0);
});

test("chain describes camera, detector and printer", () => {
  assert.deepEqual(chain(status()).map((c) => c[1]), ["q2", "200 ms", "printing"]);
  assert.deepEqual(chain(status({ camera: null, ml_api: { ok: null } })).map((c) => c[1]),
    ["not connected yet", "not checked yet", "printing"]);
});

test("isActive needs both the print and Klipper printing or paused", () => {
  assert.equal(isActive(status()), true);
  assert.equal(isActive(status({ printer: { state: "standby" } })), false);
});

test("formatting", () => {
  assert.equal(fmtScore(-0.02), "0.00");
  assert.equal(fmtScore(0.456), "0.46");
  assert.equal(fmtScore(null), "–");
  assert.equal(fmtNum(undefined), "–");
  assert.equal(fmtDuration(45), "45 s");
  assert.equal(fmtDuration(12 * 60), "12 min");
  assert.equal(fmtDuration(3720), "1 h 02");
  assert.equal(fmtDuration(3 * 86400 + 4 * 3600), "3 d 4 h");
  assert.equal(fmtAgo(NOW - 2, NOW), "just now");
  assert.equal(fmtAgo(NOW - 30, NOW), "30 s ago");
  assert.equal(fmtAgo(NOW - 600, NOW), "10 min ago");
  assert.equal(plural(1, "print"), "1 print");
  assert.equal(plural(2, "false alarm"), "2 false alarms");
});
