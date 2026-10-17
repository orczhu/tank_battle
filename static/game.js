// Tank Battle client: draws what the server sends and sends key presses back.
const FIELD = 208, HUD = 40, W = FIELD + HUD, H = 208, T = 8;
const canvas = document.getElementById('game');
const ctx = canvas.getContext('2d');
const who = document.getElementById('who');
ctx.scale(canvas.width / W, canvas.height / H);

let ws, mySlot = null, S = null, lastStage = 0, bannerUntil = 0;

// ---------- networking ----------
function connect() {
  ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.t === 'hello') {
      mySlot = m.slot;
      who.textContent = mySlot === null ? 'Watching (game is full)'
        : `You are Player ${mySlot + 1} — the ${mySlot === 0 ? 'YELLOW' : 'GREEN'} tank`;
      who.style.color = mySlot === 0 ? '#ffd23f' : mySlot === 1 ? '#5fdf5f' : '#ddd';
    } else if (m.t === 'state') {
      if (m.state === 'playing' && m.stage !== lastStage) bannerUntil = performance.now() + 2000;
      lastStage = m.state === 'playing' || m.state === 'stage_clear' ? m.stage : 0;
      m.events.forEach(play);
      S = m;
    }
  };
  ws.onclose = () => { S = null; who.textContent = 'Disconnected — reconnecting…'; setTimeout(connect, 2000); };
}
connect();

function send(obj) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); }

// ---------- input ----------
const DIR_KEYS = { ArrowUp: 0, KeyW: 0, ArrowRight: 1, KeyD: 1, ArrowDown: 2, KeyS: 2, ArrowLeft: 3, KeyA: 3 };
const FIRE_KEYS = new Set(['Space', 'KeyJ', 'KeyK']);
let held = [], fire = false, lastSent = '';

function sendInput() {
  const dir = held.length ? DIR_KEYS[held[held.length - 1]] : -1;
  const msg = JSON.stringify({ t: 'input', dir, fire });
  if (msg !== lastSent) { lastSent = msg; if (ws && ws.readyState === 1) ws.send(msg); }
}
addEventListener('keydown', (e) => {
  unlockAudio();
  if (e.code in DIR_KEYS) { held = held.filter((k) => k !== e.code); held.push(e.code); }
  else if (FIRE_KEYS.has(e.code)) fire = true;
  else if (e.code === 'Enter') send({ t: 'start' });
  else if (e.code === 'KeyM') muted = !muted;
  else return;
  e.preventDefault();
  sendInput();
});
addEventListener('keyup', (e) => {
  if (e.code in DIR_KEYS) held = held.filter((k) => k !== e.code);
  else if (FIRE_KEYS.has(e.code)) fire = false;
  else return;
  sendInput();
});
addEventListener('blur', () => { held = []; fire = false; sendInput(); });
setInterval(() => { lastSent = ''; sendInput(); }, 1000); // resend in case a message was missed

// ---------- sound ----------
let actx = null, muted = false;
function unlockAudio() {
  if (!actx) actx = new (window.AudioContext || window.webkitAudioContext)();
  if (actx.state === 'suspended') actx.resume();
}
function tone(freq, dur, type = 'square', vol = 0.06, endFreq = freq, delay = 0) {
  const t0 = actx.currentTime + delay, o = actx.createOscillator(), g = actx.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freq, t0);
  o.frequency.exponentialRampToValueAtTime(endFreq, t0 + dur);
  g.gain.setValueAtTime(vol, t0);
  g.gain.exponentialRampToValueAtTime(0.0001, t0 + dur);
  o.connect(g).connect(actx.destination);
  o.start(t0); o.stop(t0 + dur);
}
function noise(dur, vol) {
  const buf = actx.createBuffer(1, actx.sampleRate * dur, actx.sampleRate), d = buf.getChannelData(0);
  for (let i = 0; i < d.length; i++) d[i] = (Math.random() * 2 - 1) * (1 - i / d.length) ** 2;
  const src = actx.createBufferSource(), g = actx.createGain();
  g.gain.value = vol;
  src.buffer = buf;
  src.connect(g).connect(actx.destination);
  src.start();
}
function play(ev) {
  if (!actx || muted) return;
  switch (ev) {
    case 'fire': tone(700, 0.08, 'square', 0.04, 300); break;
    case 'brick': noise(0.1, 0.25); break;
    case 'steel': tone(180, 0.06, 'triangle', 0.1, 120); break;
    case 'armor': tone(1400, 0.05, 'square', 0.04); break;
    case 'explode': noise(0.45, 0.5); break;
    case 'bonus': tone(1000, 0.08, 'square', 0.04, 1500); break;
    case 'powerup': [523, 659, 784, 1047].forEach((f, i) => tone(f, 0.1, 'square', 0.05, f, i * 0.07)); break;
    case 'clear': [523, 659, 784, 1047, 784, 1047].forEach((f, i) => tone(f, 0.15, 'square', 0.05, f, i * 0.12)); break;
    case 'gameover': [392, 330, 262, 196].forEach((f, i) => tone(f, 0.3, 'triangle', 0.1, f, i * 0.25)); break;
  }
}

