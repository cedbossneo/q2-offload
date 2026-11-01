// Failure detection page: camera frames with Obico's boxes drawn over them, and a lightbox.
import { fmtClock, fmtDuration, h } from "/q2-assets/core.js";
import { icon } from "/q2-assets/icons.js";

const STRONG = 0.5;          // boxes at or above this confidence are drawn in the alarm colour
const LABEL_ROOM = 0.07;     // a box closer than this to the top gets its label inside

// A kept JPEG of a print (tNNN.jpg timeline frame, dNNN.jpg decision snapshot)
export const printFileUrl = (printId, file) =>
  "/detect/api/prints/" + encodeURIComponent(printId) + "/" + encodeURIComponent(file);

const LABEL_PX = { w: 50, h: 22 };   // room a confidence label takes on screen

// detections: [[confidence, x_center, y_center, width, height], ...] in fractions of the frame.
// Strongest first; a label that would cover a stronger box's label is left out.
export function renderBoxes(layer, detections) {
  const rect = layer.getBoundingClientRect();
  const minDx = rect.width ? LABEL_PX.w / rect.width : 0.1;
  const minDy = rect.height ? LABEL_PX.h / rect.height : 0.07;
  const labelled = [];
  const sorted = (detections || []).slice().sort((a, b) => b[0] - a[0]);
  const boxes = sorted.map(([conf, xc, yc, w, hgt]) => {
    const top = Math.max(0, yc - hgt / 2);
    const left = Math.max(0, xc - w / 2);
    const clash = labelled.some(([x, y]) => Math.abs(x - left) < minDx && Math.abs(y - top) < minDy);
    if (!clash) labelled.push([left, top]);
    return h("span", {
      class: "box" + (conf >= STRONG ? " strong" : "") + (top < LABEL_ROOM ? " label-in" : ""),
      style: {
        left: left * 100 + "%", top: top * 100 + "%",
        width: Math.min(w, 1 - left) * 100 + "%", height: Math.min(hgt, 1 - top) * 100 + "%",
      },
    }, clash ? null : h("span", { class: "box-label", text: Math.round(conf * 100) + " %" }));
  });
  layer.replaceChildren(...boxes.reverse());
}

export function describeBoxes(detections) {
  const list = detections || [];
  if (!list.length) return "nothing detected";
  const best = Math.max(...list.map((d) => d[0]));
  return list.length + (list.length === 1 ? " box" : " boxes") + ", up to " + Math.round(best * 100) + " % sure";
}

// <div class="shot"><img><div class="boxes"></div></div>, sized by the image's own aspect ratio
export function shot(src, detections, alt) {
  const layer = h("div", { class: "boxes", "aria-hidden": "true" });
  const img = h("img", { src, alt: alt || "", loading: "lazy", decoding: "async" });
  const el = h("div", { class: "shot" }, img, layer);
  img.addEventListener("load", () => {
    el.style.aspectRatio = img.naturalWidth + " / " + img.naturalHeight;
    renderBoxes(layer, detections);
  });
  img.addEventListener("error", () => {
    el.classList.add("missing");
    el.append(h("span", { class: "shot-missing" }, icon("cameraOff"), "Image not kept"));
  });
  return el;
}

let lightbox = null;

function ensureLightbox() {
  if (lightbox) return lightbox;
  const close = h("button", { class: "icon-btn lightbox-close", type: "button", "aria-label": "Close" }, icon("x"));
  const title = h("h2", { id: "lightbox-title" });
  const caption = h("p", { class: "muted" });
  const holder = h("div", { class: "lightbox-shot" });
  const dialog = h("dialog", { class: "q2-dialog lightbox", "aria-labelledby": "lightbox-title" },
    h("div", { class: "lightbox-head" }, h("div", {}, title, caption), close), holder);
  close.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (ev) => { if (ev.target === dialog) dialog.close(); });
  document.body.append(dialog);
  lightbox = { dialog, title, caption, holder };
  return lightbox;
}

export function openLightbox({ src, detections, title, caption, alt }) {
  const box = ensureLightbox();
  box.title.textContent = title || "Camera frame";
  box.caption.textContent = caption || "";
  const figure = shot(src, detections, alt || title);
  figure.querySelector("img").loading = "eager";
  box.holder.replaceChildren(figure);
  box.dialog.showModal();
}

// Frames kept every 10 minutes and at the end, as a horizontal strip
export function timelineStrip(print) {
  const items = (print.timeline || []).map((frame) => {
    const label = fmtClock(frame.t);
    const offset = fmtDuration(frame.t - print.started);
    const button = h("button", { type: "button", class: "timeline-item", "aria-label": "Frame at " + label + ", " + offset + " into the print" },
      shot(printFileUrl(print.id, frame.file), null, ""),
      h("span", { class: "timeline-time" }, h("b", { text: label }), " " + offset));
    button.addEventListener("click", () => openLightbox({
      src: printFileUrl(print.id, frame.file), title: "Frame at " + label, caption: offset + " into the print",
    }));
    return h("li", {}, button);
  });
  return h("ol", { class: "timeline" }, items);
}
