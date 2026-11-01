// q2-offload pages: inline SVG icons (24x24, stroke = currentColor). Trusted constant markup.

const PATHS = {
  viewfinder: '<path d="M4 8V5.5A1.5 1.5 0 0 1 5.5 4H8M16 4h2.5A1.5 1.5 0 0 1 20 5.5V8M20 16v2.5a1.5 1.5 0 0 1-1.5 1.5H16M8 20H5.5A1.5 1.5 0 0 1 4 18.5V16"/><circle cx="12" cy="12" r="3.2"/>',
  droplet: '<path d="M12 3.2c-3.6 4.6-5.6 7.7-5.6 10.6a5.6 5.6 0 0 0 11.2 0c0-2.9-2-6-5.6-10.6Z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6 6 6M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5Z"/>',
  auto: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17a8.5 8.5 0 0 0 0-17Z" fill="currentColor" stroke="none"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  x: '<path d="M6 6l12 12M18 6 6 18"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  bell: '<path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15Z"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0"/>',
  bellOff: '<path d="M8.2 6.3A6 6 0 0 1 18 11v4M6 11v5.5l-1.5 2H17"/><path d="M10 20.5a2.2 2.2 0 0 0 4 0M3.5 3.5l17 17"/>',
  play: '<path d="M8 5.2v13.6L18.6 12Z"/>',
  pause: '<rect x="6.5" y="5" width="3.6" height="14" rx="1"/><rect x="13.9" y="5" width="3.6" height="14" rx="1"/>',
  camera: '<path d="M4 8.5A1.5 1.5 0 0 1 5.5 7h2.2L9.2 5h5.6l1.5 2h2.2A1.5 1.5 0 0 1 20 8.5v9a1.5 1.5 0 0 1-1.5 1.5h-13A1.5 1.5 0 0 1 4 17.5Z"/><circle cx="12" cy="13" r="3.4"/>',
  cameraOff: '<path d="M9.2 5h5.6l1.5 2h2.2A1.5 1.5 0 0 1 20 8.5v8M16.5 19h-11A1.5 1.5 0 0 1 4 17.5v-9A1.5 1.5 0 0 1 5.5 7h1"/><path d="M10 10.6a3.4 3.4 0 0 0 4.4 4.9M3.5 3.5l17 17"/>',
  trash: '<path d="M4.5 7h15M9.5 7V4.8h5V7M6.5 7l.8 12.2A1.5 1.5 0 0 0 8.8 20.6h6.4a1.5 1.5 0 0 0 1.5-1.4L17.5 7"/>',
  refresh: '<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3M19.5 4.5v4h-4"/>',
  alert: '<path d="M12 4 2.8 19.5h18.4Z"/><path d="M12 10v4.2M12 17.2v.1"/>',
  plug: '<path d="M9 3.5v4M15 3.5v4M7 7.5h10v3.5a5 5 0 0 1-10 0ZM12 16v4.5"/>',
  chip: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M10 3.5V7M14 3.5V7M10 17v3.5M14 17v3.5M3.5 10H7M3.5 14H7M17 10h3.5M17 14h3.5"/>',
  flame: '<path d="M12 21a6 6 0 0 0 6-6c0-3.5-2.6-5.4-3.4-9-2 1.2-3 3-3.1 5-1-.6-1.6-1.6-1.8-2.8C7.6 9.6 6 12 6 15a6 6 0 0 0 6 6Z"/>',
  power: '<path d="M12 3.5v8M7.2 6.6a7 7 0 1 0 9.6 0"/>',
  chevronLeft: '<path d="m14.5 5.5-6.5 6.5 6.5 6.5"/>',
  chevronRight: '<path d="m9.5 5.5 6.5 6.5-6.5 6.5"/>',
  info: '<circle cx="12" cy="12" r="8.5"/><path d="M12 11v5.5M12 7.8v.1"/>',
  send: '<path d="M20.5 3.5 10 14M20.5 3.5l-6.5 17-4-6.5-6.5-4Z"/>',
  eject: '<path d="M12 5 5 13h14Z"/><path d="M5 18h14"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  sliders: '<path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/>',
  external: '<path d="M14 4.5h5.5V10M19.5 4.5 11 13M17.5 14v4a1.5 1.5 0 0 1-1.5 1.5H6A1.5 1.5 0 0 1 4.5 18V8A1.5 1.5 0 0 1 6 6.5h4"/>',
  spool: '<circle cx="12" cy="12" r="8.5"/><circle cx="12" cy="12" r="5.5"/><circle cx="12" cy="12" r="2"/>',
  live: '<circle cx="12" cy="12" r="2.5" fill="currentColor"/><path d="M7.8 7.8a6 6 0 0 0 0 8.4M16.2 7.8a6 6 0 0 1 0 8.4M5 5a10 10 0 0 0 0 14M19 5a10 10 0 0 1 0 14"/>',
};

export function iconSvg(name, extraClass = "") {
  const body = PATHS[name];
  if (!body) throw new Error("Unknown icon: " + name);
  return '<svg class="icon ' + extraClass + '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
    'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false">' + body + "</svg>";
}

export function icon(name, extraClass = "") {
  const tpl = document.createElement("template");
  tpl.innerHTML = iconSvg(name, extraClass);
  return tpl.content.firstElementChild;
}

// Fill every <span data-icon="name"> already in the page markup
export function hydrateIcons(root = document) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    el.replaceWith(icon(el.dataset.icon, el.className));
  });
}
