// The spool's journey, driven by scroll: p = how many screens of the story have scrolled.
// Panel i is centred at p = i; its animation plays while p goes from i - 0.7 to i.
import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const COLORS = { green: 0x34c17b, yellow: 0xf4c63d, red: 0xef5a4c, blue: 0x4c8df6, shell: 0x2b3042, trim: 0x3b4258, pei: 0xd4b06a };
const GATE_X = [5.5, 6.5, 7.5, 8.5];
const SPOOL_IN_BOX_Y = 1.12;
const PRINTER_X = 14;
const BED_TOP = 1.03;
const VASE = { x: 14, z: 0.2, height: 1.25 };
const LAYERS = 210;

const clamp01 = (v) => Math.min(1, Math.max(0, v));
const smooth = (t) => t * t * (3 - 2 * t);
const span = (p, a, b) => smooth(clamp01((p - a) / (b - a)));
const lerp = (a, b, t) => a + (b - a) * t;
const v3 = (x, y, z) => new THREE.Vector3(x, y, z);
const act = (p, i) => span(p, i - 0.7, i);
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

const canvas = document.getElementById('scene');
const stage = canvas.parentElement;
const story = document.querySelector('.story');

let renderer;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
} catch (err) {
  document.documentElement.classList.add('no-webgl');
  console.warn('WebGL unavailable, showing the story without the 3D scene', err);
}

function canvasTexture(w, h, draw) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  const ctx = c.getContext('2d');
  draw(ctx, w, h);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return { tex, ctx, canvas: c };
}

function ringProfile(r0, r1, h) {
  return [new THREE.Vector2(r0, -h / 2), new THREE.Vector2(r1, -h / 2), new THREE.Vector2(r1, h / 2),
    new THREE.Vector2(r0, h / 2), new THREE.Vector2(r0, -h / 2)];
}

// Wound filament: lines of constant v are circles on every face of the lathe
const grooves = canvasTexture(32, 256, (g, w, h) => {
  g.fillStyle = '#ffffff';
  g.fillRect(0, 0, w, h);
  for (let y = 0; y < h; y += 4) {
    g.fillStyle = 'rgba(0,0,0,0.30)';
    g.fillRect(0, y, w, 1.5);
    g.fillStyle = 'rgba(255,255,255,0.6)';
    g.fillRect(0, y + 2, w, 1);
  }
}).tex;
grooves.wrapS = grooves.wrapT = THREE.RepeatWrapping;
grooves.repeat.set(1, 4.5);

const layerLines = canvasTexture(8, 16, (g, w, h) => {
  g.fillStyle = '#ffffff';
  g.fillRect(0, 0, w, h);
  g.fillStyle = 'rgba(0,0,0,0.22)';
  g.fillRect(0, 12, w, 4);
}).tex;
layerLines.wrapS = layerLines.wrapT = THREE.RepeatWrapping;
layerLines.repeat.set(1, 90);

