// Failure detection page: Settings view (watching, notifications, history), saved with PUT /settings.
import { $, api, h, plural } from "/q2-assets/core.js";
import { icon } from "/q2-assets/icons.js";
import { showMsg, toast, withBusy } from "/q2-assets/ui.js";

const SENSITIVITY = [[0.8, "Low"], [1.0, "Normal"], [1.2, "High"]];
const KEEP_MIN = 1;
const KEEP_MAX = 1000;
const EXAMPLES = [
  ["ntfy", "ntfys://ntfy.sh/your-topic", "Free push notifications: subscribe to the same topic in the ntfy app."],
  ["Telegram", "tgram://bot-token/chat-id", "A bot made with BotFather, and your chat id."],
  ["Discord", "discord://webhook-id/webhook-token", "A channel webhook (channel settings, Integrations)."],
  ["Pushover", "pover://user-key@app-token", "Your user key and an application token."],
  ["Home Assistant", "hassio://homeassistant.local/access-token", "A long-lived access token; shows up as a notification in Home Assistant."],
  ["Email", "mailtos://user:app-password@gmail.com", "Most providers need an app password."],
];

const clone = (s) => JSON.parse(JSON.stringify(s));

function normalize(s) {
  const n = s.notify || {};
  return {
    enabled: Boolean(s.enabled), mode: s.mode === "pause" ? "pause" : "observe", sensitivity: Number(s.sensitivity),
    notify: { urls: (n.urls || []).map((u) => u.trim()).filter(Boolean), on_warning: Boolean(n.on_warning), on_pause: Boolean(n.on_pause), attach_image: Boolean(n.attach_image) },
    keep_prints: Number(s.keep_prints),
  };
}

function validate(draft) {
  const errors = {};
  draft.notify.urls.forEach((u, i) => {
    if (u.trim() && !/^[a-z][a-z0-9+.-]*:\/\/\S+$/i.test(u.trim())) errors["url" + i] = "This doesn't look like a notification URL (service://...).";
  });
  const keep = Number(draft.keep_prints);
  if (!Number.isInteger(keep) || keep < KEEP_MIN || keep > KEEP_MAX) errors.keep = "A whole number from " + KEEP_MIN + " to " + KEEP_MAX + ".";
  return errors;
}

