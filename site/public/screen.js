// The printer's touchscreen in the 3D scene: an illustration of what HelixScreen shows
const HEX = { green: '#34c17b', yellow: '#f4c63d', red: '#ef5a4c', blue: '#4c8df6', pei: '#d4b06a', ink: '#0d1026', panel: '#1c2150', bar: '#262c66', text: '#eef0fa', muted: '#8f96c4' };
const GATES = [HEX.yellow, HEX.green, HEX.red, HEX.blue];

function bar(g, x, y, w, h, f, color) {
  g.fillStyle = HEX.bar;
  g.beginPath(); g.roundRect(x, y, w, h, h / 2); g.fill();
  g.fillStyle = color;
  g.beginPath(); g.roundRect(x, y, Math.max(h, w * f), h, h / 2); g.fill();
}

function gates(g, x, y, active, r = 26, gap = 72) {
  GATES.forEach((c, i) => {
    g.fillStyle = c;
    g.beginPath(); g.arc(x + i * gap, y, r, 0, Math.PI * 2); g.fill();
    if (i === active) {
      g.strokeStyle = HEX.text; g.lineWidth = 5;
      g.beginPath(); g.arc(x + i * gap, y, r + 8, 0, Math.PI * 2); g.stroke();
    }
  });
}

function helix(g) {
  g.fillStyle = HEX.panel;
  g.beginPath(); g.roundRect(20, 20, 230, 248, 18); g.roundRect(262, 20, 230, 120, 18); g.roundRect(262, 152, 230, 116, 18); g.fill();
  g.fillStyle = HEX.muted; g.font = '18px sans-serif';
  g.fillText('Nozzle', 40, 58); g.fillText('Bed', 40, 128); g.fillText('Box', 40, 198);
  g.fillStyle = HEX.text; g.font = 'bold 30px sans-serif';
  g.fillText('250 °C', 40, 94); g.fillText('75 °C', 40, 164); g.fillText('45 °C  22 %', 40, 234);
  g.fillStyle = HEX.muted; g.font = '18px sans-serif'; g.fillText('Printing', 282, 56);
  bar(g, 282, 80, 190, 18, 0.62, HEX.red);
  g.fillStyle = HEX.text; g.font = 'bold 22px sans-serif'; g.fillText('62 %   1 h 08', 282, 126);
  g.fillStyle = HEX.muted; g.font = '18px sans-serif'; g.fillText('Box', 282, 186);
  gates(g, 300, 228, 2, 16, 50);
}

export function drawScreen(screen, state, progress) {
  const g = screen.ctx;
  g.fillStyle = HEX.ink;
  g.fillRect(0, 0, 512, 288);
  if (state === 'helix') { helix(g); screen.tex.needsUpdate = true; return; }
  const titles = {
    convert: 'Converting', idle: 'Ready', dialog: 'New filament', calib: 'Measuring PA', saved: 'PA 0.042 saved',
    print: 'Printing', dry: 'Drying 45 °C', swap: progress ? 'Loading gate 2' : 'Unloading gate 1', paused: 'Paused',
  };
  g.fillStyle = state === 'paused' ? HEX.red : HEX.text;
  g.font = 'bold 30px sans-serif';
  g.fillText(titles[state], 32, 60);
  if (state === 'convert') {
    g.fillStyle = HEX.muted; g.font = '22px sans-serif';
    g.fillText('The installer is working', 32, 110);
  } else if (state === 'idle' || state === 'swap') {
    gates(g, 80, 170, state === 'swap' ? (progress ? 2 : 1) : -1, 36, 115);
  } else if (state === 'dialog') {
    g.fillStyle = HEX.pei; g.beginPath(); g.roundRect(32, 110, 448, 64, 14); g.fill();
    g.fillStyle = '#1b1606'; g.font = 'bold 26px sans-serif'; g.fillText('Calibrate now', 170, 152);
    g.fillStyle = HEX.bar; g.beginPath(); g.roundRect(32, 190, 216, 60, 14); g.roundRect(264, 190, 216, 60, 14); g.fill();
  } else if (state === 'paused') {
    g.fillStyle = HEX.muted; g.font = '22px sans-serif';
    g.fillText('Failure detection paused the print', 32, 110);
    g.fillStyle = HEX.bar; g.beginPath(); g.roundRect(32, 150, 216, 64, 14); g.roundRect(264, 150, 216, 64, 14); g.fill();
    g.fillStyle = HEX.text; g.font = 'bold 24px sans-serif'; g.fillText('Resume', 96, 191); g.fillText('Cancel', 330, 191);
  } else {
    const color = state === 'saved' ? HEX.pei : state === 'dry' ? '#ff7a2f' : HEX.green;
    bar(g, 32, 150, 448, 26, state === 'dry' ? 0.1 : progress, color);
  }
  screen.tex.needsUpdate = true;
}