function makeSpool(color) {
  const group = new THREE.Group();
  const body = new THREE.Group(); // spool axis = local Y
  group.add(body);
  const flangeMat = new THREE.MeshPhysicalMaterial({ color: 0x8a93c8, roughness: 0.15, transparent: true, opacity: 0.34, depthWrite: false, clearcoat: 0.7, clearcoatRoughness: 0.2 });
  for (const side of [-1, 1]) {
    const flange = new THREE.Mesh(new THREE.LatheGeometry(ringProfile(0.24, 1, 0.05), 96), flangeMat);
    flange.position.y = side * 0.35;
    flange.castShadow = true;
    body.add(flange);
  }
  body.add(new THREE.Mesh(new THREE.LatheGeometry(ringProfile(0.2, 0.33, 0.72), 64),
    new THREE.MeshStandardMaterial({ color: 0x2a2f40, roughness: 0.5 })));
  const wound = new THREE.Mesh(new THREE.LatheGeometry(ringProfile(0.33, 0.86, 0.64), 128),
    new THREE.MeshStandardMaterial({ color, map: grooves, roughness: 0.3, metalness: 0.05 }));
  wound.castShadow = true;
  body.add(wound);
  return { group, body };
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
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;

  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 200);

  scene.add(new THREE.HemisphereLight(0xc4caff, 0x1a1d40, 0.5));
  const key = new THREE.DirectionalLight(0xffffff, 2.2);
  key.position.set(12, 14, 10);
  key.target.position.set(8, 0, 0);
  key.castShadow = true;
  key.shadow.mapSize.set(2048, 2048);
  Object.assign(key.shadow.camera, { left: -13, right: 13, top: 10, bottom: -10, near: 1, far: 45 });
  key.shadow.bias = -0.0004;
  scene.add(key, key.target);
  const rim = new THREE.DirectionalLight(0x7d88ff, 1.1);
  rim.position.set(-8, 6, -10);
  scene.add(rim);

  const ground = new THREE.Mesh(new THREE.PlaneGeometry(120, 120), new THREE.ShadowMaterial({ opacity: 0.35 }));
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  scene.add(ground);
  const grid = new THREE.GridHelper(80, 80, 0x3a4290, 0x262c62);
  grid.material.transparent = true;
  grid.material.opacity = 0.45;
  scene.add(grid);

  // The new spool and its tag
  const hero = makeSpool(COLORS.green);
  scene.add(hero.group);
  const tagWhite = new THREE.MeshStandardMaterial({ color: 0xf2f3fa, roughness: 0.6 });
  const coil = canvasTexture(256, 256, (g) => {
    g.fillStyle = '#f2f3fa';
    g.fillRect(0, 0, 256, 256);
    g.strokeStyle = '#b8893a';
    g.lineWidth = 6;
    for (let r = 112; r > 56; r -= 13) { g.beginPath(); g.arc(128, 128, r, 0, Math.PI * 2); g.stroke(); }
    g.fillStyle = '#7a5a22';
    g.fillRect(114, 30, 28, 34);
  });
  const coilMat = new THREE.MeshStandardMaterial({ map: coil.tex, roughness: 0.5, emissive: COLORS.pei, emissiveIntensity: 0 });
  const tag = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.012, 48), [tagWhite, coilMat, tagWhite]);
  tag.castShadow = true;
  hero.body.add(tag);
  const TAG_HOME = v3(0.62, 0.381, 0);
  const TAG_FROM = v3(0.62, 1.9, 1.2);

  // Phone writing the tag
  const phone = new THREE.Group();
  const phoneBody = new THREE.Mesh(new RoundedBoxGeometry(0.56, 1.12, 0.07, 4, 0.07),
    new THREE.MeshPhysicalMaterial({ color: 0x232838, roughness: 0.3, metalness: 0.6, clearcoat: 1 }));
  phone.add(phoneBody);
  const phoneScreen = canvasTexture(256, 512, () => {});
  const screenMesh = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 1.04),
    new THREE.MeshBasicMaterial({ map: phoneScreen.tex, toneMapped: false }));
  screenMesh.rotation.y = Math.PI; // the back of the phone faces the tag
  screenMesh.position.z = -0.037;
  phone.add(screenMesh);
  scene.add(phone);
  let phoneState = -1;
  function drawPhone(state) {
    const g = phoneScreen.ctx;
    g.fillStyle = '#0f1229';
    g.fillRect(0, 0, 256, 512);
    g.fillStyle = '#eef0fa';
    g.font = 'bold 22px sans-serif';
    g.fillText('Write NFC tag', 24, 60);
    const rows = [['Brand', 'Sunlu'], ['Material', 'PETG'], ['Nozzle', '230-255 °C'], ['Bed', '70-80 °C']];
    g.font = '17px sans-serif';
    rows.forEach(([k, v], i) => {
      const y = 112 + i * 52;
      g.fillStyle = '#8f96c4'; g.fillText(k, 24, y);
      g.fillStyle = '#eef0fa'; g.fillText(v, 130, y);
    });
    g.fillStyle = '#8f96c4'; g.fillText('Colour', 24, 320);
    g.fillStyle = '#34c17b'; g.beginPath(); g.arc(148, 314, 14, 0, Math.PI * 2); g.fill();
    if (state === 2) {
      g.fillStyle = '#34c17b';
      g.beginPath(); g.arc(128, 420, 34, 0, Math.PI * 2); g.fill();
      g.strokeStyle = '#0f1229'; g.lineWidth = 7; g.lineCap = 'round';
      g.beginPath(); g.moveTo(112, 421); g.lineTo(124, 433); g.lineTo(146, 409); g.stroke();
      g.fillStyle = '#eef0fa'; g.font = 'bold 17px sans-serif'; g.fillText('Tag written', 82, 484);
    } else {
      g.fillStyle = state === 1 ? '#a9843c' : '#d4b06a';
      g.beginPath(); g.roundRect(24, 392, 208, 56, 28); g.fill();
      g.fillStyle = '#1b1606'; g.font = 'bold 18px sans-serif';
      g.fillText(state === 1 ? 'Hold near tag' : 'Write tag', state === 1 ? 68 : 88, 427);
    }
    phoneScreen.tex.needsUpdate = true;
  }
  const waves = [0, 1, 2].map(() => {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(0.14, 0.01, 8, 48),
      new THREE.MeshBasicMaterial({ color: COLORS.pei, transparent: true, opacity: 0, toneMapped: false }));
    scene.add(ring);
    return ring;
  });

  // The Box: four gates, two NFC readers (gates 0-1 and 2-3), a lid hinged at the back
  const box = new THREE.Group();
  box.position.set(7, 0, 0);
  scene.add(box);
  const shellMat = new THREE.MeshStandardMaterial({ color: COLORS.shell, roughness: 0.55, metalness: 0.15 });
  const trimMat = new THREE.MeshStandardMaterial({ color: COLORS.trim, roughness: 0.45, metalness: 0.2 });
  const addBox = (parent, w, h, d, x, y, z, mat, radius = 0.04) => {
    const m = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, radius), mat);
    m.position.set(x, y, z);
    m.castShadow = m.receiveShadow = true;
    parent.add(m);
    return m;
  };
  addBox(box, 4.7, 0.14, 2.3, 0, 0.07, 0, shellMat);
  addBox(box, 4.7, 1.7, 0.1, 0, 0.85, -1.1, shellMat);
  addBox(box, 0.12, 1.7, 2.3, -2.3, 0.85, 0, shellMat);
  addBox(box, 0.12, 1.7, 2.3, 2.3, 0.85, 0, shellMat);
  addBox(box, 4.7, 0.75, 0.12, 0, 0.375, 1.1, trimMat);
  for (const z of [-0.55, 0.55]) {
    const roller = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 4.4, 24), trimMat);
    roller.rotation.z = Math.PI / 2;
    roller.position.set(0, 0.2, z);
    box.add(roller);
  }
  const readerMats = [0, 1].map(() => new THREE.MeshStandardMaterial({ color: 0x1b2a3a, emissive: COLORS.pei, emissiveIntensity: 0.15 }));
  [-1, 1].forEach((x, i) => addBox(box, 0.5, 0.04, 0.5, x, 0.16, 0.75, readerMats[i], 0.01));
  const leds = GATE_X.map((gx) => {
    const led = new THREE.Mesh(new THREE.SphereGeometry(0.05, 16, 16),
      new THREE.MeshStandardMaterial({ color: 0x222639, emissive: 0x3a4060, emissiveIntensity: 1 }));
    led.position.set(gx - 7, 0.55, 1.17);
    box.add(led);
    return led;
  });
  const lidPivot = new THREE.Group();
  lidPivot.position.set(0, 1.72, -1.12);
  box.add(lidPivot);
  const lid = new THREE.Mesh(new RoundedBoxGeometry(4.7, 0.08, 2.3, 3, 0.04),
    new THREE.MeshPhysicalMaterial({ color: 0x3a4170, roughness: 0.1, transparent: true, opacity: 0.35 }));
  lid.position.z = 1.15;
  lidPivot.add(lid);
  [[0, COLORS.yellow], [2, COLORS.red], [3, COLORS.blue]].forEach(([gate, color]) => {
    const s = makeSpool(color);
    s.group.position.set(GATE_X[gate], SPOOL_IN_BOX_Y, 0);
    s.group.rotation.z = -Math.PI / 2;
    s.body.rotation.y = gate * 1.3;
    scene.add(s.group);
    leds[gate].material.emissive.setHex(color);
  });

  // The printer: open front, bed, gantry, purge chute and wipe brush
  const printer = new THREE.Group();
  printer.position.set(PRINTER_X, 0, 0);
  scene.add(printer);
  const frameMat = new THREE.MeshStandardMaterial({ color: 0x252a3b, roughness: 0.5, metalness: 0.3 });
  const panelMat = new THREE.MeshStandardMaterial({ color: 0x2d3346, roughness: 0.65, side: THREE.DoubleSide });
  addBox(printer, 3.7, 0.75, 3.6, 0, 0.375, 0, frameMat);
  addBox(printer, 3.7, 0.1, 3.6, 0, 4.25, 0, frameMat);
  addBox(printer, 0.08, 3.5, 3.6, -1.81, 2.5, 0, panelMat, 0.02);
  addBox(printer, 0.08, 3.5, 3.6, 1.81, 2.5, 0, panelMat, 0.02);
  addBox(printer, 3.7, 3.5, 0.08, 0, 2.5, -1.76, panelMat, 0.02);
  for (const x of [-1.8, 1.8]) for (const z of [-1.75, 1.75]) addBox(printer, 0.14, 4.3, 0.14, x, 2.15, z, frameMat, 0.03);
  const pei = canvasTexture(256, 256, (g) => {
    g.fillStyle = '#c9a35e';
    g.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 6000; i++) {
      const s = Math.random();
      g.fillStyle = s > 0.5 ? 'rgba(255,240,200,0.18)' : 'rgba(90,60,20,0.18)';
      g.fillRect(Math.random() * 256, Math.random() * 256, 1.5, 1.5);
    }
  });
  addBox(printer, 2.9, 0.12, 2.9, 0, 0.93, 0, frameMat, 0.02);
  const bed = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.04, 2.8),
    new THREE.MeshStandardMaterial({ map: pei.tex, roughness: 0.55, metalness: 0.35 }));
  bed.position.set(0, 1.01, 0);
  bed.receiveShadow = true;
  printer.add(bed);
  addBox(printer, 0.5, 0.6, 0.4, 1.35, 1.2, -1.5, frameMat);
  const brush = addBox(printer, 0.6, 0.18, 0.2, -1.1, 1.12, -1.6, new THREE.MeshStandardMaterial({ color: 0x15171f, roughness: 1 }), 0.02);
  brush.castShadow = false;

  const screenTex = canvasTexture(512, 288, () => {});
  const printerScreen = new THREE.Mesh(new THREE.PlaneGeometry(0.96, 0.54),
    new THREE.MeshBasicMaterial({ map: screenTex.tex, toneMapped: false }));
  printerScreen.position.set(0.9, 0.4, 1.805);
  printer.add(printerScreen);
  let screenState = '';
  function drawScreen(state, progress = 0) {
    const g = screenTex.ctx;
    g.fillStyle = '#0d1026';
    g.fillRect(0, 0, 512, 288);
    g.fillStyle = '#eef0fa';
    g.font = 'bold 30px sans-serif';
    const titles = { idle: 'Ready', dialog: 'New filament', calib: 'Measuring PA', saved: 'PA 0.042 saved', print: 'Printing' };
    g.fillText(titles[state], 32, 60);
    if (state === 'idle') {
      [COLORS.yellow, COLORS.green, COLORS.red, COLORS.blue].forEach((c, i) => {
        g.fillStyle = '#' + c.toString(16).padStart(6, '0');
        g.beginPath(); g.arc(80 + i * 115, 170, 36, 0, Math.PI * 2); g.fill();
      });
    } else if (state === 'dialog') {
      g.fillStyle = '#d4b06a'; g.beginPath(); g.roundRect(32, 110, 448, 64, 14); g.fill();
      g.fillStyle = '#1b1606'; g.font = 'bold 26px sans-serif'; g.fillText('Calibrate now', 170, 152);
      g.fillStyle = '#262c66'; g.beginPath(); g.roundRect(32, 190, 216, 60, 14); g.roundRect(264, 190, 216, 60, 14); g.fill();
    } else {
      g.fillStyle = '#262c66'; g.beginPath(); g.roundRect(32, 150, 448, 26, 13); g.fill();
      g.fillStyle = state === 'saved' ? '#d4b06a' : '#34c17b';
      g.beginPath(); g.roundRect(32, 150, Math.max(26, 448 * progress), 26, 13); g.fill();
    }
    screenTex.tex.needsUpdate = true;
  }

  const toolhead = new THREE.Group();
  scene.add(toolhead);
  addBox(toolhead, 0.55, 0.55, 0.5, 0, 0.42, 0, new THREE.MeshStandardMaterial({ color: 0x30364a, roughness: 0.4, metalness: 0.4 }), 0.06);
  addBox(toolhead, 0.56, 0.08, 0.51, 0, 0.62, 0, new THREE.MeshStandardMaterial({ color: COLORS.pei, roughness: 0.35, metalness: 0.6 }), 0.02);
  const nozzle = new THREE.Mesh(new THREE.ConeGeometry(0.07, 0.15, 24),
    new THREE.MeshStandardMaterial({ color: 0xc9a35e, roughness: 0.25, metalness: 0.9 }));
  nozzle.rotation.x = Math.PI;
  nozzle.position.y = 0.075;
  toolhead.add(nozzle);
  const loadRings = [0, 1].map(() => {
    const r = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.008, 8, 48),
      new THREE.MeshBasicMaterial({ color: COLORS.green, transparent: true, opacity: 0, toneMapped: false }));
    r.rotation.x = Math.PI / 2;
    toolhead.add(r);
    return r;
  });
  const strand = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 1, 12),
    new THREE.MeshStandardMaterial({ color: COLORS.green, roughness: 0.3 }));
  strand.geometry.translate(0, -0.5, 0);
  scene.add(strand);
  const gantryMat = new THREE.MeshStandardMaterial({ color: 0x1e2232, roughness: 0.35, metalness: 0.7 });
  const beamX = new THREE.Mesh(new THREE.BoxGeometry(3.5, 0.1, 0.12), gantryMat);
  const railL = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.1, 3.4), gantryMat);
  const railR = railL.clone();
  scene.add(beamX, railL, railR);

  // PTFE tube from gate 1 to the printer, and the filament that fills it
  const route = new THREE.CatmullRomCurve3([v3(6.5, 1.95, -0.9), v3(6.9, 3.1, -1.3), v3(9.6, 4.7, -1.6), v3(12.6, 5.0, -0.8), v3(14, 4.3, 0)]);
  const TUBE_SEGMENTS = 220;
  const ptfe = new THREE.Mesh(new THREE.TubeGeometry(route, TUBE_SEGMENTS, 0.05, 12),
    new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.2, transparent: true, opacity: 0.28, depthWrite: false }));
  const fill = new THREE.Mesh(new THREE.TubeGeometry(route, TUBE_SEGMENTS, 0.026, 8),
    new THREE.MeshStandardMaterial({ color: COLORS.green, roughness: 0.3, emissive: COLORS.green, emissiveIntensity: 0.25 }));
  scene.add(fill, ptfe);

  // The print: a vase revealed layer by layer with a clipping plane
  const vaseRadius = (y) => 0.36 + 0.1 * Math.sin(y * 2.6 + 0.6) + 0.05 * y;
  const vasePoints = [];
  for (let i = 0; i <= 48; i++) {
    const y = (i / 48) * VASE.height;
    vasePoints.push(new THREE.Vector2(vaseRadius(y), y));
  }
  const clip = new THREE.Plane(v3(0, -1, 0), BED_TOP);
  const vaseMat = new THREE.MeshStandardMaterial({ color: COLORS.green, map: layerLines, roughness: 0.4, side: THREE.DoubleSide, clippingPlanes: [clip] });
  const vase = new THREE.Mesh(new THREE.LatheGeometry(vasePoints, 96), vaseMat);
  vase.position.set(VASE.x, BED_TOP, VASE.z);
  vase.castShadow = true;
  const base = new THREE.Mesh(new THREE.CircleGeometry(vaseRadius(0), 64), vaseMat);
  base.rotation.x = -Math.PI / 2;
  base.position.set(VASE.x, BED_TOP + 0.003, VASE.z);
  scene.add(vase, base);

  // Camera poses, one per panel
  const poses = [
    [v3(3.2, 2.1, 5.4), v3(0, 1, 0)],
    [v3(1.9, 1.7, 3.4), v3(0, 1, 0)],
    [v3(1.9, 1.65, 3.0), v3(0.45, 1.05, 0.3)],
    [v3(3.6, 2.2, 3.6), v3(0.9, 1.15, 0.6)],
    [v3(7, 5.2, 6.4), v3(7, 1.2, 0)],
    [v3(4.4, 3.1, 4.8), v3(6.7, 1.3, 0.2)],
    [v3(9.0, 5.4, 12.6), v3(12.0, 2.3, 0)],
    [v3(12.6, 3.0, 5.4), v3(14.9, 1.7, -1.1)],
    [v3(13.2, 3.1, 6.8), v3(14, 2.1, 0)],
    [v3(15.5, 2.4, 4.0), v3(14, 1.55, 0.2)],
  ];
  const camPos = v3(0, 0, 0);
  const camTarget = v3(0, 0, 0);

  const qFlat = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI / 2, 0, 0));
  const qInBox = new THREE.Quaternion().setFromEuler(new THREE.Euler(0, 0, -Math.PI / 2));
  const HOME = v3(14, 3.1, 0);
  const PURGE = v3(15.35, 1.75, -1.5);
  const BRUSH = v3(12.9, 1.27, -1.6);

  const overlays = [...document.querySelectorAll('.ov')].map((el) => ({ el, from: +el.dataset.from, to: +el.dataset.to }));
  const chart = document.getElementById('chart');
  const chartSteps = [...chart.querySelectorAll('[data-at]')];
  const btnNow = document.getElementById('btn-now');
  const layerEl = document.getElementById('layer');
  const meterEl = document.getElementById('meter');
  const curve = setupChart();

  let pTarget = 0;
  let p = 0;
  let spin = 0;
  let last = performance.now();
  let visible = true;

  function readScroll() {
    const top = story.getBoundingClientRect().top;
    pTarget = Math.max(0, -top / window.innerHeight);
    visible = story.getBoundingClientRect().bottom > 0;
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

  function toolheadAt(t) {
    if (t < 6.4) return HOME.clone();
    if (t < 6.8) return HOME.clone().lerp(PURGE, span(t, 6.4, 6.8));
    if (t < 7.15) return PURGE.clone();
    if (t < 7.35) return PURGE.clone().lerp(BRUSH, span(t, 7.15, 7.35));
    if (t < 7.75) return BRUSH.clone().add(v3(0.25 * Math.sin(((t - 7.35) / 0.4) * Math.PI * 6), 0, 0));
    const firstLayer = v3(VASE.x + vaseRadius(0), BED_TOP + 0.01, VASE.z);
    if (t < 8.3) return BRUSH.clone().lerp(HOME, span(t, 7.75, 8.3));
    if (t < 8.6) return HOME.clone().lerp(firstLayer, span(t, 8.3, 8.6));
    const pr = printProgress(t);
    const y = VASE.height * pr;
    const a = pr * Math.PI * 2 * 18;
    return v3(VASE.x + vaseRadius(y) * Math.cos(a), BED_TOP + y + 0.01, VASE.z + vaseRadius(y) * Math.sin(a));
  }

  function printProgress(t) { return clamp01((t - 8.6) / 1.0); }

  function update(time, dt) {
    // camera: chain of lerps, each panel's pose blends in as its panel arrives
    camPos.copy(poses[0][0]);
    camTarget.copy(poses[0][1]);
    for (let i = 1; i < poses.length; i++) {
      const a = act(p, i);
      if (a <= 0) break;
      camPos.lerp(poses[i][0], a);
      camTarget.lerp(poses[i][1], a);
    }
    if (!reducedMotion && p < 1) {
      camPos.x += Math.sin(time * 0.25) * 0.15 * (1 - p);
      camPos.y += Math.sin(time * 0.31) * 0.08 * (1 - p);
    }
    // portrait screens see less width: step back so the subject still fits
    if (camera.aspect < 1.2) camPos.sub(camTarget).multiplyScalar(Math.pow(1.2 / camera.aspect, 0.75)).add(camTarget);
    camera.position.copy(camPos);
    camera.lookAt(camTarget);

    // spool spin settles so the tag faces the phone
    const settle = span(p, 1.3, 2.0);
    if (!reducedMotion) spin += dt * 0.5 * (1 - settle);
    const rest = Math.round(spin / (Math.PI * 2)) * Math.PI * 2;
    const feed = span(p, 6.15, 6.6) * Math.PI * 3;
    hero.body.rotation.y = lerp(spin, rest, settle) + feed;

    // tag flies onto the flange
    tag.visible = p > 1.3;
    tag.position.copy(TAG_FROM).lerp(TAG_HOME, span(p, 1.3, 1.95));
    tag.rotation.set(lerp(-1.2, 0, span(p, 1.3, 1.95)), 0, lerp(0.8, 0, span(p, 1.3, 1.95)));

    // phone appears, writes, leaves
    const phoneIn = span(p, 2.3, 2.95);
    const phoneOut = span(p, 3.3, 3.6);
    const phoneScale = phoneIn * (1 - phoneOut);
    phone.visible = phoneScale > 0.01;
    const tagWorld = tag.getWorldPosition(v3(0, 0, 0));
    phone.position.set(lerp(2.4, 1.6, phoneIn) + phoneOut * 1.5, lerp(0.6, 1.8, phoneIn) + phoneOut * 1.5, 0.85);
    phone.scale.setScalar(Math.max(phoneScale * 0.75, 0.001));
    phone.lookAt(tagWorld);
    const state = p < 2.6 ? 0 : p < 3.0 ? 1 : 2;
    if (state !== phoneState) { phoneState = state; drawPhone(state); }
    const writing = p > 2.6 && p < 3.15;
    waves.forEach((ring, k) => {
      const f = (time * 0.9 + k / 3) % 1;
      ring.visible = writing;
      ring.position.copy(phone.position).lerp(tagWorld, f);
      ring.lookAt(tagWorld);
      ring.scale.setScalar(1 + f * 1.4);
      ring.material.opacity = writing ? Math.sin(f * Math.PI) * 0.9 : 0;
    });
    coilMat.emissiveIntensity = writing ? 0.35 + 0.35 * Math.sin(time * 10) : 0;

    // into gate 1
    const a4 = act(p, 4);
    const over = clamp01(a4 / 0.75);
    const drop = clamp01((a4 - 0.75) / 0.25);
    let y = lerp(1, 3.3, smooth(over)) + Math.sin(over * Math.PI) * 1.3;
    y = lerp(y, SPOOL_IN_BOX_Y, smooth(drop));
    hero.group.position.set(lerp(0, GATE_X[1], smooth(over)), y, 0);
    hero.group.quaternion.copy(qFlat).slerp(qInBox, smooth(over));
    lidPivot.rotation.x = -1.15 * span(p, 3.35, 3.9);

    // the reader for gates 0-1 sees the tag, gate 1 lights up
    const reading = p > 4.15 && p < 5.2;
    readerMats[0].emissiveIntensity = reading ? 0.6 + 0.6 * Math.sin(time * 8) : 0.15;
    leds[1].material.emissive.setHex(p > 4.55 ? COLORS.green : 0x3a4060);

    // filament travels to the printer
    const filled = Math.floor(span(p, 6.15, 6.6) * TUBE_SEGMENTS);
    fill.geometry.setDrawRange(0, filled * 8 * 6);
    fill.visible = filled > 0;

    // toolhead, gantry, load cell sweep
    const tip = toolheadAt(p);
    toolhead.position.copy(tip);
    beamX.position.set(PRINTER_X, tip.y + 0.85, tip.z);
    railL.position.set(PRINTER_X - 1.7, tip.y + 0.85, 0);
    railR.position.set(PRINTER_X + 1.7, tip.y + 0.85, 0);
    const extruding = p > 6.8 && p < 7.15;
    strand.visible = extruding;
    strand.position.copy(tip);
    strand.scale.y = Math.max(0.001, span(p, 6.8, 7.05) * 0.5);
    loadRings.forEach((r, k) => {
      const f = (time * 1.2 + k / 2) % 1;
      r.scale.setScalar(1 + f * 1.6);
      r.material.opacity = extruding ? (1 - f) * 0.8 : 0;
    });

    // print
    const pr = printProgress(p);
    clip.constant = BED_TOP + VASE.height * pr;
    vase.visible = base.visible = pr > 0;

    // printer screen
    const screen = p < 5.55 ? 'idle' : p < 6.3 ? 'dialog' : p < 7.45 ? 'calib' : p < 8.6 ? 'saved' : 'print';
    const screenKey = screen + (screen === 'calib' ? Math.round(span(p, 6.5, 7.4) * 20) : screen === 'print' ? Math.round(pr * 40) : '');
    if (screenKey !== screenState) {
      screenState = screenKey;
      drawScreen(screen, screen === 'calib' ? span(p, 6.5, 7.4) : screen === 'print' ? pr : 1);
    }

    // overlays
    overlays.forEach((o) => o.el.classList.toggle('on', p >= o.from && p < o.to));
    btnNow.classList.toggle('pressed', p > 6.15);
    curve.reveal(span(p, 6.6, 7.05));
    chart.classList.toggle('done', p > 7.05);
    chartSteps.forEach((s) => s.classList.toggle('lit', p >= +s.dataset.at));
    const layer = Math.round(pr * LAYERS);
    layerEl.textContent = `layer ${layer} of ${LAYERS}`;
    meterEl.style.width = `${pr * 100}%`;
  }

  function frame(now) {
    const dt = Math.min(0.05, (now - last) / 1000);
    last = now;
    p = reducedMotion ? pTarget : p + (pTarget - p) * Math.min(1, dt * 7);
    if (visible) {
      update(now / 1000, dt);
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

// Pressure error for each K tried (example data with its minimum at 0.042)
function setupChart() {
  const ks = [];
  for (let k = 0.02; k <= 0.1201; k += 0.01) ks.push(k);
  const err = (k) => 0.12 + Math.pow((k - 0.042) / 0.078, 2) * 0.62 + Math.sin(k * 400) * 0.015;
  const x = (k) => 36 + ((k - 0.02) / 0.1) * 270;
  const y = (e) => 140 - Math.min(1, e) * 120;
  const pts = ks.map((k) => [x(k), y(err(k))]);
  const poly = document.getElementById('curve');
  poly.setAttribute('points', pts.map((pt) => pt.join(',')).join(' '));
  const dots = document.getElementById('dots');
  const dotEls = pts.map(([cx, cy]) => {
    const c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    c.setAttribute('cx', cx); c.setAttribute('cy', cy); c.setAttribute('r', 3.2);
    c.setAttribute('class', 'dot');
    c.style.opacity = 0;
    dots.appendChild(c);
    return c;
  });
  const best = document.getElementById('best');
  best.setAttribute('cx', x(0.042)); best.setAttribute('cy', y(err(0.042)));
  const label = document.getElementById('best-label');
  label.setAttribute('x', x(0.042) - 22); label.setAttribute('y', y(err(0.042)) - 14);
  const length = poly.getTotalLength ? poly.getTotalLength() : 600;
  poly.style.strokeDasharray = length;
  return {
    reveal(f) {
      poly.style.strokeDashoffset = length * (1 - f);
      dotEls.forEach((d, i) => { d.style.opacity = f * (ks.length - 1) >= i ? 1 : 0; });
    },
  };
}

if (renderer) start();