export function createSettingsView({ onSaved }) {
  const root = $("#settingsRoot");
  let saved = null;
  let draft = null;
  let el = {};

  const isDirty = () => saved && JSON.stringify(normalize(draft)) !== JSON.stringify(normalize(saved));
  const update = (changes) => { draft = { ...draft, ...changes }; refreshBar(); };
  const updateNotify = (changes) => update({ notify: { ...draft.notify, ...changes } });

  window.addEventListener("beforeunload", (ev) => {
    if (isDirty()) { ev.preventDefault(); ev.returnValue = ""; }
  });

  function refreshBar() {
    const dirty = isDirty();
    el.bar.dataset.dirty = String(dirty);
    el.save.disabled = !dirty;
    el.discard.hidden = !dirty;
    showMsg(el.barMsg, dirty ? "Unsaved changes" : "All changes saved", dirty ? null : "clear");
    el.test.disabled = !normalize(draft).notify.urls.length;
  }

  // ---------- Sections ----------
  function watchingSection() {
    const enabled = h("input", { type: "checkbox", role: "switch", checked: draft.enabled, id: "setEnabled" });
    enabled.addEventListener("change", () => update({ enabled: enabled.checked }));
    const modes = [
      ["observe", "Observe", "Notify only. The print is never paused; alerts say when it would have been."],
      ["pause", "Pause", "Pause the print when the score passes the pause level, and notify."],
    ].map(([value, title, text]) => {
      const input = h("input", { type: "radio", name: "mode", value, checked: draft.mode === value });
      input.addEventListener("change", () => update({ mode: value }));
      return h("label", { class: "choice" }, input, h("strong", { text: title }), h("span", { text: text }));
    });
    const known = SENSITIVITY.some(([v]) => v === Number(draft.sensitivity));
    const options = known ? SENSITIVITY : [...SENSITIVITY, [Number(draft.sensitivity), "Custom ×" + draft.sensitivity]];
    const seg = h("div", { class: "seg", role: "radiogroup", "aria-labelledby": "sensLabel" }, options.map(([value, label]) => {
      const input = h("input", { type: "radio", name: "sensitivity", value: String(value), checked: Number(draft.sensitivity) === value });
      input.addEventListener("change", () => update({ sensitivity: value }));
      return h("label", {}, input, label);
    }));
    return h("section", { class: "panel settings-section", "aria-labelledby": "secWatch" },
      h("div", { class: "settings-intro" }, h("h2", { id: "secWatch", text: "Watching" }),
        h("p", { class: "panel-note", text: "While a print runs, a camera frame is analysed every 10 seconds." })),
      h("div", { class: "settings-body" },
        h("label", { class: "switch" }, enabled, h("span", { class: "switch-track" }),
          h("span", {}, h("strong", { text: "Watch prints" }), h("small", { class: "hint switch-hint", text: "Off: nothing is analysed and no print is paused." }))),
        h("fieldset", { class: "group" }, h("legend", { class: "field-label", text: "When a failure is likely" }), h("div", { class: "choices" }, modes)),
        h("div", { class: "group" }, h("span", { class: "field-label", id: "sensLabel", text: "Sensitivity" }), seg,
          h("p", { class: "hint", text: "Multiplies the score. High reacts sooner but may alert on harmless things like a hand or a purge blob; Low waits for clearer failures." }))));
  }

  function urlRow(value, index, errors) {
    const id = "url" + index;
    const input = h("input", {
      class: "input", type: "text", inputmode: "url", autocomplete: "off", spellcheck: "false", autocapitalize: "off",
      value, id, placeholder: "service://...", "aria-label": "Notification URL " + (index + 1),
      "aria-invalid": errors[id] ? "true" : null, "aria-describedby": errors[id] ? id + "-err" : null,
    });
    input.addEventListener("input", () => {
      updateNotify({ urls: draft.notify.urls.map((u, i) => (i === index ? input.value : u)) });
    });
    const remove = h("button", { class: "icon-btn", type: "button", "aria-label": "Remove URL " + (index + 1) }, icon("trash"));
    remove.addEventListener("click", () => {
      updateNotify({ urls: draft.notify.urls.filter((_, i) => i !== index) });
      renderUrls();
    });
    return h("li", {}, h("div", { class: "url-row" }, input, remove),
      errors[id] ? h("p", { class: "field-error", id: id + "-err", text: errors[id] }) : null);
  }

  function renderUrls(errors = {}, focusLast = false) {
    const urls = draft.notify.urls;
    el.urls.replaceChildren(...urls.map((u, i) => urlRow(u, i, errors)));
    el.urlsEmpty.hidden = urls.length > 0;
    if (focusLast && urls.length) el.urls.querySelector("li:last-child input").focus();
  }

  function addUrl(value = "") {
    updateNotify({ urls: [...draft.notify.urls, value] });
    renderUrls({}, true);
  }

  function notifySection() {
    el.urls = h("ul", { class: "urls", "aria-label": "Notification URLs" });
    el.urlsEmpty = h("p", { class: "panel-note", text: "No notification set up: alerts only show on this page." });
    const add = h("button", { class: "btn btn-sm", type: "button" }, icon("plus"), "Add a URL");
    add.addEventListener("click", () => addUrl());
    const examples = h("details", { class: "examples" }, h("summary", { text: "URL examples" }),
      h("ul", {}, EXAMPLES.map(([name, url, note]) => {
        const use = h("button", { class: "btn btn-ghost btn-sm", type: "button", "aria-label": "Add a " + name + " URL" }, "Use");
        use.addEventListener("click", () => addUrl(url));
        return h("li", {}, h("div", {}, h("strong", { text: name }), h("code", { text: url }), h("small", { class: "hint", text: note })), use);
      })),
      h("p", { class: "hint" }, "Same format as Moonraker's notifier. ",
        h("a", { href: "https://github.com/caronc/apprise/wiki", target: "_blank", rel: "noopener" }, "Every supported service")));
    const check = (key, title, text) => {
      const input = h("input", { type: "checkbox", checked: draft.notify[key] });
      input.addEventListener("change", () => updateNotify({ [key]: input.checked }));
      return h("label", { class: "check" }, input, h("span", {}, title, h("small", { text })));
    };
    el.test = h("button", { class: "btn", type: "button" }, icon("send"), "Send a test notification");
    el.testMsg = h("p", { class: "msg", role: "status" });
    el.test.addEventListener("click", sendTest);
    return h("section", { class: "panel settings-section", "aria-labelledby": "secNotify" },
      h("div", { class: "settings-intro" }, h("h2", { id: "secNotify", text: "Notifications" }),
        h("p", { class: "panel-note", text: "Sent with Apprise to your phone, chat or home automation. One URL per service." })),
      h("div", { class: "settings-body" },
        h("div", { class: "group" }, el.urls, el.urlsEmpty, h("div", { class: "row" }, add), examples),
        h("div", { class: "group" },
          check("on_warning", "On a warning", "The score passed the warning level."),
          check("on_pause", "On a pause", "The print was paused, or would have been in Observe mode."),
          check("attach_image", "Attach the camera frame", "With the boxes the detector drew.")),
        h("div", { class: "group" }, h("div", { class: "row" }, el.test), el.testMsg)));
  }

  function historySection() {
    el.keep = h("input", { type: "number", min: KEEP_MIN, max: KEEP_MAX, step: 1, value: draft.keep_prints, id: "setKeep", inputmode: "numeric" });
    el.keep.addEventListener("input", () => update({ keep_prints: el.keep.value === "" ? "" : Number(el.keep.value) }));
    el.keepErr = h("p", { class: "field-error", id: "keepErr", hidden: true });
    return h("section", { class: "panel settings-section", "aria-labelledby": "secHistory" },
      h("div", { class: "settings-intro" }, h("h2", { id: "secHistory", text: "History" }),
        h("p", { class: "panel-note", text: "Prints are kept with their chart, alerts and frames." })),
      h("div", { class: "settings-body" },
        h("div", { class: "field keep-field" }, h("label", { for: "setKeep", class: "field-label", text: "Prints to keep" }),
          h("div", { class: "with-unit" }, el.keep, h("i", { text: "prints" })), el.keepErr,
          h("small", { class: "hint", text: "Older prints and their frames are deleted." }))));
  }

  function saveBar() {
    el.save = h("button", { class: "btn btn-primary", type: "submit" }, "Save settings");
    el.discard = h("button", { class: "btn btn-ghost", type: "button" }, "Discard");
    el.barMsg = h("p", { class: "msg", role: "status" });
    el.discard.addEventListener("click", () => { draft = clone(saved); render(); });
    el.bar = h("div", { class: "save-bar" }, el.barMsg, h("div", { class: "row" }, el.discard, el.save));
    return el.bar;
  }

  function render() {
    const form = h("form", { class: "settings", novalidate: true }, watchingSection(), notifySection(), historySection(), saveBar());
    form.addEventListener("submit", (ev) => { ev.preventDefault(); save(); });
    root.replaceChildren(form);
    renderUrls();
    refreshBar();
  }

  // ---------- Save, test ----------
  function showErrors(errors) {
    renderUrls(errors);
    el.keep.setAttribute("aria-invalid", errors.keep ? "true" : "false");
    el.keepErr.hidden = !errors.keep;
    el.keepErr.textContent = errors.keep || "";
    if (errors.keep) el.keep.setAttribute("aria-describedby", "keepErr"); else el.keep.removeAttribute("aria-describedby");
  }

  async function save() {
    const errors = validate(draft);
    showErrors(errors);
    if (Object.keys(errors).length) {
      showMsg(el.barMsg, "Fix the highlighted fields first", "halt");
      const first = root.querySelector('[aria-invalid="true"]');
      if (first) first.focus();
      return false;
    }
    return withBusy(el.save, async () => {
      try {
        const result = await api("/detect/api/settings", { method: "PUT", body: normalize(draft) });
        saved = clone(result);
        draft = clone(result);
        render();
        toast("Settings saved");
        onSaved(result);
        return true;
      } catch (err) {
        showMsg(el.barMsg, "Not saved: " + err.message, "halt");
        return false;
      } finally {
        refreshBar();
      }
    }).catch(() => false);
  }

  // Tests the URLs as typed, saved or not (the service leaves the settings unchanged)
  async function sendTest() {
    const urlErrors = Object.fromEntries(Object.entries(validate(draft)).filter(([key]) => key.startsWith("url")));
    renderUrls(urlErrors);
    if (Object.keys(urlErrors).length) {
      showMsg(el.testMsg, "Fix the highlighted URL first", "halt");
      return;
    }
    const urls = normalize(draft).notify.urls;
    const unsaved = isDirty() ? " These URLs aren't saved yet." : "";
    showMsg(el.testMsg, "Sending…");
    await withBusy(el.test, async () => {
      try {
        const result = await api("/detect/api/notify/test", { method: "POST", body: { urls }, timeout: 30000 });
        if (result && result.ok) showMsg(el.testMsg, "Sent to " + plural(urls.length, "service") + ". Check that it arrived." + unsaved, "clear");
        else showMsg(el.testMsg, "Not sent: " + ((result && result.error) || "unknown error"), "halt");
      } catch (err) {
        showMsg(el.testMsg, "Not sent: " + err.message, "halt");
      }
    });
    refreshBar();
  }

  async function load() {
    root.replaceChildren(h("div", { class: "panel", "aria-busy": "true" }, h("div", { class: "state" }, h("p", { text: "Loading settings…" }))));
    try {
      saved = clone(await api("/detect/api/settings"));
      draft = clone(saved);
      render();
    } catch (err) {
      const retry = h("button", { class: "btn", type: "button" }, icon("refresh"), "Try again");
      retry.addEventListener("click", load);
      root.replaceChildren(h("div", { class: "panel" }, h("div", { class: "state", dataset: { tone: "halt" } }, icon("plug"),
        h("h2", { text: "Couldn't load the settings" }), h("p", { text: err.message }), h("div", { class: "row" }, retry))));
    }
  }

  return {
    enter() { if (!saved || !isDirty()) load(); },
  };
}
