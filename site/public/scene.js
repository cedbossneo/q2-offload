// The story, driven by scroll: p = how many screens of the story have scrolled.
// Panel i is centred at p = i; its animation plays while p goes from i - 0.7 to i.
// Panels: 0 hero, 1-5 set up, 6-14 a new spool, 15-18 every day.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import {
  COLORS, GATE_X, SPOOL_IN_BOX_Y, PRINTER_X, BED_TOP, VASE, v3,
  makeSpool, makeTag, makePhone, makeBox, makePrinter, makeToolhead, makeHost,
  makeTube, makeCable, makePackets, makeSpaghetti,
} from './models.js';
import { drawScreen } from './screen.js';

const S = 5; // first panel of the spool chapter, minus one
const LAYERS = 210;
const TAU = Math.PI * 2;
const clamp01 = (v) => Math.min(1, Math.max(0, v));
const smooth = (t) => t * t * (3 - 2 * t);
const span = (p, a, b) => smooth(clamp01((p - a) / (b - a)));
const lerp = (a, b, t) => a + (b - a) * t;
const act = (p, i) => span(p, i - 0.7, i);
const between = (p, a, b) => p >= a && p < b;
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Camera pose per panel: [position, target]
const POSES = [
  [v3(5.8, 5.6, 17.5), v3(8.6, 1.5, 0)],
  [v3(21.8, 2.4, 5.8), v3(18.7, 0.5, 1.0)],
  [v3(21.2, 1.7, 4.4), v3(18.7, 0.45, 1.2)],
  [v3(9.2, 7.4, 13.6), v3(10.6, 0.6, 0)],
  [v3(10.2, 6.9, 12.8), v3(10.9, 0.7, 0)],
  [v3(21.5, 4.4, -6.2), v3(16.4, 0.5, -0.6)],
  [v3(1.9, 1.7, 3.4), v3(0, 1, 0)],
  [v3(1.9, 1.65, 3.0), v3(0.45, 1.05, 0.3)],
  [v3(3.6, 2.2, 3.6), v3(0.9, 1.15, 0.6)],
  [v3(7, 5.2, 6.4), v3(7, 1.2, 0)],
  [v3(4.4, 3.1, 4.8), v3(6.7, 1.3, 0.2)],
  [v3(9.0, 5.4, 12.6), v3(12.0, 2.3, 0)],
  [v3(12.6, 3.0, 5.4), v3(14.9, 1.7, -1.1)],
  [v3(13.2, 3.1, 6.8), v3(14, 2.1, 0)],
  [v3(15.5, 2.4, 4.0), v3(14, 1.55, 0.2)],
  [v3(6.2, 4.6, 8.8), v3(7.2, 1.0, 0)],
  [v3(10.4, 5.6, 12.6), v3(10.6, 2.4, 0)],
  [v3(15.7, 1.0, 4.1), v3(14.85, 0.5, 1.8)],
  [v3(16.8, 3.4, 5.8), v3(13.8, 1.4, -0.2)],
];
const CHAPTERS = [[0.5, 5.5], [5.5, 14.5], [14.5, 99]];

const canvas = document.getElementById('scene');
const stage = canvas.parentElement;
const story = document.querySelector('.story');

let renderer = null;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
} catch (err) {
  document.documentElement.classList.add('no-webgl');
  console.warn('WebGL unavailable, showing the story without the 3D scene', err);
}

function setXray(materials, amount) {
  for (const m of materials) {
    const on = amount > 0.01;
    if (m.transparent !== on) { m.transparent = on; m.needsUpdate = true; }
    m.opacity = 1 - 0.78 * amount;
    m.depthWrite = !on;
  }
}

// mcu k: stock until Katapult, amber while Katapult goes on, green once Klipper is flashed
function chipState(p, k) {
  const katapult = 2.35 + 0.2 * k;
  const klipper = 3.35 + 0.2 * k;
  if (p < katapult) return { color: 0x5a6290, pulse: false };
  if (p < katapult + 0.2) return { color: COLORS.pei, pulse: true };
  if (p < klipper) return { color: COLORS.pei, pulse: false };
  if (p < klipper + 0.2) return { color: COLORS.green, pulse: true };
  return { color: COLORS.green, pulse: false };
}

