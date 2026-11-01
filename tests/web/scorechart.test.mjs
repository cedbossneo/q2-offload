// Failure detection page: the score chart built from a print's series.
import { test } from "node:test";
import assert from "node:assert/strict";
import { importWeb } from "./setup.mjs";

const { scoreChartOptions } = await importWeb("detect/scorechart.js");

const T0 = 1793490000;
const print = {
  started: T0, ended: null, frame_s: 10, safe_frames: 30,
  levels: { warning: 0.4, pause: 0.7 },
  series: { step: 2, p: [0.1, 0.2, 1.5], score: [-0.05, 0.1, 0.9] },
  decisions: [{ n: 0, t: T0 + 50, kind: "would-pause", score: 0.9 }],
};

test("no print, or no frame yet, gives an empty chart with a message", () => {
  assert.equal(scoreChartOptions(null).empty, "No print watched yet");
  assert.equal(scoreChartOptions({ ...print, series: { step: 1, p: [], score: [] } }).empty, "No frame analysed yet");
});

test("buckets are placed in time, the score never drawn below 0", () => {
  const o = scoreChartOptions(print);
  const [bars, line] = o.series;
  assert.deepEqual(bars.data.map((d) => d[0]), [T0 + 10, T0 + 30, T0 + 50]);   // bucket centres (2 frames of 10 s)
  assert.deepEqual(line.data.map((d) => d[1]), [0, 0.1, 0.9]);
  assert.equal(o.x.min, T0);
  assert.ok(o.x.max >= T0 + 20 * 60, "a fresh print still shows 20 minutes");
  assert.ok(o.y.max >= 1.5, "room for the tallest bar");
});

test("levels, the no-alert band and the decisions are drawn", () => {
  const o = scoreChartOptions(print);
  assert.deepEqual(o.levels.map((l) => [l.value, l.label]), [[0.4, "Warning 0.40"], [0.7, "Pause 0.70"]]);
  assert.deepEqual([o.bands[0].from, o.bands[0].to], [T0, T0 + 300]);
  assert.deepEqual(o.markers.map((m) => [m.x, m.color]), [[T0 + 50, "--halt"]]);
  assert.match(o.ariaLabel, /peak 0\.90/);
});

test("the tooltip shows the real score of the nearest bucket", () => {
  const tip = scoreChartOptions(print).tooltip(T0 + 28);
  assert.equal(tip.x, T0 + 30);
  assert.deepEqual(tip.rows.map((r) => r.value), ["0.10", "0.20"]);
  assert.equal(scoreChartOptions(print).tooltip(T0).rows[0].value, "0.00");
});
