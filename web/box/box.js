// q2-offload: Box drying page. Polls Moonraker (same origin) every 2 s, sends Happy Hare G-code.
import { $, api, fmtClock, h, isNum, setText } from "/q2-assets/core.js";
import { createChart, nearest, timeLabel } from "/q2-assets/chart.js";
import { hydrateIcons } from "/q2-assets/icons.js";
import { initTheme, showMsg } from "/q2-assets/ui.js";

const POLL_MS = 2000;
const HUMIDITY_POINTS = 600;            // 20 min at POLL_MS, like Moonraker's temperature store
const STORE_REFRESH_MS = 10000;
const PRINTING = ["printing", "paused"];
// Happy Hare forgets a gate's material when it is ejected: remember it to pick the
// drying temperature of the spools out (kept across reloads of the page)
const MATERIALS_KEY = "q2-box-materials";

hydrateIcons();
initTheme($("#themeBtn"));

const obj = { heater: null, env: null };     // Klipper object names, found at start
let dryingData = {};                         // material -> [temp, minutes]
let heaterMax = null;
let humidity = [];                           // [unix seconds, %RH] sampled by this page
let mode = "loaded";                         // "loaded" or "out" (spools ejected, rotating)
let modeTouched = false;
let knownMaterials = readMaterials();
let last = null;                             // last status
let autoPlanNow = null;                      // automatic temperature/time for the current mode
let busy = false;                            // a G-code command is running
let store = { data: null, at: 0, loading: false };

function readMaterials() {
  try { return JSON.parse(localStorage.getItem(MATERIALS_KEY)) || {}; } catch { return {}; }
}

// ---------- Moonraker ----------
async function moonraker(path, options) {
  return (await api(path, options)).result;
}

function gcode(script) {
  return moonraker("/printer/gcode/script", { method: "POST", body: { script }, timeout: 30000 });
}

// Happy Hare drying_data is a Python dict literal: {'PLA': (45, 300), ...}
function parseDryingData(text) {
  const out = {};
  for (const m of String(text || "").matchAll(/'([^']+)'\s*:\s*\(\s*([\d.]+)\s*,\s*([\d.]+)\s*\)/g)) {
    out[m[1].toUpperCase()] = [Number(m[2]), Number(m[3])];
  }
  return out;
}

async function discover() {
  const s = (await moonraker("/printer/objects/query?mmu_machine&configfile=settings")).status;
  const unit = s.mmu_machine && s.mmu_machine.unit_0;
  if (!unit) throw new Error("Happy Hare has no unit");
  obj.heater = unit.filament_heater;
  // environment_sensor is the temperature_sensor; the humidity is on the chip object of the same name
  const envName = (unit.environment_sensor || "").split(" ").pop();
  const list = (await moonraker("/printer/objects/list")).objects;
  obj.env = list.find((o) => o.endsWith(" " + envName) && !o.startsWith("temperature_sensor")) || unit.environment_sensor;
  const settings = s.configfile.settings;
  dryingData = parseDryingData((settings.mmu_parameters || {}).drying_data);
  const unitParams = settings["mmu_unit_parameters " + unit.name] || {};
  heaterMax = Number(unitParams.heater_max_temp) || null;
  setText($("#cap"), heaterMax || "–");
  const hum = Number(unitParams.heater_default_dry_humidity);
  if (hum && !$("#fHum").value) $("#fHum").value = hum;
}

async function poll() {
  const names = [
    "mmu=drying_state,drying,gate_status,gate_material,gate_color,gate_filament_name,enabled,filament,gate,action",
    encodeURIComponent(obj.heater), encodeURIComponent(obj.env),
    "print_stats=state", "gcode_macro%20MMU_KEEP_DRY", "gcode_macro%20_BOX_PRINT_HEAT=active",
    "temperature_sensor%20unit0_heater_temp_a", "temperature_sensor%20unit0_heater_temp_b",
  ];
  const r = await moonraker("/printer/objects/query?" + names.join("&"));
  last = { eventtime: r.eventtime, ...r.status };
  render();
}

// ---------- Drying plan ----------
function fmtDuration(seconds) {
  const m = Math.max(0, Math.round(seconds / 60));
  return Math.floor(m / 60) + " h " + String(m % 60).padStart(2, "0");
}

const fmtHours = (minutes) => String(Number((minutes / 60).toFixed(1)));

