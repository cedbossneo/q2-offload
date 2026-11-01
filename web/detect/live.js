// Failure detection page: the Live view (camera, verdict, risk rail, score chart, alerts).
import { $, $$, api, fmtAgo, fmtClock, fmtDuration, fmtNum, fmtPct, h, isNum, setText } from "/q2-assets/core.js";
import { createChart } from "/q2-assets/chart.js";
import { icon } from "/q2-assets/icons.js";
import { confirmDialog, toast, withBusy } from "/q2-assets/ui.js";
import { chain, deriveState, fmtScore, lastDecision, modeText, notices, PRINT_STATUS } from "./verdict.js";
import { renderBoxes, timelineStrip } from "./frame.js";
import { scoreChartOptions, scoreLegend } from "./scorechart.js";
import { decisionList } from "./decisions.js";

const RAIL_HEADROOM = 1.5;    // the rail ends at 1.5 x the pause level: the pause zone is its last third
const RESUME_TIMEOUT_MS = 180000;  // RESUME can run a long macro (reheat, purge) before Moonraker answers
const BLANK = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";

const clampPct = (v) => Math.min(100, Math.max(0, v)) + "%";

export function createLiveView({ applyStatus, retry }) {
  const el = {
    unreachable: $("#liveUnreachable"), notices: $("#liveNotices"), top: $("#liveTop"),
    vf: $("#vf"), media: $("#vfMedia"), frame: $("#vfFrame"), live: $("#vfLive"), boxes: $("#vfBoxes"),
    placeholder: $("#vfPlaceholder"), placeholderText: $("#vfPlaceholderText"), chip: $("#vfChip"), chipText: $("#vfChipText"),
    verdict: $("#verdict"), lamp: $("#vLamp"), status: $("#vStatus"), title: $("#vTitle"), file: $("#vFile"),
    rail: $("#rail"), railValue: $("#railValue"), tickWarn: $("#tickWarn"), tickPause: $("#tickPause"),
    why: $("#vWhy"), detail: $("#vDetail"), actions: $("#vActions"), ack: $("#ackBtn"), resume: $("#resumeBtn"), resumeText: $("#resumeText"), mute: $("#muteBtn"), muteText: $("#muteText"),
    mode: $("#vMode"), chain: $("#vChain"),
    printPanel: $("#livePrint"), chartTitle: $("#chartTitle"), chartAside: $("#chartAside"),
    alerts: $("#liveAlerts"), alertsTitle: $("#alertsTitle"), decisions: $("#liveDecisions"), timeline: $("#liveTimeline"), strip: $("#liveTimelineStrip"),
    announce: $("#announce"),
  };
  const chart = createChart($("#liveChart"), scoreChartOptions(null));
  $("#liveLegend").replaceWith(scoreLegend());
  let status = null;
  let current = null;
  let camMode = "frame";
  let frameT = null;
  let frameState = "waiting";    // waiting | ok | missing
  let decisionsKey = "";
  let timelineKey = "";
  let resuming = false;

  // ---------- Camera ----------
  function streamUrl() {
    return status && status.camera && status.camera.stream_url;
  }

  function showPlaceholder(text) {
    el.placeholder.hidden = false;
    setText(el.placeholderText, text);
  }

  function setCam(mode) {
    camMode = mode === "live" && streamUrl() ? "live" : "frame";
    $$("[data-cam]", el.vf).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.cam === camMode)));
    if (camMode === "live") {
      el.frame.hidden = true;
      el.boxes.hidden = true;
      el.live.hidden = false;
      showPlaceholder("Connecting to the camera");
      el.live.src = streamUrl();
    } else {
      el.live.src = BLANK;     // closes the MJPEG connection
      el.live.hidden = true;
      el.boxes.hidden = false;
      paintFrameState();
    }
    updateChip();
  }

  el.live.addEventListener("load", () => {
    if (camMode !== "live" || el.live.src === BLANK) return;
    el.placeholder.hidden = true;
    if (el.live.naturalWidth) el.media.style.aspectRatio = el.live.naturalWidth + " / " + el.live.naturalHeight;
  });
  el.live.addEventListener("error", () => {
    if (camMode === "live") showPlaceholder("The live stream doesn't answer: " + streamUrl());
  });
  $$("[data-cam]", el.vf).forEach((b) => b.addEventListener("click", () => setCam(b.dataset.cam)));
  document.addEventListener("visibilitychange", () => {
    if (document.hidden && camMode === "live") setCam("frame");
  });

  function paintFrameState() {
    if (camMode !== "frame") return;
    el.frame.hidden = frameState !== "ok";
    if (frameState === "ok") el.placeholder.hidden = true;
    else if (frameState === "missing") showPlaceholder("The last analysed frame isn't available.");
    else if (status && status.print) showPlaceholder("Waiting for the first frame of this print");
    else showPlaceholder("No frame analysed yet." + (streamUrl() ? " Switch to Live to check what the camera sees." : ""));
  }

  function updateFrame(print) {
    const lf = print && print.last_frame;
    if (!lf) {
      frameT = null;
      frameState = "waiting";
      renderBoxes(el.boxes, []);
      return paintFrameState();
    }
    if (lf.t === frameT) return;
    frameT = lf.t;
    const url = "/detect/api/frame.jpg?t=" + encodeURIComponent(lf.t);
    const loader = new Image();
    loader.addEventListener("load", () => {
      if (frameT !== lf.t) return;
      el.frame.src = url;
      el.media.style.aspectRatio = loader.naturalWidth + " / " + loader.naturalHeight;
      renderBoxes(el.boxes, lf.detections);
      frameState = "ok";
      paintFrameState();
    });
    loader.addEventListener("error", () => {
      if (frameT !== lf.t) return;
      frameState = "missing";
      renderBoxes(el.boxes, []);
      paintFrameState();
    });
    loader.src = url;
  }

  function updateChip() {
    if (camMode === "live") {
      el.chip.dataset.mode = "live";
      return setText(el.chipText, "Live camera");
    }
    el.chip.dataset.mode = "frame";
    const lf = status && status.print && status.print.last_frame;
    if (!lf) return setText(el.chipText, "No analysed frame");
    const n = (lf.detections || []).length;
    const boxes = n ? ", " + n + (n === 1 ? " box" : " boxes") : ", nothing seen";
    setText(el.chipText, (current && current.active ? "Analysed " : "Last analysed ") + fmtAgo(lf.t) + boxes);
  }

  // ---------- Verdict ----------
  function fileLine(print) {
    if (!print) return "";
    if (current.active) {
      const progress = status.printer && isNum(status.printer.progress) ? fmtPct(status.printer.progress) + " printed, " : "";
      return print.filename + "\n" + progress + "watched for " + fmtDuration(Date.now() / 1000 - print.started);
    }
    const [label] = PRINT_STATUS[print.status] || [print.status];
    return "Last print: " + print.filename + "\n" + label + " " + fmtAgo(print.ended || print.started);
  }

  function renderRail(print) {
    const levels = print && print.levels;
    el.rail.hidden = !(current.watching && levels && isNum(levels.warning) && isNum(levels.pause));
    if (el.rail.hidden) return;
    // Fixed scale: the zones never move, a score past the end pins the needle there
    const score = isNum(print.score) ? print.score : 0;
    const max = levels.pause * RAIL_HEADROOM;
    const pct = (v) => clampPct((v / max) * 100);
    el.rail.classList.toggle("over", score > max);
    el.rail.style.setProperty("--warn", pct(levels.warning));
    el.rail.style.setProperty("--pause", pct(levels.pause));
    el.rail.style.setProperty("--score", pct(Math.max(0, score)));
    const zone = score >= levels.pause ? ["halt", "above the pause level"]
      : score >= levels.warning ? ["caution", "above the warning level"] : ["clear", "below the warning level"];
    const quiet = print.muted || ["warmup", "camera", "ml-down"].includes(current.key);
    el.rail.dataset.tone = quiet ? "neutral" : zone[0];
    el.rail.setAttribute("aria-valuemax", Math.max(max, score).toFixed(2));
    el.rail.setAttribute("aria-valuenow", score.toFixed(2));
    el.rail.setAttribute("aria-valuetext", fmtScore(score) + ", " + zone[1]);
    setText(el.railValue, fmtScore(print.score));
    setText(el.tickWarn, "Warning " + fmtNum(levels.warning));
    setText(el.tickPause, "Pause " + fmtNum(levels.pause));
  }

  function renderChain() {
    el.chain.replaceChildren(...chain(status).map(([name, value, tone]) =>
      h("li", { dataset: { tone } }, h("span", { class: "lamp" }), h("span", { class: "muted", text: name }), h("b", { text: value }))));
  }

  function renderNotices() {
    el.notices.replaceChildren(...notices(status, current).map((n) =>
      h("div", { class: "notice", dataset: { tone: n.tone }, role: "status" }, icon(n.icon),
        h("div", {}, h("p", {}, h("strong", { text: n.title })), h("p", { text: n.text })))));
  }

  // ---------- Print: chart, alerts, timeline ----------
  function renderPrint(print) {
    chart.update(scoreChartOptions(print));
    setText(el.chartTitle, current.active ? "Score during this print" : print ? "Score during the last print" : "Score");
    setText(el.alertsTitle, current.active ? "Alerts in this print" : "Alerts in the last print");
    const peak = print && print.series ? Math.max(0, ...print.series.score.filter(isNum)) : null;
    setText(el.chartAside, print && isNum(print.frame) ? "Peak " + fmtScore(peak) + ", " + print.frame + " frames analysed" : "");

    const dKey = print ? print.id + "|" + (print.decisions || []).map((d) => d.n + ":" + d.label).join(",") : "";
    if (dKey !== decisionsKey) {
      decisionsKey = dKey;
      const has = Boolean(print && (print.decisions || []).length);
      el.alerts.hidden = !has;
      el.decisions.replaceChildren(has ? decisionList(print, (updated) => {
        if (updated && status && status.print && status.print.id === updated.id) {
          applyStatus({ ...status, print: { ...status.print, decisions: updated.decisions } });
        } else {
          decisionsKey = "";
          renderPrint(status.print);
        }
      }) : "");
    }
    const tKey = print ? print.id + "|" + (print.timeline || []).map((f) => f.file).join(",") : "";
    if (tKey !== timelineKey) {
      timelineKey = tKey;
      const has = Boolean(print && (print.timeline || []).length);
      el.timeline.hidden = !has;
      el.strip.replaceChildren(has ? timelineStrip(print) : "");
    }
  }

  // ---------- Actions ----------
  el.ack.addEventListener("click", () => withBusy(el.ack, async () => {
    try {
      applyStatus(await api("/detect/api/ack", { method: "POST" }));
      toast("Alert dismissed. Still watching.");
    } catch (err) {
      toast("Couldn't dismiss the alert: " + err.message, "halt");
    }
  }));
  el.mute.addEventListener("click", async () => {
    const name = status && status.print ? status.print.filename : "this print";
    const ok = await confirmDialog({
      title: "Mute until this print ends?",
      body: "No alert and no pause for " + name + ". Frames are still analysed and shown here. The next print is watched normally.",
      confirm: "Mute this print",
    });
    if (!ok) return;
    await withBusy(el.mute, async () => {
      try {
        applyStatus(await api("/detect/api/mute", { method: "POST" }));
        toast("Muted until this print ends.");
      } catch (err) {
        toast("Couldn't mute: " + err.message, "halt");
      }
    });
  });

  // Resume: Moonraker on the same origin. A detection pause asks first and closes the alert.
  function paintResume() {
    el.resume.hidden = !(current.canResume || resuming);
    el.resume.disabled = resuming;
    el.resume.classList.toggle("pending", resuming);
    el.resume.classList.toggle("btn-primary", !current.canAck);
    setText(el.resumeText, resuming ? "Resuming…" : "Resume print");
  }

  async function confirmResume() {
    if (!current.confirmResume) return true;
    const last = lastDecision(status.print);
    return confirmDialog({
      title: "Resume the print?",
      body: "Obico saw a failure" + (last ? " at " + fmtClock(last.t) : "") + ": check the print before resuming, a tangle can wrap " +
        "around the nozzle." + (status.print.alert_pending ? " Resuming also marks the alert as fine." : ""),
      confirm: "Resume print",
    });
  }

  el.resume.addEventListener("click", async () => {
    if (resuming || !(await confirmResume())) return;
    resuming = true;
    paintResume();
    try {
      if (current.confirmResume && status.print.alert_pending) applyStatus(await api("/detect/api/ack", { method: "POST" }));
      await api("/printer/print/resume", { method: "POST", timeout: RESUME_TIMEOUT_MS });
      toast("Print resumed");
    } catch (err) {
      toast("Couldn't resume the print: " + err.message, "halt");
    } finally {
      resuming = false;
      if (status) render(status);
    }
  });

  // ---------- Render ----------
  function render(next) {
    status = next;
    const previous = current;
    current = deriveState(status);
    const print = status.print;
    el.unreachable.hidden = true;
    el.top.hidden = false;
    el.printPanel.hidden = !print;

    el.verdict.dataset.tone = current.tone;
    el.vf.dataset.tone = current.tone;
    el.lamp.classList.toggle("pulse", current.pulse);
    setText(el.status, current.label);
    setText(el.title, current.title);
    setText(el.file, fileLine(print));
    setText(el.why, current.why);
    setText(el.detail, current.detail);
    renderRail(print);

    el.actions.hidden = !(current.watching || current.canResume || resuming);
    el.ack.hidden = !current.canAck;
    el.mute.hidden = !current.watching;
    el.mute.disabled = !current.canMute;
    paintResume();
    setText(el.muteText, print && print.muted ? "Muted until the print ends" : "Mute for this print");
    el.mode.replaceChildren(modeText(current.mode) + " ", h("a", { href: "#settings", text: "Change" }));
    renderChain();
    renderNotices();

    if (camMode === "live" && !streamUrl()) setCam("frame");
    $$("[data-cam='live']", el.vf).forEach((b) => {
      b.disabled = !streamUrl();
      b.title = streamUrl() ? "" : "Moonraker has no live stream for this camera";
    });
    updateFrame(print);
    updateChip();
    renderPrint(print);

    if (previous && previous.key !== current.key) el.announce.textContent = current.label + ": " + current.title;
  }

  function unreachable(err, hadData) {
    if (hadData) {
      el.notices.replaceChildren(h("div", { class: "notice", dataset: { tone: "halt" }, role: "alert" }, icon("plug"),
        h("div", {}, h("p", {}, h("strong", { text: "Lost contact with the detection service" })),
          h("p", { text: (err ? err.message + ". " : "") + "What you see may be out of date. Retrying every 10 seconds." }))));
      return;
    }
    const retryBtn = h("button", { class: "btn", type: "button" }, icon("refresh"), "Try again");
    retryBtn.addEventListener("click", () => withBusy(retryBtn, () => retry().catch(() => {})));
    el.unreachable.replaceChildren(h("div", { class: "state", dataset: { tone: "halt" } }, icon("plug"),
      h("h2", { text: "Can't reach the detection service" }),
      h("p", { text: err ? "The page got: " + err.message + "." : "" }),
      h("p", {}, "Check that the q2-detect service runs on the printer host (", h("code", { text: "systemctl status q2-detect" }),
        "). The page tries again every 10 seconds."),
      h("div", { class: "row" }, retryBtn)));
    el.unreachable.hidden = false;
    el.top.hidden = true;
    el.printPanel.hidden = true;
    el.alerts.hidden = true;
    el.timeline.hidden = true;
    decisionsKey = "";
    timelineKey = "";
  }

  return {
    render,
    unreachable,
    tick() { if (status) { updateChip(); setText(el.file, fileLine(status.print)); } },
    leave() { if (camMode === "live") setCam("frame"); },
  };
}