// ---------- drawing ----------
const TANK_COLORS = {
  p1: ['#e7b800', '#7a5c00', '#ffe680'],
  p2: ['#3fbf3f', '#1b5e1b', '#a6f5a6'],
  basic: ['#bcbcbc', '#555', '#fff'],
  fast: ['#8fc8ff', '#2d5f8f', '#e0f0ff'],
  power: ['#ff9a4a', '#8a4210', '#ffd8b0'],
};
const ARMOR_COLORS = { 4: ['#c050d0', '#5a1f66', '#f0c0ff'], 3: ['#e07070', '#6e2424', '#ffd0d0'],
  2: ['#e0c070', '#6e5a24', '#fff0c0'], 1: ['#bcbcbc', '#555', '#fff'] };
const POWER_ICONS = { star: '⭐', grenade: '💣', helmet: '🛡️', shovel: '🏰', timer: '⏰', tank: '❤️' };

function drawTile(ch, x, y, tick) {
  if (ch === '#') {
    ctx.fillStyle = '#a0461e'; ctx.fillRect(x, y, 8, 8);
    ctx.fillStyle = '#5a2a14';
    ctx.fillRect(x, y + 3, 8, 1); ctx.fillRect(x, y + 7, 8, 1);
    ctx.fillRect(x + 3, y, 1, 3); ctx.fillRect(x + 7, y + 4, 1, 3);
  } else if (ch === '@') {
    ctx.fillStyle = '#7c7c7c'; ctx.fillRect(x, y, 8, 8);
    ctx.fillStyle = '#d8d8d8'; ctx.fillRect(x, y, 7, 7);
    ctx.fillStyle = '#fff'; ctx.fillRect(x + 2, y + 2, 3, 3);
  } else if (ch === '~') {
    ctx.fillStyle = '#2038ec'; ctx.fillRect(x, y, 8, 8);
    ctx.fillStyle = '#6cb8ff';
    const o = (Math.floor(tick / 30) + x / 8 + y / 8) % 2 ? 0 : 3;
    ctx.fillRect(x + o, y + 2, 3, 1); ctx.fillRect(x + 4 - o, y + 6, 3, 1);
  }
}
function drawTrees(x, y) {
  ctx.fillStyle = '#0a7a0a'; ctx.fillRect(x, y, 8, 8);
  ctx.fillStyle = '#84d42a';
  ctx.fillRect(x + 1, y + 1, 2, 2); ctx.fillRect(x + 5, y + 2, 2, 2); ctx.fillRect(x + 2, y + 5, 2, 2);
  ctx.fillStyle = '#044a04'; ctx.fillRect(x + 5, y + 5, 2, 2);
}

function drawBase(alive) {
  const x = 96, y = 192;
  if (!alive) {
    ctx.fillStyle = '#555'; ctx.fillRect(x + 2, y + 9, 12, 7);
    ctx.fillStyle = '#333'; ctx.fillRect(x + 4, y + 6, 3, 4); ctx.fillRect(x + 9, y + 7, 4, 3);
    return;
  }
  // a little eagle
  ctx.fillStyle = '#9a9a9a';
  ctx.beginPath();
  ctx.moveTo(x + 8, y + 2); ctx.lineTo(x + 15, y + 6); ctx.lineTo(x + 12, y + 11);
  ctx.lineTo(x + 8, y + 9); ctx.lineTo(x + 4, y + 11); ctx.lineTo(x + 1, y + 6); ctx.closePath(); ctx.fill();
  ctx.fillStyle = '#ddd'; ctx.fillRect(x + 7, y + 1, 3, 4);
  ctx.fillStyle = '#e04020'; ctx.fillRect(x + 9, y + 2, 2, 1);
  ctx.fillStyle = '#9a9a9a'; ctx.fillRect(x + 6, y + 9, 4, 5); ctx.fillRect(x + 4, y + 14, 8, 2);
}

