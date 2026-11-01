// Failure detection page: History view (summary, list of prints, one print's detail).
import { $, api, fmtDuration, fmtNum, fmtWhen, h, isNum, plural } from "/q2-assets/core.js";
import { createChart } from "/q2-assets/chart.js";
import { icon } from "/q2-assets/icons.js";
import { confirmDialog, toast, withBusy } from "/q2-assets/ui.js";
import { ACTIVE, fmtScore, PRINT_STATUS } from "./verdict.js";
import { printFileUrl, timelineStrip } from "./frame.js";
import { scoreChartOptions, scoreLegend } from "./scorechart.js";
import { decisionList } from "./decisions.js";

const LIST_LIMIT = 50;
const FILTERS = [["all", "All prints"], ["alerts", "With alerts"], ["review", "To review"]];

function errorState(message, onRetry) {
  const retry = h("button", { class: "btn", type: "button" }, icon("refresh"), "Try again");
  retry.addEventListener("click", onRetry);
  return h("div", { class: "panel" }, h("div", { class: "state", dataset: { tone: "halt" } }, icon("plug"),
    h("h2", { text: "Couldn't load the history" }), h("p", { text: message }), h("div", { class: "row" }, retry)));
}

function loadingList() {
  const row = () => h("li", { class: "print-row skeleton-row" },
    h("span", { class: "print-thumb skeleton" }), h("span", { class: "print-main" },
      h("span", { class: "skeleton", style: { width: "60%", height: "14px" } }),
      h("span", { class: "skeleton", style: { width: "35%", height: "12px", marginTop: "8px" } })));
  return h("div", { class: "panel", "aria-busy": "true" }, h("ul", { class: "prints", "aria-label": "Loading prints" }, row(), row(), row()));
}

function summarySentence(s, onReview) {
  const strong = (text, tone) => h("strong", { dataset: tone ? { tone } : null, class: tone ? "toned" : null, text });
  const first = h("p", { class: "summary-lead" },
    strong(plural(s.prints, "print")), " watched, ", strong(fmtNum(s.watched_hours, 1) + " hours"), " in all.");
  const alerts = s.warnings + s.pauses;
  const second = alerts
    ? h("p", {}, strong(plural(s.warnings, "warning"), s.warnings ? "caution" : null), " and ",
      strong(plural(s.pauses, "pause"), s.pauses ? "halt" : null), ". You marked ",
      strong(plural(s.false_alarms, "false alarm")), " and ", strong(plural(s.real_failures, "real failure")), ".")
    : h("p", { text: "No alert so far." });
  const parts = [first, second];
  if (s.unreviewed) {
    const btn = h("button", { class: "btn btn-sm", type: "button" }, plural(s.unreviewed, "alert") + " to review");
    btn.addEventListener("click", onReview);
    parts.push(h("div", { class: "row" }, btn));
  }
  return h("div", { class: "panel summary" }, ...parts);
}

function printFlags(p) {
  const flags = [];
  if (p.status !== "completed") {
    const [label, tone] = PRINT_STATUS[p.status] || [p.status, "neutral"];
    flags.push(h("span", { class: "badge plain", dataset: { tone }, text: label }));
  }
  if (p.pauses) flags.push(h("span", { class: "badge", dataset: { tone: "halt" }, text: plural(p.pauses, "pause") }));
  if (p.warnings) flags.push(h("span", { class: "badge", dataset: { tone: "caution" }, text: plural(p.warnings, "warning") }));
  if (p.unreviewed) flags.push(h("span", { class: "badge plain", dataset: { tone: "accent" }, text: p.unreviewed + " to review" }));
  if (p.real_failures) flags.push(h("span", { class: "badge plain", dataset: { tone: "halt" }, text: "Real failure" }));
  else if (p.false_alarms) flags.push(h("span", { class: "badge plain", dataset: { tone: "neutral" }, text: "False alarm" }));
  return flags;
}

function printRow(p) {
  const duration = isNum(p.ended) ? fmtDuration(p.ended - p.started) : "running";
  const thumb = p.thumbnail
    ? h("img", { src: printFileUrl(p.id, p.thumbnail), alt: "", loading: "lazy", decoding: "async" })
    : icon("camera");
  return h("li", {}, h("a", { class: "print-row", href: "#history/" + encodeURIComponent(p.id) },
    h("span", { class: "print-thumb" }, thumb),
    h("span", { class: "print-main" },
      h("span", { class: "print-name", text: p.filename }),
      h("span", { class: "print-meta", text: fmtWhen(p.started) + ", " + duration + ", " + plural(p.frames || 0, "frame") })),
    h("span", { class: "print-flags" }, printFlags(p)),
    h("span", { class: "print-peak" }, h("span", { class: "muted", text: "Peak" }), h("b", { text: fmtScore(p.max_score) })),
    icon("chevronRight", "print-go")));
}

