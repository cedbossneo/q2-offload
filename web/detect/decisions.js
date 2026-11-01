// Failure detection page: a print's alerts, with their snapshot and the user's review.
import { api, fmtClock, fmtDuration, fmtNum, h } from "/q2-assets/core.js";
import { toast } from "/q2-assets/ui.js";
import { decisionLevels, fmtScore, KIND_LABEL, KIND_TONE } from "./verdict.js";
import { describeBoxes, openLightbox, printFileUrl as snapshotUrl, shot } from "./frame.js";

const LABELS = [
  ["false_alarm", "False alarm"],
  ["real_failure", "Real failure"],
];

// Compared with the levels in force at that moment (they move a little during a print)
function why(decision, print) {
  const levels = decisionLevels(decision, print);
  const level = decision.kind === "warning" ? ["warning", levels.warning] : ["pause", levels.pause];
  return "Score " + fmtScore(decision.score) + ", the " + level[0] + " level was " + fmtNum(level[1]) + ". " +
    (decision.kind === "pause" ? "The print was paused." : decision.kind === "would-pause" ? "Observe mode: the print kept going." : "A warning was sent.");
}

async function sendLabel(print, decision, label, onChange) {
  try {
    const updated = await api("/detect/api/prints/" + encodeURIComponent(print.id) + "/decisions/" + decision.n + "/label", {
      method: "POST", body: { label },
    });
    toast(label == null ? "Review cleared" : label === "false_alarm" ? "Marked as a false alarm" : "Marked as a real failure");
    window.dispatchEvent(new CustomEvent("q2:reviewed"));
    onChange(updated);
  } catch (err) {
    toast("Couldn't save the review: " + err.message, "halt");
    onChange(null);
  }
}

function reviewGroup(print, decision, onChange) {
  const buttons = LABELS.map(([value, text]) => {
    const pressed = decision.label === value;
    const button = h("button", {
      type: "button", class: "btn btn-sm review-btn", "aria-pressed": String(pressed), dataset: { value },
    }, text);
    button.addEventListener("click", () => {
      buttons.forEach((b) => { b.disabled = true; });
      button.setAttribute("aria-busy", "true");
      sendLabel(print, decision, pressed ? null : value, onChange);
    });
    return button;
  });
  return h("div", { class: "review", role: "group", "aria-label": "Your review of this alert" },
    h("span", { class: "review-q", text: decision.label ? "Your review" : "Was it a failure?" }), ...buttons);
}

// onChange(updatedPrint | null): called after a review was saved (or failed, with null)
export function decisionList(print, onChange) {
  const items = (print.decisions || []).slice().reverse().map((d) => {
    const tone = KIND_TONE[d.kind] || "caution";
    const when = fmtClock(d.t) + ", " + fmtDuration(d.t - print.started) + " into the print";
    const media = d.snapshot
      ? h("button", { type: "button", class: "decision-shot", "aria-label": "Enlarge the snapshot of this alert" },
        shot(snapshotUrl(print.id, d.snapshot), d.detections, "Camera frame when the alert was raised"))
      : h("div", { class: "decision-shot none" }, "No snapshot");
    if (d.snapshot) {
      media.addEventListener("click", () => openLightbox({
        src: snapshotUrl(print.id, d.snapshot), detections: d.detections,
        title: KIND_LABEL[d.kind] + " at " + fmtClock(d.t),
        caption: why(d, print) + " " + (d.detections ? "Boxes: " + describeBoxes(d.detections) + "." : ""),
      }));
    }
    return h("li", { class: "decision", dataset: { tone } },
      media,
      h("div", { class: "decision-body" },
        h("p", { class: "decision-head" },
          h("span", { class: "badge", dataset: { tone }, text: KIND_LABEL[d.kind] || d.kind }),
          h("span", { class: "muted", text: when })),
        h("p", { class: "decision-why", text: why(d, print) }),
        reviewGroup(print, d, onChange)));
  });
  return h("ol", { class: "decisions" }, items);
}
