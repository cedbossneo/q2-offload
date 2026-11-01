// q2-offload pages: small canvas chart (bars, lines, dashed levels, shaded bands, markers,
// time axis, pointer tooltip). Colours are CSS custom property names ("--accent"), read at
// draw time so the chart follows the theme. Sharp on high-DPI screens.
import { fmtClock, h } from "./core.js";

const PAD_TOP = 14;
const PAD_BOTTOM = 26;
const TICK_PX = 84;                  // minimum room per x tick label
const TIME_STEPS = [10, 30, 60, 120, 300, 600, 900, 1800, 3600, 7200, 10800, 21600, 43200, 86400];
const TOUCH_TIP_MS = 2600;

function niceStep(range, count) {
  const raw = range / Math.max(1, count);
  const mag = 10 ** Math.floor(Math.log10(raw || 1));
  const norm = raw / mag;
  const nice = norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  return nice * mag;
}

function numberTicks(min, max, count) {
  const step = niceStep(max - min, count);
  const ticks = [];
  for (let v = Math.ceil(min / step) * step; v <= max + step * 1e-6; v += step) ticks.push(Number(v.toFixed(10)));
  return ticks;
}

// Ticks on round local times (every 5 min, 30 min, 1 h...)
function timeTicks(min, max, maxCount) {
  const step = TIME_STEPS.find((s) => (max - min) / s <= maxCount) || TIME_STEPS[TIME_STEPS.length - 1];
  const offset = -new Date(min * 1000).getTimezoneOffset() * 60;
  const ticks = [];
  for (let t = Math.ceil((min + offset) / step) * step - offset; t <= max; t += step) ticks.push(t);
  return ticks;
}

export const timeLabel = fmtClock;

