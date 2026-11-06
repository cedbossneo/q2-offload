// The objects of the scene: spools, phone, Box, printer, host, cables. No animation here.
import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

export const COLORS = {
  green: 0x34c17b, yellow: 0xf4c63d, red: 0xef5a4c, blue: 0x4c8df6,
  shell: 0x2b3042, trim: 0x3b4258, pei: 0xd4b06a, heat: 0xff7a2f,
};
export const GATE_X = [5.5, 6.5, 7.5, 8.5];
export const GATE_COLORS = [COLORS.yellow, COLORS.green, COLORS.red, COLORS.blue];
export const SPOOL_IN_BOX_Y = 1.12;
export const PRINTER_X = 14;
export const BED_TOP = 1.03;
export const VASE = { x: 14, z: 0.2, height: 1.25 };
export const HOST_POS = new THREE.Vector3(18.7, 0, 1.3);
export const v3 = (x, y, z) => new THREE.Vector3(x, y, z);

export function canvasTexture(w, h, draw = () => {}) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  const ctx = c.getContext('2d');
  draw(ctx, w, h);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 8;
  return { tex, ctx };
}

const ringProfile = (r0, r1, h) => [
  new THREE.Vector2(r0, -h / 2), new THREE.Vector2(r1, -h / 2), new THREE.Vector2(r1, h / 2),
  new THREE.Vector2(r0, h / 2), new THREE.Vector2(r0, -h / 2)];

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

export function rbox(parent, w, h, d, x, y, z, mat, radius = 0.04) {
  const m = new THREE.Mesh(new RoundedBoxGeometry(w, h, d, 3, radius), mat);
  m.position.set(x, y, z);
  m.castShadow = m.receiveShadow = true;
  parent.add(m);
  return m;
}

export function makeSpool(color) {
  const group = new THREE.Group();
  const body = new THREE.Group(); // spool axis = local Y
  group.add(body);
  const flangeMat = new THREE.MeshPhysicalMaterial({ color: 0x8a93c8, roughness: 0.15, transparent: true, opacity: 0.34, depthWrite: false, clearcoat: 0.7 });
  for (const side of [-1, 1]) {
    const flange = new THREE.Mesh(new THREE.LatheGeometry(ringProfile(0.24, 1, 0.05), 96), flangeMat);
    flange.position.y = side * 0.35;
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

export function makeTag() {
  const white = new THREE.MeshStandardMaterial({ color: 0xf2f3fa, roughness: 0.6 });
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
  const mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.17, 0.17, 0.012, 48), [white, coilMat, white]);
  mesh.castShadow = true;
  return { mesh, coilMat };
}

export function makePhone() {
  const group = new THREE.Group();
  group.add(new THREE.Mesh(new RoundedBoxGeometry(0.56, 1.12, 0.07, 4, 0.07),
    new THREE.MeshPhysicalMaterial({ color: 0x232838, roughness: 0.3, metalness: 0.6, clearcoat: 1 })));
  const screen = canvasTexture(256, 512);
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(0.5, 1.04), new THREE.MeshBasicMaterial({ map: screen.tex, toneMapped: false }));
  plane.rotation.y = Math.PI; // the back of the phone faces the tag
  plane.position.z = -0.037;
  group.add(plane);
  function draw(state) {
    const g = screen.ctx;
    g.fillStyle = '#0f1229';
    g.fillRect(0, 0, 256, 512);
    g.fillStyle = '#eef0fa';
    g.font = 'bold 22px sans-serif';
    g.fillText('Write NFC tag', 24, 60);
    g.font = '17px sans-serif';
    [['Brand', 'Sunlu'], ['Material', 'PETG'], ['Nozzle', '230-255 °C'], ['Bed', '70-80 °C']].forEach(([k, v], i) => {
      const y = 112 + i * 52;
      g.fillStyle = '#8f96c4'; g.fillText(k, 24, y);
      g.fillStyle = '#eef0fa'; g.fillText(v, 130, y);
    });
    g.fillStyle = '#8f96c4'; g.fillText('Colour', 24, 320);
    g.fillStyle = '#34c17b'; g.beginPath(); g.arc(148, 314, 14, 0, Math.PI * 2); g.fill();
    if (state === 2) {
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
    screen.tex.needsUpdate = true;
  }
  return { group, draw };
}