// What Happy Hare would choose for an automatic cycle with the loaded spools
function autoPlan(materials) {
  const known = materials.map((m) => dryingData[m.toUpperCase()]).filter(Boolean);
  if (!known.length) return null;
  let temp = Math.min(...known.map((k) => k[0]));
  if (heaterMax) temp = Math.min(temp, heaterMax);
  return { temp, minutes: Math.max(...known.map((k) => k[1])) };
}

function rememberMaterials(mmu) {
  const next = { ...knownMaterials };
  (mmu.gate_status || []).forEach((status, i) => {
    const material = (mmu.gate_material[i] || "").trim();
    if (status !== 0 && material) next[i] = material;
  });
  knownMaterials = next;
  try { localStorage.setItem(MATERIALS_KEY, JSON.stringify(knownMaterials)); } catch { /* private window */ }
}

// Gates a cycle would dry in the current mode, with the material used for the temperature
function dryingGates(mmu) {
  return (mmu.gate_status || []).map((status, i) => ({
    gate: i, empty: status === 0,
    material: status === 0 ? knownMaterials[i] || "" : (mmu.gate_material[i] || "").trim(),
  })).filter((g) => (mode === "out" ? g.empty : !g.empty));
}

function canEject(mmu, gate, printing) {
  // Never the gate whose filament is in the bowden or the toolhead
  const inUse = mmu.filament !== "Unloaded" && mmu.gate === gate;
  return !printing && !inUse && mmu.action === "Idle";
}

// ---------- Spools ----------
const HEX = /^[0-9a-f]{6}$/i;

function spoolDisc(index, colour, kind, drying) {
  const fill = colour && HEX.test(colour) ? "#" + colour : null;
  const wind = kind === "loaded"
    ? '<circle class="wind" cx="50" cy="50" r="39"' + (fill ? ' fill="' + fill + '"' : ' fill="var(--raised)"') + '/>' +
      '<circle class="groove" cx="50" cy="50" r="32"/><circle class="groove" cx="50" cy="50" r="25"/>'
    : '<circle class="wind-out" cx="50" cy="50" r="38"/>';
  const ring = drying ? '<circle class="dry-ring ' + drying + '" cx="50" cy="50" r="49"/>' : "";
  const tpl = document.createElement("template");
  tpl.innerHTML = '<svg class="spool-disc" viewBox="0 0 100 100" aria-hidden="true">' + ring +
    '<circle class="flange" cx="50" cy="50" r="46"/>' + wind +
    '<circle class="hub" cx="50" cy="50" r="15"/><text class="hub-text" x="50" y="50">T' + index + "</text></svg>";
  return tpl.content.firstElementChild;
}

function spoolItem(mmu, i, printing) {
  const status = mmu.gate_status[i];
  const empty = status === 0;
  const material = empty ? knownMaterials[i] || "" : (mmu.gate_material[i] || "").trim();
  const kind = !empty ? "loaded" : mode === "out" && material ? "out" : "empty";
  const dryState = (mmu.drying_state || [])[i];
  const drying = dryState === "active" || dryState === "queued" ? dryState : "";
  const dd = dryingData[material.toUpperCase()];
  const title = empty ? (material ? material : "Empty") : material || "Unknown material";
  const children = [
    spoolDisc(i, empty ? null : mmu.gate_color[i], kind, drying),
    h("div", { class: "spool-info" },
      h("p", { class: "spool-mat" }, h("span", { class: "visually-hidden", text: "Gate " + i + ": " }), title,
        kind === "out" ? h("span", { class: "spool-tag", text: "out" }) : null),
      h("p", { class: "spool-name", text: empty ? (material ? "Ejected for drying" : "No spool") : mmu.gate_filament_name[i] || "" }),
      h("p", { class: "spool-dry", text: !material ? "" : dd ? "Dries at " + dd[0] + " °C, " + fmtHours(dd[1]) + " h" : "No drying data" })),
  ];
  // The heat ring shows a gate being dried; a queued gate (waiting for a free heater) says so
  if (drying === "queued") children.push(h("span", { class: "badge spool-badge", dataset: { tone: "heat" }, text: "Queued" }));
  if (drying === "active") children[1].prepend(h("span", { class: "visually-hidden", text: "Drying now. " }));
  if (mode === "out" && !empty) {
    const ok = canEject(mmu, i, printing) && !busy;
    const inUse = mmu.filament !== "Unloaded" && mmu.gate === i;
    const eject = h("button", { type: "button", class: "btn btn-sm spool-eject", disabled: !ok,
      title: ok ? "MMU_EJECT GATE=" + i : "Filament in use or a print is running" },
    inUse ? "In use" : printing ? "Printing" : "Eject");
    eject.addEventListener("click", () => run($("#dryMsg"), "MMU_EJECT GATE=" + i, "T" + i + " ejected: secure the end to its spool"));
    children.push(eject);
  }
  return h("li", { class: "spool", dataset: { kind, drying } }, children);
}