export function createChart(container, initial) {
  const canvas = h("canvas", { role: "img" });
  const tip = h("div", { class: "chart-tip", hidden: true, "aria-hidden": "true" });
  container.replaceChildren(canvas, tip);
  const ctx = canvas.getContext("2d");
  let opts = initial;
  let size = { w: 0, h: 0 };
  let plot = null;
  let hoverX = null;
  let touchTimer = null;

  function color(name, fallback = "#888") {
    if (!name) return fallback;
    if (!name.startsWith("--")) return name;
    return getComputedStyle(container).getPropertyValue(name).trim() || fallback;
  }

  function resize() {
    const rect = container.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    size = { w: Math.max(1, rect.width), h: Math.max(1, rect.height) };
    canvas.width = Math.round(size.w * dpr);
    canvas.height = Math.round(size.h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }

  function axisOf(name) {
    return name === "y2" && opts.y2 ? opts.y2 : opts.y;
  }

  function scales() {
    const font = color("--font", "system-ui");
    ctx.font = "500 11.5px " + font;
    const yTicks = numberTicks(opts.y.min, opts.y.max, Math.max(2, Math.floor((size.h - PAD_TOP - PAD_BOTTOM) / 44)));
    const y2Ticks = opts.y2 ? numberTicks(opts.y2.min, opts.y2.max, yTicks.length - 1) : [];
    const labelW = (ticks, fmt) => Math.max(0, ...ticks.map((t) => ctx.measureText(fmt(t)).width));
    const left = Math.ceil(labelW(yTicks, opts.y.format || String)) + 12;
    const right = opts.y2 ? Math.ceil(labelW(y2Ticks, opts.y2.format || String)) + 12 : 8;
    const r = { x: left, y: PAD_TOP, w: Math.max(10, size.w - left - right), h: Math.max(10, size.h - PAD_TOP - PAD_BOTTOM) };
    const xs = (v) => r.x + ((v - opts.x.min) / ((opts.x.max - opts.x.min) || 1)) * r.w;
    const ys = (v, axis = "y") => {
      const a = axisOf(axis);
      return r.y + r.h - ((v - a.min) / ((a.max - a.min) || 1)) * r.h;
    };
    return { r, xs, ys, yTicks, y2Ticks, font };
  }

  function drawGrid(s) {
    ctx.lineWidth = 1;
    ctx.strokeStyle = color("--line-soft");
    ctx.fillStyle = color("--faint");
    ctx.textBaseline = "middle";
    for (const t of s.yTicks) {
      const y = Math.round(s.ys(t)) + 0.5;
      ctx.beginPath(); ctx.moveTo(s.r.x, y); ctx.lineTo(s.r.x + s.r.w, y); ctx.stroke();
      ctx.textAlign = "right";
      ctx.fillText((opts.y.format || String)(t), s.r.x - 8, y);
    }
    if (opts.y2) {
      ctx.textAlign = "left";
      for (const t of s.y2Ticks) ctx.fillText((opts.y2.format || String)(t), s.r.x + s.r.w + 8, s.ys(t, "y2"));
    }
    const ticks = opts.x.time
      ? timeTicks(opts.x.min, opts.x.max, Math.max(2, Math.floor(s.r.w / TICK_PX)))
      : numberTicks(opts.x.min, opts.x.max, Math.max(2, Math.floor(s.r.w / TICK_PX)));
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    for (const t of ticks) {
      const x = s.xs(t);
      if (x < s.r.x - 1 || x > s.r.x + s.r.w + 1) continue;
      ctx.fillText((opts.x.format || timeLabel)(t), Math.min(Math.max(x, s.r.x + 18), s.r.x + s.r.w - 18), s.r.y + s.r.h + 8);
    }
    ctx.strokeStyle = color("--line");
    ctx.beginPath(); ctx.moveTo(s.r.x, s.r.y + s.r.h + 0.5); ctx.lineTo(s.r.x + s.r.w, s.r.y + s.r.h + 0.5); ctx.stroke();
  }

  function drawBands(s) {
    for (const band of opts.bands || []) {
      const x0 = Math.max(s.r.x, s.xs(band.from));
      const x1 = Math.min(s.r.x + s.r.w, s.xs(band.to));
      if (x1 <= x0) continue;
      ctx.globalAlpha = 0.5;
      ctx.fillStyle = color(band.color || "--raised");
      ctx.fillRect(x0, s.r.y, x1 - x0, s.r.h);
      ctx.globalAlpha = 1;
      if (band.label && x1 - x0 > 60) {
        ctx.fillStyle = color("--faint");
        ctx.textAlign = "left";
        ctx.textBaseline = "top";
        ctx.fillText(band.label, x0 + 6, s.r.y + 4);
      }
    }
  }

  function drawBars(s, series) {
    ctx.fillStyle = color(series.color);
    ctx.globalAlpha = series.opacity ?? 0.55;
    const pxW = Math.max(1, (series.barWidth / ((opts.x.max - opts.x.min) || 1)) * s.r.w);
    const base = s.ys(axisOf(series.axis).min, series.axis);
    for (const [x, v] of series.data) {
      if (v == null || v <= 0) continue;
      const top = Math.max(s.r.y, s.ys(v, series.axis));
      ctx.fillRect(s.xs(x) - pxW / 2, top, pxW, Math.max(1, base - top));
    }
    ctx.globalAlpha = 1;
  }

  function drawLine(s, series) {
    ctx.strokeStyle = color(series.color);
    ctx.lineWidth = series.width || 2;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    ctx.setLineDash(series.dash || []);
    ctx.beginPath();
    let pen = false;
    for (const [x, v] of series.data) {
      if (v == null) { pen = false; continue; }
      const px = s.xs(x), py = s.ys(v, series.axis);
      if (pen) ctx.lineTo(px, py); else ctx.moveTo(px, py);
      pen = true;
    }
    ctx.stroke();
    ctx.setLineDash([]);
  }

  function drawLevels(s) {
    for (const level of opts.levels || []) {
      const y = Math.round(s.ys(level.value, level.axis)) + 0.5;
      if (y < s.r.y || y > s.r.y + s.r.h) continue;
      ctx.strokeStyle = color(level.color);
      ctx.lineWidth = 1.5;
      ctx.setLineDash([5, 4]);
      ctx.beginPath(); ctx.moveTo(s.r.x, y); ctx.lineTo(s.r.x + s.r.w, y); ctx.stroke();
      ctx.setLineDash([]);
      if (!level.label) continue;
      // Labels sit at the left end: the newest data, on the right, stays visible
      ctx.font = "600 11.5px " + s.font;
      const w = ctx.measureText(level.label).width + 10;
      const lx = s.r.x + 4;
      ctx.fillStyle = color("--surface");
      ctx.fillRect(lx, y - 9, w, 18);
      ctx.fillStyle = color(level.color);
      ctx.textAlign = "left";
      ctx.textBaseline = "middle";
      ctx.fillText(level.label, lx + 5, y);
      ctx.font = "500 11.5px " + s.font;
    }
  }

  function drawMarkers(s) {
    for (const m of opts.markers || []) {
      const x = s.xs(m.x), y = Math.max(s.r.y + 4, s.ys(m.y, m.axis));
      ctx.beginPath();
      ctx.arc(x, y, 5.5, 0, Math.PI * 2);
      ctx.fillStyle = color(m.color);
      ctx.fill();
      ctx.lineWidth = 2;
      ctx.strokeStyle = color("--surface");
      ctx.stroke();
    }
  }

  function drawHover(s) {
    if (hoverX == null || !opts.tooltip) return hideTip();
    const info = opts.tooltip(hoverX);
    if (!info) return hideTip();
    const x = s.xs(info.x);
    ctx.strokeStyle = color("--faint");
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(Math.round(x) + 0.5, s.r.y); ctx.lineTo(Math.round(x) + 0.5, s.r.y + s.r.h); ctx.stroke();
    tip.replaceChildren(h("b", { text: info.title }),
      ...info.rows.map((row) => h("div", {}, h("i", { style: { background: color(row.color) } }), row.label + " ", h("strong", { text: row.value }))));
    tip.hidden = false;
    const tw = tip.offsetWidth;
    const left = x + 14 + tw > size.w ? x - 14 - tw : x + 14;
    tip.style.transform = "translate(" + Math.max(0, left) + "px, " + (s.r.y + 4) + "px)";
  }

  function hideTip() {
    tip.hidden = true;
  }

  function draw() {
    ctx.clearRect(0, 0, size.w, size.h);
    if (!opts) return;
    const s = scales();
    plot = s;
    if (opts.empty) {
      drawGrid(s);
      ctx.fillStyle = color("--faint");
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.font = "500 13px " + s.font;
      ctx.fillText(opts.empty, s.r.x + s.r.w / 2, s.r.y + s.r.h / 2);
      hideTip();
      return;
    }
    drawGrid(s);
    ctx.save();
    ctx.beginPath(); ctx.rect(s.r.x, s.r.y - 2, s.r.w, s.r.h + 2); ctx.clip();
    drawBands(s);
    for (const series of opts.series || []) {
      if (series.type === "bars") drawBars(s, series); else drawLine(s, series);
    }
    ctx.restore();
    drawLevels(s);
    drawMarkers(s);
    drawHover(s);
  }

  function pointer(ev) {
    if (!plot || opts.empty) return;
    const rect = canvas.getBoundingClientRect();
    const px = ev.clientX - rect.left;
    if (px < plot.r.x || px > plot.r.x + plot.r.w) { hoverX = null; draw(); return; }
    hoverX = opts.x.min + ((px - plot.r.x) / plot.r.w) * (opts.x.max - opts.x.min);
    draw();
    clearTimeout(touchTimer);
    if (ev.pointerType === "touch") touchTimer = setTimeout(() => { hoverX = null; draw(); }, TOUCH_TIP_MS);
  }

  canvas.addEventListener("pointermove", pointer);
  canvas.addEventListener("pointerdown", pointer);
  canvas.addEventListener("pointerleave", (ev) => {
    if (ev.pointerType !== "touch") { hoverX = null; draw(); }
  });
  const observer = new ResizeObserver(resize);
  observer.observe(container);
  window.addEventListener("q2:theme", draw);
  if (document.fonts) document.fonts.ready.then(draw);

  function update(next) {
    opts = next;
    if (next.ariaLabel) canvas.setAttribute("aria-label", next.ariaLabel);
    draw();
  }
  update(initial);

  return {
    update,
    destroy() { observer.disconnect(); window.removeEventListener("q2:theme", draw); },
  };
}

// Nearest point of a sorted [[x, y], ...] series to x
export function nearest(data, x) {
  if (!data.length) return null;
  let lo = 0, hi = data.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if (data[mid][0] < x) lo = mid; else hi = mid;
  }
  return Math.abs(data[lo][0] - x) <= Math.abs(data[hi][0] - x) ? lo : hi;
}