// A small board with its MCU and a status ring, shown when the shells turn see-through
export function makeChip() {
  const group = new THREE.Group();
  group.add(new THREE.Mesh(new THREE.BoxGeometry(0.42, 0.03, 0.3), new THREE.MeshStandardMaterial({ color: 0x1f6b45, roughness: 0.5 })));
  const ic = new THREE.Mesh(new THREE.BoxGeometry(0.13, 0.03, 0.13), new THREE.MeshStandardMaterial({ color: 0x111318, roughness: 0.4 }));
  ic.position.y = 0.03;
  group.add(ic);
  const ringMat = new THREE.MeshBasicMaterial({ color: 0x5a6290, transparent: true, opacity: 0.9, toneMapped: false });
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.3, 0.018, 8, 64), ringMat);
  ring.rotation.x = Math.PI / 2;
  ring.position.y = 0.05;
  group.add(ring);
  return { group, ringMat };
}

export function makeBox(scene) {
  const box = new THREE.Group();
  box.position.set(7, 0, 0);
  scene.add(box);
  const shellMat = new THREE.MeshStandardMaterial({ color: COLORS.shell, roughness: 0.55, metalness: 0.15 });
  const trimMat = new THREE.MeshStandardMaterial({ color: COLORS.trim, roughness: 0.45, metalness: 0.2 });
  rbox(box, 4.7, 0.14, 2.3, 0, 0.07, 0, shellMat);
  rbox(box, 4.7, 1.7, 0.1, 0, 0.85, -1.1, shellMat);
  rbox(box, 0.12, 1.7, 2.3, -2.3, 0.85, 0, shellMat);
  rbox(box, 0.12, 1.7, 2.3, 2.3, 0.85, 0, shellMat);
  rbox(box, 4.7, 0.75, 0.12, 0, 0.375, 1.1, trimMat);
  for (const z of [-0.55, 0.55]) {
    const roller = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 4.4, 24), trimMat);
    roller.rotation.z = Math.PI / 2;
    roller.position.set(0, 0.2, z);
    box.add(roller);
  }
  // two NFC readers: gates 0-1 and gates 2-3
  const readerMats = [0, 1].map(() => new THREE.MeshStandardMaterial({ color: 0x1b2a3a, emissive: COLORS.pei, emissiveIntensity: 0.15 }));
  [-1, 1].forEach((x, i) => rbox(box, 0.5, 0.04, 0.5, x, 0.16, 0.75, readerMats[i], 0.01));
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
  const chip = makeChip();
  chip.group.position.set(1.85, 0.2, -0.85);
  box.add(chip.group);
  // heater glow and rising warm air while drying
  const heatLight = new THREE.PointLight(COLORS.heat, 0, 6, 1.5);
  heatLight.position.set(0, 0.6, 0);
  box.add(heatLight);
  const count = 160;
  const pos = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    pos[i * 3] = (Math.random() - 0.5) * 4.3;
    pos[i * 3 + 1] = Math.random() * 1.6;
    pos[i * 3 + 2] = (Math.random() - 0.5) * 2;
  }
  const heatGeo = new THREE.BufferGeometry();
  heatGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const heatMat = new THREE.PointsMaterial({ color: COLORS.heat, size: 0.11, transparent: true, opacity: 0, depthWrite: false, toneMapped: false });
  const heat = new THREE.Points(heatGeo, heatMat);
  box.add(heat);
  const spools = [];
  GATE_COLORS.forEach((color, gate) => {
    if (gate === 1) return; // gate 1 is the new spool
    const s = makeSpool(color);
    s.group.position.set(GATE_X[gate], SPOOL_IN_BOX_Y, 0);
    s.group.rotation.z = -Math.PI / 2;
    s.body.rotation.y = gate * 1.3;
    scene.add(s.group);
    leds[gate].material.emissive.setHex(color);
    spools[gate] = s;
  });
  return { box, shellMat, trimMat, readerMats, leds, lidPivot, chip, heatLight, heat, heatMat, spools };
}