function renderGates(mmu, printing) {
  rememberMaterials(mmu);
  const gates = $("#gates");
  gates.removeAttribute("aria-busy");
  gates.replaceChildren(...(mmu.gate_status || []).map((_, i) => spoolItem(mmu, i, printing)));
  const plan = autoPlan(dryingGates(mmu).map((g) => g.material).filter(Boolean));
  setText($("#auto"), plan
    ? "Automatic cycle for the spools " + (mode === "out" ? "out" : "loaded") + ": " + plan.temp + " °C for " + fmtHours(plan.minutes) + " h."
    : mode === "out" ? "No spool out yet: eject the spools to dry." : "No loaded spool with drying data: an automatic cycle uses Happy Hare's default.");
  return plan;
}

// ---------- Climate ----------
function renderClimate(s, heater, env, drying, printHeat, cycle) {
  if (env.humidity != null) {
    setText($("#hum"), Math.round(env.humidity));
    humidity = [...humidity, [Date.now() / 1000, env.humidity]].slice(-HUMIDITY_POINTS);
  }
  setText($("#humSub"), isNum(env.temperature) ? "Inside the Box, air at " + env.temperature.toFixed(0) + " °C" : "Inside the Box");
  setText($("#temp"), heater.temperature != null ? heater.temperature.toFixed(1) : "–");
  $(".reading-heat").dataset.on = String(Boolean(heater.target));
  const elements = ["a", "b"].map((x) => (s["temperature_sensor unit0_heater_temp_" + x] || {}).temperature).filter((t) => t != null);
  const hottest = elements.length ? Math.max(...elements).toFixed(0) + " °C" : "?";
  setText($("#target"), heater.target
    ? "Target " + heater.target + " °C, " + Math.round((heater.power || 0) * 100) + " % power, hottest element " + hottest
    : "Heater off");

  const state = $("#state");
  state.dataset.tone = drying ? "heat" : printHeat ? "accent" : "neutral";
  setText(state, drying ? "Drying" : printHeat ? "Print heating" : "Idle");
  let detail = "", times = "", progress = null;
  if (drying && cycle) {
    const left = cycle.end_time - s.eventtime;
    detail = cycle.temp + " °C, " + fmtDuration(left) + " left" + (cycle.rotate ? ", spools rotating" : "");
    if (cycle.humidity_target != null) detail += ", or until " + cycle.humidity_target + " % RH";
    progress = 1 - left / (cycle.end_time - cycle.start_time);
    const now = Date.now() / 1000;
    times = "Started " + fmtClock(now - (s.eventtime - cycle.start_time)) + ", ends around " + fmtClock(now + left);
  } else if (drying) {
    detail = "Time left not reported by this Happy Hare";
  } else if (printHeat) {
    detail = "Set by the print for the loaded materials";
  } else {
    detail = "No drying cycle running";
  }
  setText($("#stateDetail"), detail);
  setText($("#stateTimes"), times);
  $("#barWrap").hidden = progress == null;
  if (progress != null) {
    const pct = Math.min(100, Math.max(0, progress * 100));
    $("#bar").style.width = pct + "%";
    $("#barWrap").setAttribute("aria-valuenow", pct.toFixed(0));
  }
}

// ---------- Forms ----------
function renderDryForm(mmu, drying, printing) {
  const nothingOut = mode === "out" && !dryingGates(mmu).length;
  const reason = printing ? "The Box is managed by the print." : drying ? "A cycle is already running."
    : !mmu.enabled ? "Happy Hare is disabled." : nothingOut ? "Eject at least one spool first." : "";
  $("#start").disabled = Boolean(reason) || busy;
  $("#stop").disabled = !drying || busy;
  setText($("#startHint"), reason);
  $("#fTemp").placeholder = autoPlanNow ? "auto: " + autoPlanNow.temp : mode === "out" ? "required" : "auto";
  $("#fHours").placeholder = autoPlanNow ? "auto: " + fmtHours(autoPlanNow.minutes) : "auto";
}