export function createHistoryView({ getStatus, onSummary }) {
  const listRoot = $("#historyList");
  const detailRoot = $("#historyDetail");
  let filter = "all";
  let data = null;
  let detailChart = null;

  function filtered() {
    const prints = data.prints || [];
    if (filter === "alerts") return prints.filter((p) => p.warnings || p.pauses);
    if (filter === "review") return prints.filter((p) => p.unreviewed);
    return prints;
  }

  function renderList() {
    const s = data.summary || {};
    if (!s.prints) {
      listRoot.replaceChildren(h("div", { class: "panel" }, h("div", { class: "state" }, icon("clock"),
        h("h2", { text: "No print watched yet" }),
        h("p", { text: "Every print shows up here with its score chart, its alerts and a camera frame every 10 minutes. Start a print to fill it." }))));
      return;
    }
    const seg = h("div", { class: "seg seg-sm", role: "group", "aria-label": "Show" }, FILTERS.map(([key, label]) => {
      const b = h("button", { type: "button", "aria-pressed": String(filter === key) }, label);
      b.addEventListener("click", () => { filter = key; renderList(); });
      return b;
    }));
    const items = filtered();
    const more = s.prints > (data.prints || []).length
      ? h("p", { class: "panel-note", text: "Showing the latest " + data.prints.length + " of " + s.prints + " prints." }) : null;
    listRoot.replaceChildren(
      summarySentence(s, () => { filter = "review"; renderList(); }),
      h("section", { class: "panel", "aria-label": "Prints" },
        h("div", { class: "panel-head" }, h("h2", { text: "Prints" }), h("div", { class: "aside" }, seg)),
        items.length ? h("ul", { class: "prints" }, items.map(printRow))
          : h("div", { class: "state" }, h("p", { text: filter === "review" ? "Nothing left to review." : "No print with alerts." })),
        more));
  }

  async function loadList() {
    listRoot.replaceChildren(loadingList());
    try {
      data = await api("/detect/api/prints?limit=" + LIST_LIMIT);
      onSummary(data.summary);
      renderList();
    } catch (err) {
      listRoot.replaceChildren(errorState(err.message, loadList));
    }
  }

  function isCurrent(print) {
    const status = getStatus();
    return Boolean(status && status.print && status.print.id === print.id && ACTIVE.includes(print.status));
  }

  async function remove(print, button) {
    const ok = await confirmDialog({
      title: "Delete this print?",
      body: print.filename + ", its chart, alerts and frames are deleted for good.",
      confirm: "Delete print", danger: true,
    });
    if (!ok) return;
    await withBusy(button, async () => {
      try {
        await api("/detect/api/prints/" + encodeURIComponent(print.id), { method: "DELETE" });
        toast("Print deleted");
        location.hash = "#history";
      } catch (err) {
        toast(err.status === 409 ? "This print is still running: it can be deleted once it ends." : "Couldn't delete: " + err.message, "halt");
      }
    });
  }

  function renderDetail(print) {
    if (detailChart) detailChart.destroy();
    const [label, tone] = PRINT_STATUS[print.status] || [print.status, "neutral"];
    const ran = isNum(print.ended) ? "ran " + fmtDuration(print.ended - print.started) : "running for " + fmtDuration(Date.now() / 1000 - print.started);
    const current = isCurrent(print);
    const del = h("button", { class: "btn btn-danger btn-sm", type: "button", disabled: current }, icon("trash"), "Delete print");
    del.addEventListener("click", () => remove(print, del));
    const chartEl = h("div", { class: "chart chart-score" });
    const decisions = print.decisions || [];
    detailRoot.replaceChildren(
      h("a", { class: "back", href: "#history" }, icon("chevronLeft"), "All prints"),
      h("section", { class: "panel detail-head" },
        h("div", { class: "detail-title-row" },
          h("h2", { class: "detail-title", text: print.filename }),
          h("span", { class: "badge plain", dataset: { tone }, text: label })),
        h("p", { class: "muted", text: "Started " + fmtWhen(print.started) + ", " + ran + ", " + plural(print.frame || 0, "frame") + " analysed." }),
        h("div", { class: "row detail-actions" }, del,
          current ? h("span", { class: "hint", text: "The running print can be deleted once it ends." }) : null)),
      h("section", { class: "panel" },
        h("div", { class: "panel-head" }, h("h2", { text: "Score" }),
          h("span", { class: "aside", text: "Final levels: warning " + fmtNum((print.levels || {}).warning) + ", pause " + fmtNum((print.levels || {}).pause) })),
        chartEl, scoreLegend()),
      h("section", { class: "panel" },
        h("div", { class: "panel-head" }, h("h2", { text: decisions.length ? "Alerts" : "No alert" }),
          decisions.length ? h("span", { class: "aside", text: "Tap a snapshot to enlarge it" }) : null),
        decisions.length
          ? decisionList(print, (updated) => renderDetail(updated || print))
          : h("p", { class: "panel-note", text: "The score stayed below the warning level for the whole print." })),
      (print.timeline || []).length
        ? h("section", { class: "panel" }, h("div", { class: "panel-head" }, h("h2", { text: "Timeline" }),
          h("span", { class: "aside", text: "A frame every 10 minutes and at the end" })), timelineStrip(print))
        : null);
    detailChart = createChart(chartEl, scoreChartOptions(print));
  }

  async function loadDetail(id) {
    detailRoot.replaceChildren(h("a", { class: "back", href: "#history" }, icon("chevronLeft"), "All prints"), loadingList());
    try {
      renderDetail(await api("/detect/api/prints/" + encodeURIComponent(id)));
    } catch (err) {
      detailRoot.replaceChildren(h("a", { class: "back", href: "#history" }, icon("chevronLeft"), "All prints"),
        err.status === 404
          ? h("div", { class: "panel" }, h("div", { class: "state" }, icon("clock"), h("h2", { text: "This print isn't in the history any more" }),
            h("p", { text: "It was deleted, or dropped to keep only the latest prints." })))
          : errorState(err.message, () => loadDetail(id)));
    }
  }

  return {
    enter(id) {
      listRoot.hidden = Boolean(id);
      detailRoot.hidden = !id;
      if (id) loadDetail(id);
      else loadList();
      window.scrollTo(0, 0);
    },
  };
}