export function makePrinter(scene) {
  const printer = new THREE.Group();
  printer.position.set(PRINTER_X, 0, 0);
  scene.add(printer);
  const frameMat = new THREE.MeshStandardMaterial({ color: 0x252a3b, roughness: 0.5, metalness: 0.3 });
  const panelMat = new THREE.MeshStandardMaterial({ color: 0x2d3346, roughness: 0.65, side: THREE.DoubleSide });
  rbox(printer, 3.7, 0.75, 3.6, 0, 0.375, 0, frameMat);
  rbox(printer, 3.7, 0.1, 3.6, 0, 4.25, 0, frameMat);
  rbox(printer, 0.08, 3.5, 3.6, -1.81, 2.5, 0, panelMat, 0.02);
  rbox(printer, 0.08, 3.5, 3.6, 1.81, 2.5, 0, panelMat, 0.02);
  rbox(printer, 3.7, 3.5, 0.08, 0, 2.5, -1.76, panelMat, 0.02);
  for (const x of [-1.8, 1.8]) for (const z of [-1.75, 1.75]) rbox(printer, 0.14, 4.3, 0.14, x, 2.15, z, frameMat, 0.03);
  const pei = canvasTexture(256, 256, (g) => {
    g.fillStyle = '#c9a35e';
    g.fillRect(0, 0, 256, 256);
    for (let i = 0; i < 6000; i++) {
      g.fillStyle = Math.random() > 0.5 ? 'rgba(255,240,200,0.18)' : 'rgba(90,60,20,0.18)';
      g.fillRect(Math.random() * 256, Math.random() * 256, 1.5, 1.5);
    }
  });
  rbox(printer, 2.9, 0.12, 2.9, 0, 0.93, 0, frameMat, 0.02);
  const bed = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.04, 2.8), new THREE.MeshStandardMaterial({ map: pei.tex, roughness: 0.55, metalness: 0.35 }));
  bed.position.set(0, 1.01, 0);
  bed.receiveShadow = true;
  printer.add(bed);
  rbox(printer, 0.5, 0.6, 0.4, 1.35, 1.2, -1.5, frameMat); // purge chute
  rbox(printer, 0.6, 0.18, 0.2, -1.1, 1.12, -1.6, new THREE.MeshStandardMaterial({ color: 0x15171f, roughness: 1 }), 0.02); // wipe brush
  const chip = makeChip();
  chip.group.position.set(-0.6, 0.45, 0.6);
  printer.add(chip.group);
  // the chamber camera, top front, and what it sees
  rbox(printer, 0.3, 0.16, 0.16, 0, 4.1, 1.6, new THREE.MeshStandardMaterial({ color: 0x15171f, roughness: 0.4 }), 0.03);
  const lens = new THREE.Mesh(new THREE.CircleGeometry(0.05, 24), new THREE.MeshBasicMaterial({ color: 0x4c8df6, toneMapped: false }));
  lens.position.set(0, 4.06, 1.52);
  lens.rotation.x = Math.PI * 0.8;
  printer.add(lens);
  const coneMat = new THREE.MeshBasicMaterial({ color: COLORS.blue, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide, toneMapped: false });
  const cone = new THREE.Mesh(new THREE.ConeGeometry(1.5, 3.1, 4, 1, true), coneMat);
  cone.position.set(0, 2.5, 0.4);
  cone.rotation.set(0.42, Math.PI / 4, 0);
  printer.add(cone);

  const screen = canvasTexture(512, 288);
  const plane = new THREE.Mesh(new THREE.PlaneGeometry(0.96, 0.54), new THREE.MeshBasicMaterial({ map: screen.tex, toneMapped: false }));
  plane.position.set(0.9, 0.4, 1.805);
  printer.add(plane);
  return { printer, frameMat, panelMat, chip, coneMat, screen };
}

export function makeToolhead(scene) {
  const toolhead = new THREE.Group();
  scene.add(toolhead);
  const bodyMat = new THREE.MeshStandardMaterial({ color: 0x30364a, roughness: 0.4, metalness: 0.4 });
  rbox(toolhead, 0.55, 0.55, 0.5, 0, 0.42, 0, bodyMat, 0.06);
  rbox(toolhead, 0.56, 0.08, 0.51, 0, 0.62, 0, new THREE.MeshStandardMaterial({ color: COLORS.pei, roughness: 0.35, metalness: 0.6 }), 0.02);
  const nozzle = new THREE.Mesh(new THREE.ConeGeometry(0.07, 0.15, 24), new THREE.MeshStandardMaterial({ color: 0xc9a35e, roughness: 0.25, metalness: 0.9 }));
  nozzle.rotation.x = Math.PI;
  nozzle.position.y = 0.075;
  toolhead.add(nozzle);
  const chip = makeChip();
  chip.group.scale.setScalar(0.8);
  chip.group.position.set(0, 0.42, 0);
  toolhead.add(chip.group);
  const loadRings = [0, 1].map(() => {
    const r = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.008, 8, 48),
      new THREE.MeshBasicMaterial({ color: COLORS.green, transparent: true, opacity: 0, toneMapped: false }));
    r.rotation.x = Math.PI / 2;
    toolhead.add(r);
    return r;
  });
  const strandMat = new THREE.MeshStandardMaterial({ color: COLORS.green, roughness: 0.3 });
  const strand = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 1, 12), strandMat);
  strand.geometry.translate(0, -0.5, 0);
  scene.add(strand);
  const gantryMat = new THREE.MeshStandardMaterial({ color: 0x1e2232, roughness: 0.35, metalness: 0.7 });
  const beamX = new THREE.Mesh(new THREE.BoxGeometry(3.5, 0.1, 0.12), gantryMat);
  const railL = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.1, 3.4), gantryMat);
  const railR = railL.clone();
  scene.add(beamX, railL, railR);
  return { toolhead, bodyMat, chip, loadRings, strand, strandMat, beamX, railL, railR };
}