function start() {
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.localClippingEnabled = true;

  const scene = new THREE.Scene();
  scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 200);

  scene.add(new THREE.HemisphereLight(0xc4caff, 0x1a1d40, 0.5));
  const key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.position.set(13, 14, 10);
  key.target.position.set(9, 0, 0);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, { left: -14, right: 14, top: 10, bottom: -10, near: 1, far: 45 });
  key.shadow.bias = -0.0004;
  scene.add(key, key.target);
  const rim = new THREE.DirectionalLight(0x7d88ff, 1.1);
  rim.position.set(-8, 6, -10);
  scene.add(rim);
  const ground = new THREE.Mesh(new THREE.PlaneGeometry(140, 140), new THREE.ShadowMaterial({ opacity: 0.35 }));
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  const grid = new THREE.GridHelper(90, 90, 0x3a4290, 0x262c62);
  grid.material.transparent = true;
  grid.material.opacity = 0.45;
  scene.add(grid);

  const hero = makeSpool(COLORS.green);
  scene.add(hero.group);
  const tag = makeTag();
  hero.body.add(tag.mesh);
  const TAG_HOME = v3(0.62, 0.381, 0);
  const TAG_FROM = v3(0.62, 1.9, 1.2);
  const phone = makePhone();
  scene.add(phone.group);
  const waves = [0, 1, 2].map(() => {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.14, 0.01, 8, 48),
      new THREE.MeshBasicMaterial({ color: COLORS.pei, transparent: true, opacity: 0, toneMapped: false }));
    scene.add(ring);
    return ring;
  });

  const box = makeBox(scene);
  const printer = makePrinter(scene);
  const head = makeToolhead(scene);
  const host = makeHost(scene);
  const chips = [printer.chip, head.chip, box.chip];
  const chipAnchors = chips.map((c) => c.group);
  const xrayMats = [box.shellMat, box.trimMat, printer.frameMat, printer.panelMat, head.bodyMat];

  // PTFE: one tube per gate to the hub, one from the hub to the toolhead
  const HUB = v3(7, 2.6, -1.35);
  const gateTubes = GATE_X.map((gx, g) => makeTube(scene, [v3(gx, 1.95, -0.9), v3(gx, 2.35, -1.15), v3(lerp(gx, 7, 0.6), 2.55, -1.3), HUB],
    { segments: 40, core: g === 1 ? COLORS.green : g === 2 ? COLORS.red : null, radius: 0.04 }));
  const main = makeTube(scene, [HUB, v3(9.6, 4.7, -1.6), v3(12.6, 5.0, -0.8), v3(14, 4.3, 0)], { segments: 200, core: [COLORS.green, COLORS.red] });
  function fillPath(gate, color, f) {
    gateTubes[gate].fill(color, f / 0.25);
    main.fill(color, (f - 0.25) / 0.75);
  }

  // network: host to printer board, printer board to the Box
  const lan = makeCable(scene, [v3(18.7, 0.12, 0.6), v3(18.1, 0.05, -0.8), v3(16.6, 0.05, -2.1), v3(15.6, 0.5, -1.95)]);
  const usb = makeCable(scene, [v3(9.35, 0.3, -0.6), v3(10.8, 0.05, -0.9), v3(12.15, 0.3, -1.2)]);
  const packets = [
    ...makePackets(scene, lan.curve, [COLORS.pei, COLORS.green, COLORS.blue], 12),
    ...makePackets(scene, usb.curve, [COLORS.blue], 5),
  ];

  const vaseRadius = (y) => 0.36 + 0.1 * Math.sin(y * 2.6 + 0.6) + 0.05 * y;
  const vasePoints = [];
  for (let i = 0; i <= 48; i++) {
    const y = (i / 48) * VASE.height;
    vasePoints.push(new THREE.Vector2(vaseRadius(y), y));
  }
  const layerLines = new THREE.CanvasTexture((() => {
    const c = document.createElement('canvas');
    c.width = 8; c.height = 16;
    const g = c.getContext('2d');
    g.fillStyle = '#fff'; g.fillRect(0, 0, 8, 16);
    g.fillStyle = 'rgba(0,0,0,0.22)'; g.fillRect(0, 12, 8, 4);
    return c;
  })());
  layerLines.wrapS = layerLines.wrapT = THREE.RepeatWrapping;
  layerLines.repeat.set(1, 90);
  const clip = new THREE.Plane(v3(0, -1, 0), BED_TOP);
  const vaseMat = new THREE.MeshStandardMaterial({ color: COLORS.green, map: layerLines, roughness: 0.4, side: THREE.DoubleSide, clippingPlanes: [clip] });
  const vase = new THREE.Mesh(new THREE.LatheGeometry(vasePoints, 96), vaseMat);
  vase.position.set(VASE.x, BED_TOP, VASE.z);
  vase.castShadow = true;
  const base = new THREE.Mesh(new THREE.CircleGeometry(vaseRadius(0), 64), vaseMat);
  base.rotation.x = -Math.PI / 2;
  base.position.set(VASE.x, BED_TOP + 0.003, VASE.z);
  scene.add(vase, base);
  const spaghetti = makeSpaghetti(scene, COLORS.red);

  const qFlat = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0));
  const qInBox = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, -Math.PI / 2));
  const HOME = v3(14, 3.1, 0);
  const PURGE = v3(15.35, 1.75, -1.5);
  const BRUSH = v3(12.9, 1.27, -1.6);
  const SPAG = v3(13.2, 1.5, -0.4);

  const ui = bindOverlays();
  let pTarget = 0;
  let p = 0;
  let spin = 0;
  let last = performance.now();
  let visible = true;
  let phoneState = -1;
  let screenKey = '';

  const printProgress = (t) => clamp01((t - (S + 8.6)) / 1.0);
  function vasePoint(pr) {
    const y = VASE.height * pr;
    const a = pr * TAU * 18;
    return v3(VASE.x + vaseRadius(y) * Math.cos(a), BED_TOP + y + 0.01, VASE.z + vaseRadius(y) * Math.sin(a));
  }

  function toolheadAt(t) {
    const q = t - S;
    if (q < 6.4) return HOME.clone();
    if (q < 6.8) return HOME.clone().lerp(PURGE, span(q, 6.4, 6.8));
    if (q < 7.15) return PURGE.clone();
    if (q < 7.35) return PURGE.clone().lerp(BRUSH, span(q, 7.15, 7.35));
    if (q < 7.75) return BRUSH.clone().add(v3(0.25 * Math.sin(((q - 7.35) / 0.4) * Math.PI * 6), 0, 0));
    if (q < 8.3) return BRUSH.clone().lerp(HOME, span(q, 7.75, 8.3));
    if (q < 8.6) return HOME.clone().lerp(vasePoint(0), span(q, 8.3, 8.6));
    if (q < 9.6) return vasePoint(printProgress(t));
    const top = vasePoint(1).add(v3(0, 0.3, 0));
    if (t < 15.1) return vasePoint(1).lerp(top, span(t, 14.6, 15.1));
    if (t < 15.35) return top.lerp(PURGE, span(t, 15.1, 15.35));
    if (t < 16.6) return PURGE.clone();
    if (t < 17.2) return PURGE.clone().lerp(SPAG, span(t, 16.6, 17.2));
    if (t < 17.8) return SPAG.clone().add(v3(0.4 * Math.sin((t - 17.2) * 24), 0.08 * (t - 17.2), 0.3 * Math.cos((t - 17.2) * 17)));
    return SPAG.clone().add(v3(0, 0.05, 0)).lerp(HOME, span(t, 17.8, 18.1));
  }

  function readScroll() {
    const rect = story.getBoundingClientRect();
    pTarget = Math.max(0, -rect.top / window.innerHeight);
    visible = rect.bottom > 0;
  }

  function resize() {
    const w = stage.clientWidth;
    const h = stage.clientHeight;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    // keep the scene clear of the text: right of it on wide screens, above it on narrow ones
    if (w > 820) camera.setViewOffset(w, h, -w * 0.17, 0, w, h);
    else camera.setViewOffset(w, h, 0, h * 0.06, w, h);
    camera.updateProjectionMatrix();
  }

  function updateCamera(time) {
    const pos = POSES[0][0].clone();
    const target = POSES[0][1].clone();
    for (let i = 1; i < POSES.length; i++) {
      const a = act(p, i);
      if (a <= 0) break;
      pos.lerp(POSES[i][0], a);
      target.lerp(POSES[i][1], a);
    }
    if (!reducedMotion && p < 1) {
      pos.x += Math.sin(time * 0.25) * 0.3 * (1 - p);
      pos.y += Math.sin(time * 0.31) * 0.15 * (1 - p);
    }
    // portrait screens see less width: step back so the subject still fits
    if (camera.aspect < 1.2) pos.sub(target).multiplyScalar(Math.pow(1.2 / camera.aspect, 0.75)).add(target);
    camera.position.copy(pos);
    camera.lookAt(target);
  }

  function updateSetup(time) {
    host.group.scale.setScalar(Math.max(0.001, span(p, 0.3, 0.8)));
    host.group.visible = p > 0.3;
    lan.mesh.geometry.setDrawRange(0, Math.floor(span(p, 0.55, 1.0) * 80) * 8 * 6);
    usb.mesh.geometry.setDrawRange(0, Math.floor(span(p, 4.1, 4.5) * 80) * 8 * 6);
    const installing = between(p, 1.3, 4.9);
    host.ledMat.color.setHex(installing && Math.sin(time * 9) > 0 ? 0xffffff : COLORS.pei);
    const xray = span(p, 2.25, 2.6) * (1 - span(p, 4.6, 5.0));
    setXray(xrayMats, xray);
    chips.forEach((c, k) => {
      c.group.visible = xray > 0.02;
      const st = chipState(p, k);
      c.ringMat.color.setHex(st.color);
      c.ringMat.opacity = st.pulse ? 0.4 + 0.6 * Math.abs(Math.sin(time * 7)) : 0.95;
    });
    const linkUp = p > 4.3;
    packets.forEach((pk) => {
      pk.m.visible = linkUp;
      if (!linkUp) return;
      let f = (time * 0.32 + pk.offset) % 1;
      if (pk.dir < 0) f = 1 - f;
      pk.m.position.copy(pk.curve.getPointAt(f));
      pk.m.material.opacity = 0.9 * (p < 6 ? 1 : 0.55);
    });
    ui.chipLabels(xray, chipAnchors, camera, stage);
  }

  function updateSpool(time, dt) {
    const q = p - S;
    const settle = span(q, 1.3, 2.0);
    if (!reducedMotion) spin += dt * 0.5 * (1 - settle);
    const rest = Math.round(spin / TAU) * TAU;
    const feed = span(q, 6.15, 6.6) * Math.PI * 3 - span(p, 15.3, 15.6) * Math.PI * 2;
    hero.body.rotation.y = lerp(spin, rest, settle) + feed;

    tag.mesh.visible = q > 1.3;
    const tagIn = span(q, 1.3, 1.95);
    tag.mesh.position.copy(TAG_FROM).lerp(TAG_HOME, tagIn);
    tag.mesh.rotation.set(lerp(-1.2, 0, tagIn), 0, lerp(0.8, 0, tagIn));

    const phoneIn = span(q, 2.3, 2.95);
    const phoneOut = span(q, 3.3, 3.6);
    const phoneScale = phoneIn * (1 - phoneOut);
    phone.group.visible = phoneScale > 0.01;
    const tagWorld = tag.mesh.getWorldPosition(v3(0, 0, 0));
    phone.group.position.set(lerp(2.4, 1.6, phoneIn) + phoneOut * 1.5, lerp(0.6, 1.8, phoneIn) + phoneOut * 1.5, 0.85);
    phone.group.scale.setScalar(Math.max(phoneScale * 0.75, 0.001));
    phone.group.lookAt(tagWorld);
    const state = q < 2.6 ? 0 : q < 3.0 ? 1 : 2;
    if (state !== phoneState) { phoneState = state; phone.draw(state); }
    const writing = q > 2.6 && q < 3.15;
    waves.forEach((ring, k) => {
      const f = (time * 0.9 + k / 3) % 1;
      ring.visible = writing;
      ring.position.copy(phone.group.position).lerp(tagWorld, f);
      ring.lookAt(tagWorld);
      ring.scale.setScalar(1 + f * 1.4);
      ring.material.opacity = writing ? Math.sin(f * Math.PI) * 0.9 : 0;
    });
    tag.coilMat.emissiveIntensity = writing ? 0.35 + 0.35 * Math.sin(time * 10) : 0;

    const a4 = act(q, 4);
    const over = clamp01(a4 / 0.75);
    const drop = clamp01((a4 - 0.75) / 0.25);
    let y = lerp(1, 3.3, smooth(over)) + Math.sin(over * Math.PI) * 1.3;
    y = lerp(y, SPOOL_IN_BOX_Y, smooth(drop));
    hero.group.position.set(lerp(0, GATE_X[1], smooth(over)), y, 0);
    hero.group.quaternion.copy(qFlat).slerp(qInBox, smooth(over));
    const arrive = span(p, 5.25, 5.95);
    hero.group.visible = arrive > 0.01;
    if (q < 3.3) hero.group.scale.setScalar(Math.max(0.001, arrive));
    box.lidPivot.rotation.x = -1.15 * span(q, 3.35, 3.9) * (1 - span(p, 14.4, 14.9));

    const reading = q > 4.15 && q < 5.2;
    box.readerMats[0].emissiveIntensity = reading ? 0.6 + 0.6 * Math.sin(time * 8) : 0.15;
    box.leds[1].material.emissive.setHex(q > 4.55 ? COLORS.green : 0x3a4060);
  }

  function updatePrinter(time) {
    const q = p - S;
    // filament: green loads for the calibration, unloads at the colour change, red loads
    fillPath(1, COLORS.green, span(q, 6.15, 6.6) * (1 - span(p, 15.3, 15.6)));
    fillPath(2, COLORS.red, span(p, 15.65, 16.0));
    if (box.spools[2]) box.spools[2].body.rotation.y = 2.6 + span(p, 15.65, 16.0) * Math.PI * 3;

    const tip = toolheadAt(p);
    head.toolhead.position.copy(tip);
    head.beamX.position.set(PRINTER_X, tip.y + 0.85, tip.z);
    head.railL.position.set(PRINTER_X - 1.7, tip.y + 0.85, 0);
    head.railR.position.set(PRINTER_X + 1.7, tip.y + 0.85, 0);
    const calibrating = q > 6.8 && q < 7.15;
    const purging = p > 16.0 && p < 16.4;
    head.strand.visible = calibrating || purging;
    head.strandMat.color.setHex(purging ? COLORS.red : COLORS.green);
    head.strand.position.copy(tip);
    head.strand.scale.y = Math.max(0.001, (calibrating ? span(q, 6.8, 7.05) : span(p, 16.0, 16.3)) * 0.5);
    head.loadRings.forEach((r, k) => {
      const f = (time * 1.2 + k / 2) % 1;
      r.scale.setScalar(1 + f * 1.6);
      r.material.opacity = calibrating ? (1 - f) * 0.8 : 0;
    });

    const pr = printProgress(p);
    clip.constant = BED_TOP + VASE.height * pr;
    vase.visible = base.visible = pr > 0;
    spaghetti.reveal(span(p, 17.2, 17.8));
    printer.coneMat.opacity = 0.1 * span(p, 16.9, 17.2);

    const heat = span(p, 14.4, 14.9) * (1 - span(p, 15.25, 15.5));
    box.heatLight.intensity = heat * (6 + 1.5 * Math.sin(time * 3));
    box.heatMat.opacity = heat * 0.8;
    if (heat > 0) {
      const arr = box.heat.geometry.attributes.position;
      for (let i = 0; i < arr.count; i++) arr.setY(i, (arr.getY(i) + 0.006) % 1.6);
      arr.needsUpdate = true;
    }

    const screen = screenStateAt(p, pr);
    if (screen.key !== screenKey) {
      screenKey = screen.key;
      drawScreen(printer.screen, screen.name, screen.progress);
    }
    return pr;
  }

  function screenStateAt(t, pr) {
    const q = t - S;
    const calib = span(q, 6.5, 7.4);
    if (t < 4.6) return { name: 'convert', key: 'convert', progress: 0 };
    if (q < 5.55) return { name: 'idle', key: 'idle', progress: 0 };
    if (q < 6.3) return { name: 'dialog', key: 'dialog', progress: 0 };
    if (q < 7.45) return { name: 'calib', key: 'calib' + Math.round(calib * 20), progress: calib };
    if (q < 8.6) return { name: 'saved', key: 'saved', progress: 1 };
    if (t < 14.75) return { name: 'print', key: 'print' + Math.round(pr * 40), progress: pr };
    if (t < 15.25) return { name: 'dry', key: 'dry', progress: 0 };
    if (t < 16.3) return { name: 'swap', key: 'swap' + (t > 15.65 ? 1 : 0), progress: t > 15.65 ? 1 : 0 };
    if (t < 17.75) return { name: 'helix', key: 'helix', progress: 0 };
    return { name: 'paused', key: 'paused', progress: 0 };
  }

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    p = reducedMotion ? pTarget : p + (pTarget - p) * Math.min(1, dt * 7);
    if (visible) {
      const time = now / 1000;
      updateCamera(time);
      updateSetup(time);
      updateSpool(time, dt);
      const pr = updatePrinter(time);
      ui.update(p, pr);
      renderer.render(scene, camera);
    }
    requestAnimationFrame(frame);
  }

  window.addEventListener('scroll', readScroll, { passive: true });
  window.addEventListener('resize', () => { resize(); readScroll(); });
  resize();
  readScroll();
  p = pTarget;
  requestAnimationFrame(frame);
}