function drawTank(t, tick) {
  const [x, y, dir, kind, hp, level, flags] = t;
  if (flags & 8) { // spawning sparkle
    const s = 3 + 4 * Math.abs(Math.sin(tick / 6));
    ctx.fillStyle = '#fff';
    ctx.beginPath();
    ctx.moveTo(x + 8, y + 8 - s); ctx.lineTo(x + 9, y + 7); ctx.lineTo(x + 8 + s, y + 8); ctx.lineTo(x + 9, y + 9);
    ctx.lineTo(x + 8, y + 8 + s); ctx.lineTo(x + 7, y + 9); ctx.lineTo(x + 8 - s, y + 8); ctx.lineTo(x + 7, y + 7);
    ctx.fill();
    return;
  }
  if ((flags & 2) && Math.floor(tick / 6) % 2) return; // frozen by sibling: blink
  let [main, dark, light] = kind === 'armor' ? ARMOR_COLORS[hp] || ARMOR_COLORS[1] : TANK_COLORS[kind];
  if ((flags & 4) && Math.floor(tick / 8) % 2) [main, dark, light] = ['#e03030', '#701010', '#ffb0b0'];

  ctx.save();
  ctx.translate(x + 8, y + 8);
  ctx.rotate(dir * Math.PI / 2);
  // treads
  ctx.fillStyle = dark; ctx.fillRect(-8, -7, 4, 15); ctx.fillRect(4, -7, 4, 15);
  ctx.fillStyle = light;
  for (let i = -6; i < 8; i += 3) { ctx.fillRect(-8, i, 4, 1); ctx.fillRect(4, i, 4, 1); }
  // body
  ctx.fillStyle = main; ctx.fillRect(-4, -5, 8, 12);
  // turret + barrel (players' barrel grows with stars)
  const bw = kind === 'power' || level >= 2 ? 3 : 2, blen = kind === 'fast' || level >= 1 ? 10 : 8;
  ctx.fillStyle = light; ctx.fillRect(-bw / 2, -blen, bw, blen);
  if (level >= 3) { ctx.fillRect(-3, -blen + 1, 1.5, blen - 1); ctx.fillRect(1.5, -blen + 1, 1.5, blen - 1); }
  ctx.fillStyle = dark; ctx.beginPath(); ctx.arc(0, 1, kind === 'armor' ? 4.5 : 3.5, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = main; ctx.beginPath(); ctx.arc(0, 1, kind === 'armor' ? 3.2 : 2.3, 0, Math.PI * 2); ctx.fill();
  ctx.restore();

  if (flags & 1) { // shield bubble
    ctx.strokeStyle = Math.floor(tick / 4) % 2 ? '#fff' : '#6cf';
    ctx.lineWidth = 1;
    ctx.setLineDash([2, 2]); ctx.lineDashOffset = tick % 4;
    ctx.beginPath(); ctx.arc(x + 8, y + 8, 10, 0, Math.PI * 2); ctx.stroke();
    ctx.setLineDash([]);
  }
}

function drawExplosion([x, y, big, age]) {
  const max = big ? 30 : 15, p = age / max, r = (big ? 13 : 6) * Math.sin(Math.PI * Math.min(1, p * 1.3));
  if (r <= 0) return;
  ctx.fillStyle = '#c01818'; ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#ff9a20'; ctx.beginPath(); ctx.arc(x, y, r * 0.7, 0, Math.PI * 2); ctx.fill();
  ctx.fillStyle = '#fff6a0'; ctx.beginPath(); ctx.arc(x, y, r * 0.35, 0, Math.PI * 2); ctx.fill();
}

function drawHud() {
  ctx.fillStyle = '#636363'; ctx.fillRect(FIELD, 0, HUD, H);
  // remaining enemies
  ctx.fillStyle = '#222';
  for (let i = 0; i < S.left; i++) ctx.fillRect(FIELD + 10 + (i % 2) * 10, 8 + Math.floor(i / 2) * 8, 6, 6);
  ctx.font = 'bold 7px monospace'; ctx.textBaseline = 'top';
  S.players.forEach((p, i) => {
    const y = 104 + i * 34;
    ctx.fillStyle = i === 0 ? '#ffd23f' : '#5fdf5f';
    ctx.fillText(`${i + 1}P${mySlot === i ? ' ◀' : ''}`, FIELD + 4, y);
    ctx.fillStyle = '#111';
    if (p) {
      ctx.fillText(`♥ ${Math.max(0, p.lives)}`, FIELD + 4, y + 9);
      ctx.fillText(`${p.score}`, FIELD + 4, y + 18);
    } else ctx.fillText('—', FIELD + 4, y + 9);
  });
  ctx.fillStyle = '#111';
  ctx.fillText('STAGE', FIELD + 4, 178);
  ctx.font = 'bold 10px monospace';
  ctx.fillText(`${S.stage}`, FIELD + 4, 188);
}

function overlay(lines) {
  ctx.fillStyle = 'rgba(0,0,0,0.75)'; ctx.fillRect(0, 0, FIELD, H);
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  let y = H / 2 - (lines.length - 1) * 7;
  for (const [text, size, color] of lines) {
    ctx.font = `bold ${size}px monospace`; ctx.fillStyle = color;
    ctx.fillText(text, FIELD / 2, y);
    y += Math.max(14, size + 4);
  }
  ctx.textAlign = 'left';
}

function scoreLines() {
  return S.players.map((p, i) => p ? [`Player ${i + 1}: ${p.score}`, 9, i === 0 ? '#ffd23f' : '#5fdf5f'] : null).filter(Boolean);
}

function render() {
  requestAnimationFrame(render);
  ctx.fillStyle = '#000'; ctx.fillRect(0, 0, W, H);
  if (!S) {
    ctx.fillStyle = '#fff'; ctx.font = 'bold 10px monospace'; ctx.textAlign = 'center';
    ctx.fillText('Connecting to server…', W / 2, H / 2); ctx.textAlign = 'left';
    return;
  }
  const tick = S.tick, map = S.map;
  for (let r = 0; r < 26; r++) for (let c = 0; c < 26; c++) drawTile(map[r * 26 + c], c * T, r * T, tick);
  drawBase(S.base);
  if (S.powerup && (S.powerup[3] > 300 || Math.floor(tick / 10) % 2)) {
    const [px, py, kind] = S.powerup;
    ctx.fillStyle = '#fff'; ctx.fillRect(px, py, 16, 16);
    ctx.fillStyle = '#203080'; ctx.fillRect(px + 1, py + 1, 14, 14);
    ctx.font = '11px sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(POWER_ICONS[kind], px + 8, py + 9); ctx.textAlign = 'left';
  }
  S.tanks.forEach((t) => drawTank(t, tick));
  ctx.fillStyle = '#fff';
  S.bullets.forEach(([x, y]) => ctx.fillRect(x - 1.5, y - 1.5, 3, 3));
  for (let r = 0; r < 26; r++) for (let c = 0; c < 26; c++) if (map[r * 26 + c] === '%') drawTrees(c * T, r * T);
  S.boom.forEach(drawExplosion);
  drawHud();

  if (S.state === 'lobby') {
    overlay([
      ['TANK BATTLE', 18, '#ff7a30'],
      ['', 6, '#fff'],
      [`Player 1 (yellow): ${S.conn[0] ? 'ready ✔' : 'waiting…'}`, 8, '#ffd23f'],
      [`Player 2 (green):  ${S.conn[1] ? 'ready ✔' : 'waiting…'}`, 8, '#5fdf5f'],
      ['', 6, '#fff'],
      ['Protect the eagle! 🦅', 8, '#fff'],
      ['Press ENTER to start', 10, '#fff'],
    ]);
  } else if (S.state === 'gameover') {
    overlay([['GAME OVER', 20, '#e03030'], ...scoreLines(), ['Press ENTER to play again', 9, '#fff']]);
  } else if (S.state === 'stage_clear') {
    overlay([[`STAGE ${S.stage} CLEAR!`, 16, '#ffd23f'], ...scoreLines()]);
  } else if (performance.now() < bannerUntil) {
    ctx.fillStyle = 'rgba(0,0,0,0.6)'; ctx.fillRect(0, H / 2 - 14, FIELD, 28);
    ctx.fillStyle = '#fff'; ctx.font = 'bold 14px monospace'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.fillText(`STAGE ${S.stage}`, FIELD / 2, H / 2); ctx.textAlign = 'left';
  }
}
render();