export function makeHost(scene) {
  const group = new THREE.Group();
  group.position.copy(HOST_POS);
  scene.add(group);
  rbox(group, 1.3, 0.42, 1.3, 0, 0.21, 0, new THREE.MeshStandardMaterial({ color: 0x6b7290, roughness: 0.35, metalness: 0.8 }), 0.12);
  const ledMat = new THREE.MeshBasicMaterial({ color: COLORS.pei, toneMapped: false });
  const led = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.025, 0.02), ledMat);
  led.position.set(0, 0.12, 0.655);
  group.add(led);
  return { group, ledMat };
}

// A tube along a curve, plus a coloured core that can be drawn partially
export function makeTube(scene, points, { segments = 120, core = null, sheath = true, radius = 0.05 } = {}) {
  const curve = new THREE.CatmullRomCurve3(points);
  const out = { curve, segments };
  if (sheath) {
    out.sheath = new THREE.Mesh(new THREE.TubeGeometry(curve, segments, radius, 12),
      new THREE.MeshPhysicalMaterial({ color: 0xffffff, roughness: 0.2, transparent: true, opacity: 0.28, depthWrite: false }));
    scene.add(out.sheath);
  }
  if (core !== null) {
    out.cores = {};
    for (const color of [].concat(core)) {
      const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, segments, radius * 0.52, 8),
        new THREE.MeshStandardMaterial({ color, roughness: 0.3, emissive: color, emissiveIntensity: 0.25 }));
      mesh.visible = false;
      scene.add(mesh);
      out.cores[color] = mesh;
    }
  }
  out.fill = (color, f) => {
    const mesh = out.cores[color];
    const n = Math.floor(Math.min(1, Math.max(0, f)) * segments);
    mesh.visible = n > 0;
    mesh.geometry.setDrawRange(0, n * 8 * 6);
  };
  return out;
}

export function makeCable(scene, points, color = 0x15182a) {
  const curve = new THREE.CatmullRomCurve3(points);
  const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, 80, 0.035, 8), new THREE.MeshStandardMaterial({ color, roughness: 0.6 }));
  mesh.castShadow = true;
  scene.add(mesh);
  return { curve, mesh };
}

export function makePackets(scene, curve, colors, count = 9) {
  return Array.from({ length: count }, (_, i) => {
    const m = new THREE.Mesh(new THREE.SphereGeometry(0.06, 12, 12),
      new THREE.MeshBasicMaterial({ color: colors[i % colors.length], transparent: true, opacity: 0, toneMapped: false }));
    scene.add(m);
    return { m, curve, offset: i / count, dir: i % 2 ? -1 : 1 };
  });
}

// A failed print: a tangle of filament next to the vase, revealed by draw range
export function makeSpaghetti(scene, color) {
  let seed = 7;
  const rand = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const pts = [];
  let x = 13.2;
  let z = -0.5;
  for (let i = 0; i < 70; i++) {
    x += (rand() - 0.5) * 0.5;
    z += (rand() - 0.5) * 0.5;
    x = Math.min(13.75, Math.max(12.45, x));
    z = Math.min(0.3, Math.max(-1.1, z));
    pts.push(v3(x, BED_TOP + 0.03 + rand() * 0.55, z));
  }
  const curve = new THREE.CatmullRomCurve3(pts);
  const segments = 600;
  const mesh = new THREE.Mesh(new THREE.TubeGeometry(curve, segments, 0.034, 6), new THREE.MeshStandardMaterial({ color, roughness: 0.35 }));
  mesh.castShadow = true;
  scene.add(mesh);
  return { mesh, reveal: (f) => { mesh.visible = f > 0; mesh.geometry.setDrawRange(0, Math.floor(f * segments) * 6 * 6); } };
}
