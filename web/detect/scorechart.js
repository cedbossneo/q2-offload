// Failure detection page: chart options for one print's score (live view and history).
import { fmtClock, fmtDuration, fmtNum, h, isNum } from "/q2-assets/core.js";
import { nearest } from "/q2-assets/chart.js";
import { fmtScore, KIND_TONE } from "./verdict.js";

const MIN_SPAN_S = 20 * 60;   // a fresh print still shows a readable time axis
const HEADROOM = 1.25;        // room above the pause level
const BAR_FILL = 0.72;        // bar width as a share of its bucket

const tick = (v) => String(Number(v.toFixed(2)));

function emptyOptions(message) {
  const now = Date.now() / 1000;
  return { empty: message, x: { min: now - MIN_SPAN_S, max: now, time: true }, y: { min: 0, max: 1, format: tick } };
}

const LEGEND = [
  ["sw", "--muted", "Detections (sum of box confidences)"],
  ["sw sw-line", "--accent", "Score"],
  ["sw sw-dash", "--caution", "Warning level"],
  ["sw sw-dash", "--halt", "Pause level"],
  ["sw sw-band", "--faint", "First minutes: no alerts"],
];

export function scoreLegend() {
  return h("ul", { class: "legend" }, LEGEND.map(([cls, colour, text]) =>
    h("li", {}, h("span", { class: cls, style: { "--c": "var(" + colour + ")" } }), text)));
}

export function scoreChartOptions(print) {
  const series = print && print.series;
  if (!series || !series.score || !series.score.length) return emptyOptions(print ? "No frame analysed yet" : "No print watched yet");
  const frameS = print.frame_s || 10;
  const bucketS = (series.step || 1) * frameS;
  const t0 = print.started;
  const at = (i) => t0 + (i + 0.5) * bucketS;
  const p = series.p.map((v, i) => [at(i), v]);
  const raw = series.score.map((v, i) => [at(i), v]);
  const score = raw.map(([t, v]) => [t, v == null ? null : Math.max(0, v)]);
  const levels = print.levels || {};
  const lastT = t0 + series.score.length * bucketS;
  const xMax = Math.max(t0 + MIN_SPAN_S, print.ended || 0, lastT);
  const values = [...series.p, ...series.score].filter(isNum);
  const yMax = Math.max((levels.pause || 0.6) * HEADROOM, ...values.map((v) => v * 1.08), 0.5);
  const decisions = print.decisions || [];
  const peak = Math.max(0, ...series.score.filter(isNum));

  return {
    x: { min: t0, max: xMax, time: true },
    y: { min: 0, max: yMax, format: tick },
    bands: [{ from: t0, to: t0 + (print.safe_frames || 0) * frameS, color: "--raised", label: "No alerts" }],
    levels: [
      isNum(levels.warning) && { value: levels.warning, color: "--caution", label: "Warning " + fmtNum(levels.warning) },
      isNum(levels.pause) && { value: levels.pause, color: "--halt", label: "Pause " + fmtNum(levels.pause) },
    ].filter(Boolean),
    series: [
      { type: "bars", data: p, color: "--muted", barWidth: bucketS * BAR_FILL, opacity: 0.42 },
      { type: "line", data: score, color: "--accent", width: 2.2 },
    ],
    markers: decisions.map((d) => ({ x: d.t, y: Math.max(0, d.score || 0), color: "--" + (KIND_TONE[d.kind] || "caution") })),
    tooltip(x) {
      const i = nearest(raw, x);
      if (i == null) return null;
      return {
        x: raw[i][0],
        title: fmtClock(raw[i][0]) + ", " + fmtDuration(raw[i][0] - t0) + " in",
        rows: [
          { label: "Score", value: fmtScore(raw[i][1]), color: "--accent" },
          { label: "Detections", value: fmtNum(p[i][1]), color: "--muted" },
        ],
      };
    },
    ariaLabel: "Score chart: peak " + fmtNum(peak) + ", warning level " + fmtNum(levels.warning) + ", pause level " +
      fmtNum(levels.pause) + ", " + decisions.length + " alert" + (decisions.length === 1 ? "" : "s") + ".",
  };
}
