// Failure detection page: entry point. Routes (#live, #history, #history/<id>, #settings),
// live status over Server-Sent Events (polling /status every 10 s when SSE fails).
import { $, $$, api, h, liveFeed, setText } from "/q2-assets/core.js";
import { hydrateIcons } from "/q2-assets/icons.js";
import { initTheme } from "/q2-assets/ui.js";
import { createLiveView } from "./live.js";
import { createHistoryView } from "./history.js";
import { createSettingsView } from "./settings.js";

const POLL_MS = 10000;
const TICK_MS = 1000;
const CONN = {
  connecting: ["neutral", "Connecting…"],
  live: ["clear", "Live"],
  reconnecting: ["caution", "Reconnecting…"],
  polling: ["caution", "Updates every 10 s"],
  offline: ["halt", "Service unreachable"],
};

hydrateIcons();
initTheme($("#themeBtn"));

let status = null;
let feed = null;
let decisionsSeen = null;

function applyStatus(next) {
  status = next;
  live.render(status);
  setText($("#version"), "q2-offload failure detection " + (status.version || ""));
  // A new alert (or a review) changes the number to review in the History tab
  const p = status.print;
  const key = p ? p.id + ":" + (p.decisions || []).map((d) => d.label).join(",") + ":" + (p.decisions || []).length : "";
  if (decisionsSeen !== null && key !== decisionsSeen) refreshReviewCount();
  decisionsSeen = key;
}

function setConn(mode, err) {
  const [tone, text] = CONN[mode] || CONN.connecting;
  $("#conn").dataset.tone = tone;
  setText($("#connText"), text);
  $("#conn").title = err ? text + ": " + err.message : text;
  if (mode === "offline") live.unreachable(err, Boolean(status));
}

async function refreshReviewCount(summary) {
  let s = summary;
  if (!s) {
    try { s = (await api("/detect/api/prints?limit=1")).summary; } catch { return; }
  }
  const badge = $("#reviewCount");
  const n = (s && s.unreviewed) || 0;
  badge.hidden = !n;
  badge.replaceChildren(n ? String(n) : "", n ? h("span", { class: "visually-hidden", text: " to review" }) : "");
}

const live = createLiveView({
  applyStatus,
  retry: () => feed.refresh(),
});
const history = createHistoryView({ getStatus: () => status, onSummary: refreshReviewCount });
const settings = createSettingsView({
  onSaved: (saved) => { if (status) applyStatus({ ...status, settings: saved }); },
});

function route() {
  const [name, id] = (location.hash.replace(/^#/, "") || "live").split("/");
  const view = ["live", "history", "settings"].includes(name) ? name : "live";
  $$(".view").forEach((v) => { v.hidden = v.id !== "view-" + view; });
  $$(".tabs a").forEach((a) => {
    if (a.dataset.route === view) a.setAttribute("aria-current", "page");
    else a.removeAttribute("aria-current");
  });
  if (view !== "live") live.leave();
  if (view === "history") history.enter(id ? decodeURIComponent(id) : null);
  if (view === "settings") settings.enter();
  document.title = (view === "live" ? "" : view[0].toUpperCase() + view.slice(1) + " – ") + "Failure detection";
}

window.addEventListener("hashchange", route);
window.addEventListener("q2:reviewed", () => refreshReviewCount());
route();

feed = liveFeed({
  url: "/detect/api/events",
  event: "status",
  pollUrl: "/detect/api/status",
  pollMs: POLL_MS,
  onData: applyStatus,
  onMode: setConn,
});
refreshReviewCount();
setInterval(() => live.tick(), TICK_MS);