function renderKeepDry(keep) {
  const editing = [$("#kTrig"), $("#kTarget")].includes(document.activeElement);
  if (!editing) {
    $("#kTrig").value = keep.trigger ?? "";
    $("#kTarget").value = keep.target ?? "";
  }
  setText($("#kInterval"), keep.interval ? Math.round(keep.interval / 60) : "–");
  const toggle = $("#keepEnable");
  if (!busy) {
    toggle.checked = Boolean(keep.enable);
    toggle.disabled = false;
  }
  setText($("#keepState"), keep.enable
    ? "On: a cycle starts above " + (keep.trigger ?? "?") + " % RH and runs down to " + (keep.target ?? "?") + " %"
    : "Off: the Box only dries when you start a cycle");
}

function render() {
  const s = last, mmu = s.mmu || {}, heater = s[obj.heater] || {}, env = s[obj.env] || {};
  const printHeat = (s["gcode_macro _BOX_PRINT_HEAT"] || {}).active;
  const printing = PRINTING.includes((s.print_stats || {}).state);
  const drying = (mmu.drying_state || []).some((d) => d === "active" || d === "queued");
  const cycle = (mmu.drying || [])[0];
  // A running cycle that rotates the spools shows the spools-out view
  if (cycle && cycle.rotate && mode !== "out" && !modeTouched) return setMode("out");

  renderClimate(s, heater, env, drying, printHeat, cycle);
  autoPlanNow = renderGates(mmu, printing);
  renderDryForm(mmu, drying, printing);
  renderKeepDry(s["gcode_macro MMU_KEEP_DRY"] || {});
  drawChart();
}

// ---------- Chart ----------
const chart = createChart($("#chart"), { empty: "Loading…", x: { min: 0, max: 1, time: true }, y: { min: 0, max: 1 } });

async function drawChart() {
  if (!store.loading && Date.now() - store.at >= STORE_REFRESH_MS) {
    store = { ...store, loading: true };
    try {
      const data = await moonraker("/server/temperature_store");
      store = { data: data[obj.heater], at: Date.now(), loading: false };
    } catch {
      store = { ...store, loading: false };   // keep the previous curve
    }
  }
  redrawChart();
}

function redrawChart() {
  const data = store.data || { temperatures: [], targets: [] };
  // Moonraker keeps one point per second, the newest last: that sets the time window
  const now = Date.now() / 1000;
  const span = Math.max(data.temperatures.length, 60);
  const series = (values) => values.map((v, i) => [now - (values.length - 1 - i), v]);
  const temps = series(data.temperatures);
  const targets = series(data.targets || []);
  const hum = humidity.filter(([t]) => t >= now - span);
  const tMax = Math.max(40, ...data.temperatures, ...(data.targets || [])) + 5;
  setText($("#chartAside"), "Scale up to " + Math.round(tMax) + " °C and 100 % RH");
  chart.update({
    empty: temps.length ? null : "No temperature history yet",
    x: { min: now - span, max: now, time: true },
    y: { min: 0, max: tMax, format: (v) => v + "°" },
    y2: { min: 0, max: 100, format: (v) => v + "%" },
    series: [
      { type: "line", data: targets, color: "--faint", width: 1.5, dash: [5, 4] },
      { type: "line", data: temps, color: "--heat", width: 2.2 },
      { type: "line", data: hum, color: "--moisture", width: 2.2, axis: "y2" },
    ],
    tooltip(x) {
      const i = nearest(temps, x);
      if (i == null) return null;
      const j = nearest(hum, temps[i][0]);
      const rows = [
        { label: "Heater", value: temps[i][1].toFixed(1) + " °C", color: "--heat" },
        { label: "Target", value: targets[i] ? targets[i][1] + " °C" : "–", color: "--faint" },
      ];
      if (j != null && Math.abs(hum[j][0] - temps[i][0]) < 10) rows.push({ label: "Humidity", value: hum[j][1].toFixed(0) + " %", color: "--moisture" });
      return { x: temps[i][0], title: timeLabel(temps[i][0]), rows };
    },
    ariaLabel: "Heater temperature and humidity over the last " + Math.round(span / 60) + " minutes",
  });
}