// HTML over the scene: what the screens, Spoolman and the slicer show at each moment
function bindOverlays() {
  const overlays = [...document.querySelectorAll('.ov')].map((el) => ({ el, from: +el.dataset.from, to: +el.dataset.to }));
  const timed = [...document.querySelectorAll('[data-at]')];
  const q = (id) => document.getElementById(id);
  const chapterLinks = [...document.querySelectorAll('.chapters a')];
  const labels = [...document.querySelectorAll('.chip-label')];
  const paCurve = lineChart('curve', 'dots', 'best', 'best-label');
  const detect = detectChart();
  const tmp = v3(0, 0, 0);

  chapterLinks.forEach((a) => a.addEventListener('click', (e) => {
    e.preventDefault();
    const story = document.querySelector('.story');
    window.scrollTo({ top: story.offsetTop + (+a.dataset.p) * window.innerHeight, behavior: reducedMotion ? 'auto' : 'smooth' });
  }));

  return {
    update(p, pr) {
      overlays.forEach((o) => o.el.classList.toggle('on', p >= o.from && p < o.to));
      timed.forEach((el) => el.classList.toggle('lit', p >= +el.dataset.at));
      q('btn-now').classList.toggle('pressed', p > S + 6.15);
      paCurve(span(p, S + 6.6, S + 7.05));
      q('chart').classList.toggle('done', p > S + 7.05);
      q('layer').textContent = `layer ${Math.round(pr * LAYERS)} of ${LAYERS}`;
      q('meter').style.width = `${pr * 100}%`;
      const dry = span(p, 14.45, 15.0);
      q('dry-left').textContent = `${4 - Math.floor(dry * 0.9)} h ${String(52 - Math.round(dry * 40)).padStart(2, '0')} min left`;
      q('dry-hum').textContent = `${Math.round(41 - dry * 17)} %`;
      q('dry-meter').style.width = `${(0.03 + dry * 0.12) * 100}%`;
      const swapped = p > 15.65;
      q('gs-1').textContent = p < 15.3 ? 'in extruder' : p < 15.6 ? 'unloading' : 'ready';
      q('gs-2').textContent = !swapped ? 'ready' : p < 16.0 ? 'loading' : 'in extruder';
      q('gr-1').classList.toggle('active', !swapped);
      q('gr-2').classList.toggle('active', swapped);
      detect(span(p, 17.2, 17.85));
      chapterLinks.forEach((a, i) => a.classList.toggle('on', p >= CHAPTERS[i][0] && p < CHAPTERS[i][1]));
      document.querySelector('.chapters').classList.toggle('on', p > 0.5 && p < 18.6);
    },
    chipLabels(xray, anchors, camera, stage) {
      labels.forEach((el, i) => {
        el.style.opacity = xray > 0.3 ? 1 : 0;
        if (xray <= 0.3) return;
        anchors[i].getWorldPosition(tmp).project(camera);
        const x = (tmp.x * 0.5 + 0.5) * stage.clientWidth;
        const y = (-tmp.y * 0.5 + 0.5) * stage.clientHeight;
        el.style.transform = `translate(${x}px, ${y}px) translate(-50%, -150%)`;
      });
    },
  };
}

