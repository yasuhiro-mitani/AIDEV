const KEY = 'dateCountdown.state';
const DATETIME_SUPPORTED = (() => {
  const input = document.createElement('input');
  input.setAttribute('type', 'datetime-local');
  return input.type === 'datetime-local';
})();

const els = {
  form: document.getElementById('setup'),
  title: document.getElementById('title'),
  target: document.getElementById('target'),
  reset: document.getElementById('reset'),
  display: document.getElementById('display'),
  eventName: document.getElementById('eventName'),
  eventTime: document.getElementById('eventTime'),
  days: document.getElementById('days'),
  hours: document.getElementById('hours'),
  mins: document.getElementById('mins'),
  secs: document.getElementById('secs'),
  done: document.getElementById('done')
};

let state = null; // { title: string, targetMs: number }
let timerId = null;
let notified = false;

function toLocalDateTimeValue(ms) {
  const d = new Date(ms);
  const pad = (n) => String(n).padStart(2, '0');
  const y = d.getFullYear();
  const m = pad(d.getMonth() + 1);
  const day = pad(d.getDate());
  const h = pad(d.getHours());
  const min = pad(d.getMinutes());
  return `${y}-${m}-${day}T${h}:${min}`;
}

function parseLocalDateTimeString(str) {
  if (!str) return NaN;
  const s = String(str).trim();
  // Accept: YYYY-MM-DDTHH:mm[:ss] or YYYY-MM-DD HH:mm[:ss]
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::(\d{2}))?$/);
  if (m) {
    const [_, yy, MM, dd, hh, mm, ss] = m;
    const date = new Date(
      Number(yy),
      Number(MM) - 1,
      Number(dd),
      Number(hh),
      Number(mm),
      ss ? Number(ss) : 0,
      0
    );
    return date.getTime();
  }
  // Accept: YYYY-MM-DD (midnight)
  const dOnly = s.match(/^(\d{4})-(\d{2})-(\d{2})$/);
  if (dOnly) {
    const [_, yy, MM, dd] = dOnly;
    const date = new Date(Number(yy), Number(MM) - 1, Number(dd), 0, 0, 0, 0);
    return date.getTime();
  }
  return NaN;
}

function loadState() {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed.targetMs !== 'number') return null;
    return parsed;
  } catch {
    return null;
  }
}

function saveState(s) {
  try { localStorage.setItem(KEY, JSON.stringify(s)); } catch {}
}

function clearState() {
  try { localStorage.removeItem(KEY); } catch {}
}

function setHidden(el, hidden) { el.hidden = !!hidden; }

function renderDigits(msRemaining) {
  const totalSec = Math.max(0, Math.floor(msRemaining / 1000));
  const days = Math.floor(totalSec / 86400);
  const hours = Math.floor((totalSec % 86400) / 3600);
  const mins = Math.floor((totalSec % 3600) / 60);
  const secs = totalSec % 60;
  els.days.textContent = String(days);
  els.hours.textContent = String(hours).padStart(2, '0');
  els.mins.textContent = String(mins).padStart(2, '0');
  els.secs.textContent = String(secs).padStart(2, '0');
}

function updateEventMeta() {
  if (!state) return;
  els.eventName.textContent = state.title || 'イベント';
  const dt = new Date(state.targetMs);
  els.eventTime.setAttribute('datetime', dt.toISOString());
  try {
    els.eventTime.textContent = dt.toLocaleString('ja-JP', { dateStyle: 'full', timeStyle: 'short' });
  } catch {
    els.eventTime.textContent = dt.toLocaleString();
  }
}

function stopTimer() {
  if (timerId) {
    clearInterval(timerId);
    timerId = null;
  }
}

function tick() {
  if (!state) return;
  const now = Date.now();
  const diff = state.targetMs - now;
  renderDigits(diff);
  const reached = diff <= 0;
  setHidden(els.done, !reached);
  if (reached) {
    if (!notified) {
      notified = true;
      notifyReached();
    }
    stopTimer();
  }
}

function startTimer() {
  stopTimer();
  tick();
  timerId = setInterval(tick, 1000);
}

function applyState(newState) {
  state = newState;
  if (state) {
    saveState(state);
    updateEventMeta();
    setHidden(els.display, false);
    startTimer();
  } else {
    clearState();
    stopTimer();
    setHidden(els.display, true);
    setHidden(els.done, true);
    renderDigits(0);
  }
}

function init() {
  // Configure input based on support
  if (DATETIME_SUPPORTED) {
    // Set min to current local time to discourage past selections
    els.target.min = toLocalDateTimeValue(Date.now());
  } else {
    // Fallback: treat as free text with ISO-like format
    try { els.target.type = 'text'; } catch {}
    els.target.placeholder = 'YYYY-MM-DDTHH:mm（例: 2025-12-31T23:59）';
    els.target.setAttribute('enterkeyhint', 'done');
    els.target.setAttribute('autocomplete', 'off');
    els.target.setAttribute('inputmode', 'text');
  }

  // Restore if saved
  const restored = loadState();
  if (restored) {
    els.title.value = restored.title || '';
    els.target.value = toLocalDateTimeValue(restored.targetMs);
    applyState(restored);
  }

  els.form.addEventListener('submit', (e) => {
    e.preventDefault();
    const title = els.title.value.trim();
    const value = els.target.value;
    if (!value) return;
    let targetMs;
    if (DATETIME_SUPPORTED) {
      const target = new Date(value); // datetime-local → local time
      targetMs = target.getTime();
    } else {
      targetMs = parseLocalDateTimeString(value);
    }
    if (!Number.isFinite(targetMs) || targetMs <= Date.now()) {
      els.target.focus();
      els.target.reportValidity?.();
      return;
    }
    // Unlock audio on user gesture if needed
    primeAudio();
    notified = false;
    applyState({ title, targetMs });
  });

  els.reset.addEventListener('click', () => {
    els.title.value = '';
    els.target.value = toLocalDateTimeValue(Date.now());
    if (DATETIME_SUPPORTED) {
      els.target.min = toLocalDateTimeValue(Date.now());
    }
    applyState(null);
  });

  // Register service worker for PWA when served over http(s)
  if ('serviceWorker' in navigator && /^https?:$/.test(location.protocol)) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('./sw.js').catch(() => {});
    });
  }

  // Generate PNG icons (192/512) and update manifest/favicons
  try { setupDynamicIcons(); } catch {}
}