// ---------- Actions ----------
async function run(el, script, done) {
  busy = true;
  showMsg(el, "Sending " + script + "…");
  if (last) render();
  try {
    await gcode(script);
    showMsg(el, done, "clear");
  } catch (e) {
    showMsg(el, e.message, "halt");
  } finally {
    busy = false;
  }
  try { await poll(); } catch { /* the loop reports connection problems */ }
}

function setMode(next, byUser) {
  if (byUser) modeTouched = true;
  mode = next;
  $("#modeLoaded").setAttribute("aria-pressed", String(mode === "loaded"));
  $("#modeOut").setAttribute("aria-pressed", String(mode === "out"));
  $("#outHelp").hidden = mode !== "out";
  if (last) render();
}

$("#dryForm").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const parts = ["MMU_HEATER DRY=1"];
  let temp = $("#fTemp").value, hours = $("#fHours").value;
  const hum = $("#fHum").value;
  if (mode === "out") {
    // Happy Hare no longer knows the material of an ejected gate: send the values
    parts.push("ROTATE=1 GATES=" + dryingGates(last.mmu).map((g) => g.gate).join(","));
    if (!temp && autoPlanNow) temp = autoPlanNow.temp;
    if (!hours && autoPlanNow) hours = autoPlanNow.minutes / 60;
    if (!temp) {
      $("#fTemp").focus();
      return showMsg($("#dryMsg"), "Unknown material for the spools out: enter a temperature", "halt");
    }
  }
  if (temp) parts.push("TEMP=" + Number(temp));
  if (hours) parts.push("TIMER=" + Math.round(Number(hours) * 60));
  if (hum) parts.push("HUMIDITY=" + Number(hum));
  run($("#dryMsg"), parts.join(" "), "Drying started");
});
$("#modeLoaded").addEventListener("click", () => setMode("loaded", true));
$("#modeOut").addEventListener("click", () => setMode("out", true));
$("#stop").addEventListener("click", () => run($("#dryMsg"), "MMU_HEATER STOP=1", "Drying stopped"));
$("#keepForm").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const trig = Number($("#kTrig").value), target = Number($("#kTarget").value);
  if (!(target < trig)) return showMsg($("#keepMsg"), "The threshold must be above the target humidity", "halt");
  run($("#keepMsg"), "MMU_KEEP_DRY TRIGGER=" + trig + " TARGET=" + target, "Saved (until Klipper restarts)");
});
$("#keepEnable").addEventListener("change", (ev) => {
  const on = ev.target.checked;
  ev.target.disabled = true;
  run($("#keepMsg"), "MMU_KEEP_DRY ENABLE=" + (on ? 1 : 0), on ? "Keep dry on" : "Keep dry off");
});

// ---------- Connection ----------
function setConnected(ok, message) {
  $("#conn").dataset.tone = ok ? "clear" : "halt";
  setText($("#connText"), ok ? "Connected" : "No connection");
  $("#conn").title = ok ? "Connected to Klipper" : "No connection to Klipper: " + message;
  $("#connNotice").hidden = ok;
  document.body.classList.toggle("stale", !ok);
  if (!ok) {
    setText($("#connError"), message + ". The page tries again every 2 seconds.");
    ["#start", "#stop", "#keepEnable", "#keepSave"].forEach((sel) => { $(sel).disabled = true; });
    document.querySelectorAll(".spool-eject").forEach((b) => { b.disabled = true; });
  } else {
    $("#keepSave").disabled = false;
  }
}

async function loop() {
  try {
    if (!obj.heater) await discover();
    await poll();
    setConnected(true);
  } catch (e) {
    setConnected(false, e.message);
    obj.heater = null;          // Klipper may have restarted with another config
  }
  setTimeout(loop, POLL_MS);
}

hydrateSkeleton();
loop();

function hydrateSkeleton() {
  $("#gates").replaceChildren(...[0, 1, 2, 3].map(() =>
    h("li", { class: "spool spool-skeleton" }, h("span", { class: "spool-disc skeleton" }),
      h("div", { class: "spool-info" }, h("span", { class: "skeleton", style: { width: "50%", height: "16px" } }),
        h("span", { class: "skeleton", style: { width: "80%", height: "12px", marginTop: "8px" } })))));
}
