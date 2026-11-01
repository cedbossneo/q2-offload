// q2-offload pages: theme toggle, toasts, confirmation dialog, busy buttons.
import { h } from "./core.js";
import { icon, iconSvg } from "./icons.js";

// ---------- Theme ----------
// Stored per browser (shared by every q2 page): "light", "dark" or absent (follow the device)
const THEME_KEY = "q2-theme";
const THEMES = ["auto", "light", "dark"];
const THEME_LABEL = { auto: "Theme: same as the device", light: "Theme: light", dark: "Theme: dark" };
const THEME_ICON = { auto: "auto", light: "sun", dark: "moon" };

function readTheme() {
  try {
    const value = localStorage.getItem(THEME_KEY);
    return value === "light" || value === "dark" ? value : "auto";
  } catch {
    return "auto";
  }
}

function applyTheme(theme) {
  if (theme === "auto") delete document.documentElement.dataset.theme;
  else document.documentElement.dataset.theme = theme;
  try {
    if (theme === "auto") localStorage.removeItem(THEME_KEY);
    else localStorage.setItem(THEME_KEY, theme);
  } catch { /* private window: the choice lasts for this page only */ }
  window.dispatchEvent(new CustomEvent("q2:theme"));
}

export function initTheme(button) {
  let theme = readTheme();
  applyTheme(theme);
  const paint = () => {
    button.innerHTML = iconSvg(THEME_ICON[theme]);
    button.setAttribute("aria-label", THEME_LABEL[theme] + ". Change theme");
    button.title = THEME_LABEL[theme];
  };
  paint();
  button.addEventListener("click", () => {
    theme = THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
    applyTheme(theme);
    paint();
  });
  const media = window.matchMedia("(prefers-color-scheme: light)");
  media.addEventListener("change", () => window.dispatchEvent(new CustomEvent("q2:theme")));
}

// ---------- Toasts ----------
const TOAST_MS = 4500;
const TOAST_ICON = { clear: "check", halt: "alert", caution: "alert", accent: "info" };

function toastRegion() {
  let region = document.querySelector(".toasts");
  if (!region) {
    region = h("div", { class: "toasts", role: "status", "aria-live": "polite" });
    document.body.append(region);
  }
  return region;
}

export function toast(message, tone = "clear") {
  const el = h("div", { class: "toast", dataset: { tone } }, icon(TOAST_ICON[tone] || "info"), h("p", { text: message }));
  toastRegion().append(el);
  const remove = () => {
    el.classList.add("leaving");
    setTimeout(() => el.remove(), 220);
  };
  setTimeout(remove, tone === "halt" ? TOAST_MS * 1.6 : TOAST_MS);
  el.addEventListener("click", remove);
}

// ---------- Confirmation dialog ----------
// Resolves true when confirmed. Esc, Cancel and the backdrop resolve false.
export function confirmDialog({ title, body, confirm = "Confirm", danger = false }) {
  return new Promise((resolve) => {
    const ok = h("button", { class: "btn " + (danger ? "btn-danger" : "btn-primary"), type: "button", text: confirm });
    const cancel = h("button", { class: "btn", type: "button", text: "Cancel" });
    const titleId = "dlg-" + Math.random().toString(36).slice(2);
    const dialog = h("dialog", { class: "q2-dialog", "aria-labelledby": titleId },
      h("div", { class: "dialog-body" }, h("h2", { id: titleId, text: title }), body ? h("p", { text: body }) : null),
      h("div", { class: "dialog-actions" }, cancel, ok));
    let result = false;
    ok.addEventListener("click", () => { result = true; dialog.close(); });
    cancel.addEventListener("click", () => dialog.close());
    dialog.addEventListener("click", (ev) => { if (ev.target === dialog) dialog.close(); });
    dialog.addEventListener("close", () => { dialog.remove(); resolve(result); });
    document.body.append(dialog);
    dialog.showModal();
    cancel.focus();
  });
}

// ---------- Busy buttons ----------
// Runs task with the button disabled and a spinner; returns the task's result or rethrows.
export async function withBusy(button, task) {
  button.disabled = true;
  button.setAttribute("aria-busy", "true");
  try {
    return await task();
  } finally {
    button.removeAttribute("aria-busy");
    button.disabled = false;
  }
}

// Status line next to an action: tone "clear" (done), "halt" (failed) or none (in progress)
export function showMsg(el, text, tone) {
  el.textContent = text || "";
  if (tone) el.dataset.tone = tone;
  else delete el.dataset.tone;
}