// --- Notification helpers (sound + vibration) ---
let audioCtx = null;
function primeAudio() {
  try {
    if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
    if (audioCtx.state === 'suspended') audioCtx.resume();
  } catch {}
}

async function beep(pattern = [880, 988, 880], durationMs = 120, gapMs = 80) {
  if (!audioCtx) return;
  for (const freq of pattern) {
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.type = 'sine';
    osc.frequency.value = freq;
    gain.gain.value = 0.001;
    osc.connect(gain).connect(audioCtx.destination);
    const now = audioCtx.currentTime;
    gain.gain.exponentialRampToValueAtTime(0.2, now + 0.01);
    osc.start();
    osc.stop(now + durationMs / 1000);
    await new Promise(r => setTimeout(r, durationMs + gapMs));
  }
}

function vibrate() {
  try { navigator.vibrate && navigator.vibrate([200, 100, 200]); } catch {}
}

function notifyReached() {
  vibrate();
  primeAudio();
  beep();
}

// --- Dynamic PNG icons + manifest injection ---
function drawIcon(ctx, size) {
  const r = 96 * (size / 512); // base radius scaling
  const grad = ctx.createLinearGradient(0, 0, size, size);
  grad.addColorStop(0, '#2563eb');
  grad.addColorStop(1, '#0ea5e9');
  ctx.fillStyle = grad;
  const rr = size * 0.1875; // 512 -> 96
  roundRect(ctx, 0, 0, size, size, rr);
  ctx.fill();

  ctx.fillStyle = 'rgba(255,255,255,0.15)';
  const pad = size * 0.1875; // 96
  const panelW = size - pad * 2;
  const panelH = size * 0.5625; // 288 on 512
  roundRect(ctx, pad, size * 0.25, panelW, panelH, size * 0.046875);
  ctx.fill();

  ctx.fillStyle = 'rgba(255,255,255,0.8)';
  roundRect(ctx, pad + size * 0.046875, size * 0.296875, panelW - size * 0.09375, size * 0.046875, size * 0.0234375);
  ctx.fill();

  ctx.fillStyle = '#fff';
  // top circles
  circle(ctx, size * 0.328125, size * 0.25, size * 0.0390625);
  ctx.fill();
  circle(ctx, size * 0.671875, size * 0.25, size * 0.0390625);
  ctx.fill();
  // bars
  roundRect(ctx, size * 0.3125, size * 0.453125, size * 0.375, size * 0.0625, size * 0.03125);
  ctx.fill();
  ctx.globalAlpha = 0.9;
  roundRect(ctx, size * 0.234375, size * 0.515625, size * 0.53125, size * 0.0625, size * 0.03125);
  ctx.globalAlpha = 1;
  ctx.fill();
}

function roundRect(ctx, x, y, w, h, r) {
  const rr = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}

function circle(ctx, cx, cy, r) {
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.closePath();
}

function generateIconDataURL(size) {
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  drawIcon(ctx, size);
  return canvas.toDataURL('image/png');
}

async function setupDynamicIcons() {
  const png192 = generateIconDataURL(192);
  const png512 = generateIconDataURL(512);

  // Favicons
  setIconLink('icon', png192, '192x192');
  setIconLink('icon', png512, '512x512');
  setIconLink('apple-touch-icon', png192, '192x192');

  // Manifest replacement with PNG icons
  const base = await loadExistingManifest();
  const manifest = Object.assign({
    name: '日付カウントダウン',
    short_name: 'カウントダウン',
    start_url: './',
    display: 'standalone',
    background_color: '#0b1220',
    theme_color: '#2563eb',
    scope: './'
  }, base);
  manifest.icons = [
    { src: png192, sizes: '192x192', type: 'image/png', purpose: 'any maskable' },
    { src: png512, sizes: '512x512', type: 'image/png', purpose: 'any maskable' }
  ];
  const blob = new Blob([JSON.stringify(manifest)], { type: 'application/manifest+json' });
  setManifestUrl(URL.createObjectURL(blob));
}

function setIconLink(rel, href, sizes) {
  let link = document.querySelector(`link[rel="${rel}"][sizes="${sizes}"]`);
  if (!link) {
    link = document.createElement('link');
    link.rel = rel;
    link.sizes = sizes;
    link.type = 'image/png';
    document.head.appendChild(link);
  }
  link.href = href;
}

async function loadExistingManifest() {
  try {
    const link = document.querySelector('link[rel="manifest"]');
    if (!link) return {};
    const res = await fetch(link.href, { cache: 'no-cache' });
    if (!res.ok) return {};
    return await res.json();
  } catch { return {}; }
}

function setManifestUrl(href) {
  let link = document.querySelector('link[rel="manifest"][data-dynamic="true"]');
  if (!link) {
    link = document.createElement('link');
    link.rel = 'manifest';
    link.setAttribute('data-dynamic', 'true');
    document.head.appendChild(link);
  }
  link.href = href;
}

init();