// Pressure error for each K tried (example data with its minimum at 0.042)
function lineChart(curveId, dotsId, bestId, labelId) {
  const ks = [];
  for (let k = 0.02; k <= 0.1201; k += 0.01) ks.push(k);
  const err = (k) => 0.12 + Math.pow((k - 0.042) / 0.078, 2) * 0.62 + Math.sin(k * 400) * 0.015;
  const x = (k) => 36 + ((k - 0.02) / 0.1) * 270;
  const y = (e) => 140 - Math.min(1, e) * 120;
  const pts = ks.map((k) => [x(k), y(err(k))]);
  const poly = document.getElementById(curveId);
  poly.setAttribute('points', pts.map((pt) => pt.join(',')).join(' '));
  const dots = document.getElementById(dotsId);
  const dotEls = pts.map(([cx, cy]) => {
    const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c.setAttribute('cx', cx); c.setAttribute('cy', cy); c.setAttribute('r', 3.2);
    c.setAttribute('class', 'dot');
    c.style.opacity = 0;
    dots.appendChild(c);
    return c;
  });
  const best = document.getElementById(bestId);
  best.setAttribute('cx', x(0.042)); best.setAttribute('cy', y(err(0.042)));
  const label = document.getElementById(labelId);
  label.setAttribute('x', x(0.042) - 22); label.setAttribute('y', y(err(0.042)) - 14);
  const length = poly.getTotalLength();
  poly.style.strokeDasharray = length;
  return (f) => {
    poly.style.strokeDashoffset = length * (1 - f);
    dotEls.forEach((d, i) => { d.style.opacity = f * (ks.length - 1) >= i ? 1 : 0; });
  };
}

// Failure score over the frames of a print: quiet, then spaghetti, warning, pause
function detectChart() {
  const poly = document.getElementById('det-curve');
  const n = 30;
  const score = (i) => (i < 14 ? 0.05 + 0.04 * Math.sin(i * 1.7) : 0.05 + Math.pow((i - 14) / 16, 1.4) * 1.1);
  const pts = Array.from({ length: n + 1 }, (_, i) => [20 + (i / n) * 290, 140 - Math.min(1.15, score(i)) * 110]);
  poly.setAttribute('points', pts.map((pt) => pt.join(',')).join(' '));
  const length = poly.getTotalLength();
  poly.style.strokeDasharray = length;
  const card = document.getElementById('detect');
  return (f) => {
    poly.style.strokeDashoffset = length * (1 - f);
    card.classList.toggle('warn', f > 0.62);
    card.classList.toggle('paused', f > 0.9);
  };
}

if (renderer) start();
