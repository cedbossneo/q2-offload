// q2-offload pages: DOM, HTTP, live updates and formatting helpers (vanilla ES module).

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

// h("button", { class: "btn", onClick: fn, "aria-label": "Close" }, "text", childNode)
// Strings become text nodes: never markup. `html` is for trusted constants (icons) only.
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(props || {})) {
    if (value == null || value === false) continue;
    if (key === "class") el.className = value;
    else if (key === "text") el.textContent = value;
    else if (key === "html") el.innerHTML = value;
    else if (key === "style" && typeof value === "object") {
      for (const [prop, v] of Object.entries(value)) {
        if (prop.startsWith("--")) el.style.setProperty(prop, v);
        else el.style[prop] = v;
      }
    }
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === "value" || key === "checked") el[key] = value;
    else el.setAttribute(key, value === true ? "" : String(value));
  }
  for (const child of children.flat(Infinity)) {
    if (child == null || child === false) continue;
    el.append(child instanceof Node ? child : String(child));
  }
  return el;
}

export function setText(el, text) {
  const value = text == null ? "" : String(text);
  if (el && el.textContent !== value) el.textContent = value;
}

// ---------- HTTP ----------

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

const DEFAULT_TIMEOUT_MS = 12000;

function errorMessage(data, res) {
  if (data && typeof data.error === "string") return data.error;
  if (data && data.error && data.error.message) return data.error.message; // Moonraker
  return res.status + " " + (res.statusText || "error");
}

// JSON request. Throws ApiError with a readable message (network, timeout, HTTP status, body.error).
export async function api(path, { method = "GET", body, timeout = DEFAULT_TIMEOUT_MS } = {}) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeout);
  const init = { method, cache: "no-store", signal: controller.signal, headers: { Accept: "application/json" } };
  if (body !== undefined) {
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  let res;
  try {
    res = await fetch(path, init);
  } catch (err) {
    const message = err.name === "AbortError" ? "no answer after " + timeout / 1000 + " s" : "the host does not answer";
    throw new ApiError(message, 0, null);
  } finally {
    clearTimeout(timer);
  }
  const text = await res.text().catch(() => "");
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch { data = null; }
  }
  if (!res.ok) throw new ApiError(errorMessage(data, res), res.status, data);
  return data;
}

// ---------- Live updates: Server-Sent Events, polling fallback ----------
// onMode(mode, error): "connecting" | "live" (SSE) | "reconnecting" | "polling" | "offline"
export function liveFeed({ url, event = "message", pollUrl, pollMs = 10000, retrySseMs = 60000, onData, onMode }) {
  let source = null;
  let pollTimer = null;
  let retryTimer = null;
  let errors = 0;
  let stopped = false;
  const mode = (name, err) => onMode && onMode(name, err || null);

  function deliver(data) {
    if (!stopped) onData(data);
  }

  let offline = false;

  async function pollOnce() {
    try {
      const data = await api(pollUrl);
      if (pollTimer) mode("polling");
      deliver(data);
      // Back after an outage: try the live stream again now rather than at the next retry
      if (offline && !source) startSse();
      offline = false;
    } catch (err) {
      offline = true;
      mode("offline", err);
    }
  }

  function startPolling() {
    if (pollTimer || stopped) return;
    pollTimer = setInterval(pollOnce, pollMs);
    pollOnce();
  }

  function stopPolling() {
    clearInterval(pollTimer);
    pollTimer = null;
  }

  function closeSource() {
    if (source) source.close();
    source = null;
  }

  function startSse() {
    clearTimeout(retryTimer);
    if (stopped) return;
    if (typeof EventSource === "undefined") return startPolling();
    errors = 0;
    source = new EventSource(url);
    source.addEventListener(event, (ev) => {
      let data;
      try { data = JSON.parse(ev.data); } catch { return; }
      errors = 0;
      stopPolling();
      mode("live");
      deliver(data);
    });
    source.addEventListener("error", () => {
      errors += 1;
      // CLOSED: the server refused the stream (proxy error, not SSE). Two errors in a row: give up for now.
      if (source && (source.readyState === EventSource.CLOSED || errors >= 2)) {
        closeSource();
        startPolling();
        retryTimer = setTimeout(startSse, retrySseMs);
      } else {
        mode("reconnecting");
      }
    });
  }

  mode("connecting");
  startSse();

  return {
    // Fetch once now (the user pressing Retry); errors go to the caller and to onMode
    async refresh() {
      try {
        deliver(await api(pollUrl));
        if (!source || source.readyState !== EventSource.OPEN) {
          mode("polling");
          startPolling();
        }
      } catch (err) {
        if (!source || source.readyState !== EventSource.OPEN) mode("offline", err);
        throw err;
      }
    },
    reconnect() { closeSource(); stopPolling(); startSse(); },
    stop() { stopped = true; closeSource(); stopPolling(); clearTimeout(retryTimer); },
  };
}

// ---------- Formatting ----------

export const isNum = (v) => typeof v === "number" && Number.isFinite(v);

export function fmtNum(value, digits = 2) {
  return isNum(value) ? value.toFixed(digits) : "–";
}

export function fmtPct(fraction, digits = 0) {
  return isNum(fraction) ? (fraction * 100).toFixed(digits) + " %" : "–";
}

// 45 s, 12 min, 1 h 02, 3 d 4 h
export function fmtDuration(seconds) {
  if (!isNum(seconds)) return "–";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return s + " s";
  const m = Math.round(s / 60);
  if (m < 60) return m + " min";
  const hours = Math.floor(m / 60);
  if (hours < 48) return hours + " h " + String(m % 60).padStart(2, "0");
  return Math.floor(hours / 24) + " d " + (hours % 24) + " h";
}

// English day and month names (the pages are in English), 12 or 24 h clock as the device prefers
const hourCycle = new Intl.DateTimeFormat(undefined, { hour: "numeric" }).resolvedOptions().hourCycle;
const hour12 = hourCycle === "h12" || hourCycle === "h11";
const timeFormat = new Intl.DateTimeFormat("en-GB", { hour: "2-digit", minute: "2-digit", hour12 });
const dayFormat = new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short" });

export function fmtClock(unixSeconds) {
  return isNum(unixSeconds) ? timeFormat.format(new Date(unixSeconds * 1000)) : "–";
}

function dayKey(date) {
  return date.getFullYear() + "-" + date.getMonth() + "-" + date.getDate();
}

// "Today, 14:32", "Yesterday, 09:10", "Sat 31 Oct, 14:32"
export function fmtWhen(unixSeconds) {
  if (!isNum(unixSeconds)) return "–";
  const date = new Date(unixSeconds * 1000);
  const today = new Date();
  const yesterday = new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1);
  const time = timeFormat.format(date);
  if (dayKey(date) === dayKey(today)) return "Today, " + time;
  if (dayKey(date) === dayKey(yesterday)) return "Yesterday, " + time;
  return dayFormat.format(date) + ", " + time;
}

export function fmtAgo(unixSeconds, now = Date.now() / 1000) {
  if (!isNum(unixSeconds)) return "–";
  const s = Math.max(0, now - unixSeconds);
  if (s < 5) return "just now";
  if (s < 60) return Math.round(s) + " s ago";
  if (s < 3600) return Math.round(s / 60) + " min ago";
  if (s < 86400 * 2) return fmtDuration(s) + " ago";
  return Math.round(s / 86400) + " days ago";
}

export function plural(count, one, many = one + "s") {
  return count + " " + (count === 1 ? one : many);
}
