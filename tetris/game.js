(() => {
  const COLS = 10;
  const ROWS = 20;
  const BLOCK = 30; // pixels per cell (board is 300x600)
  const COLORS = {
    I: "#00ffff", O: "#f1e05a", T: "#a970ff", S: "#00ff9c",
    Z: "#ff4d6d", J: "#4dabf7", L: "#ffb74d"
  };
  const SHAPES = {
    I: [ [0,1],[1,1],[2,1],[3,1] ],
    O: [ [1,0],[2,0],[1,1],[2,1] ],
    T: [ [1,0],[0,1],[1,1],[2,1] ],
    S: [ [1,1],[2,1],[0,2],[1,2] ],
    Z: [ [0,1],[1,1],[1,2],[2,2] ],
    J: [ [0,0],[0,1],[1,1],[2,1] ],
    L: [ [2,0],[0,1],[1,1],[2,1] ],
  };
  const TETROS = Object.keys(SHAPES);

  const board = document.getElementById('board');
  const ctx = board.getContext('2d');
  const nextCanvas = document.getElementById('next');
  const nctx = nextCanvas.getContext('2d');
  const holdCanvas = document.getElementById('hold');
  const hctx = holdCanvas.getContext('2d');
  const scoreEl = document.getElementById('score');
  const linesEl = document.getElementById('lines');
  const levelEl = document.getElementById('level');
  const pausedEl = document.getElementById('paused');
  const gameoverEl = document.getElementById('gameover');
  const restartBtn = document.getElementById('restart');

  // Touch controls
  const btnLeft = document.getElementById('btn-left');
  const btnRight = document.getElementById('btn-right');
  const btnDown = document.getElementById('btn-down');
  const btnRotate = document.getElementById('btn-rotate');
  const btnDrop = document.getElementById('btn-drop');
  const btnHold = document.getElementById('btn-hold');
  const btnPause = document.getElementById('btn-pause');

  // Minimal beep sound effects via WebAudio
  const SFX = {
    ctx: null,
    init() {
      if (this.ctx) return;
      try { this.ctx = new (window.AudioContext || window.webkitAudioContext)(); } catch(e) {}
    },
    play(name) {
      this.init();
      if (!this.ctx) return;
      let freq = 440, dur = 0.06, vol = 0.03, type = 'square';
      switch (name) {
        case 'move': freq = 420; dur = 0.03; break;
        case 'rotate': freq = 520; dur = 0.04; break;
        case 'drop': freq = 220; dur = 0.08; vol = 0.05; type = 'sawtooth'; break;
        case 'hold': freq = 300; dur = 0.05; break;
        case 'clear1': freq = 680; dur = 0.07; type = 'triangle'; break;
        case 'clear2': freq = 760; dur = 0.08; type = 'triangle'; break;
        case 'clear3': freq = 820; dur = 0.09; type = 'triangle'; break;
        case 'clear4': freq = 900; dur = 0.12; type = 'triangle'; break;
        case 'level': freq = 1000; dur = 0.12; type = 'square'; break;
        case 'over': freq = 180; dur = 0.5; vol = 0.04; type = 'sine'; break;
      }
      const t = this.ctx.currentTime;
      const o = this.ctx.createOscillator();
      const g = this.ctx.createGain();
      o.type = type;
      o.frequency.value = freq;
      g.gain.setValueAtTime(0.0001, t);
      g.gain.exponentialRampToValueAtTime(vol, t + 0.01);
      g.gain.exponentialRampToValueAtTime(0.0001, t + dur);
      o.connect(g).connect(this.ctx.destination);
      o.start(t);
      o.stop(t + dur);
    }
  };

  function createGrid(w, h) {
    return Array.from({ length: h }, () => Array(w).fill(null));
  }

  function pieceFromType(type) {
    const shape = SHAPES[type].map(p => ({ x: p[0], y: p[1] }));
    return { type, shape, x: 3, y: -2, rot: 0, color: COLORS[type] };
  }

  function randomPiece() {
    const type = TETROS[Math.floor(Math.random() * TETROS.length)];
    return pieceFromType(type);
  }

  function clonePiece(p) { return { type: p.type, shape: p.shape.map(c=>({x:c.x,y:c.y})), x: p.x, y: p.y, rot: p.rot, color: p.color }; }

  function rotate(p) {
    const c = clonePiece(p);
    c.rot = (c.rot + 1) % 4;
    // naive 3x3 rotation for simplicity
    c.shape = c.shape.map(({x,y}) => ({ x: 2 - y, y: x }));
    return c;
  }

  function collides(p) {
    for (const {x,y} of p.shape) {
      const gx = p.x + x, gy = p.y + y;
      if (gy < 0) continue; // allow spawn above
      if (gx < 0 || gx >= COLS || gy >= ROWS) return true;
      if (grid[gy][gx]) return true;
    }
    return false;
  }

  function merge(p) {
    for (const {x,y} of p.shape) {
      const gx = p.x + x, gy = p.y + y;
      if (gy >= 0) grid[gy][gx] = p.color;
    }
  }

  function clearLines() {
    let cleared = 0;
    for (let y = ROWS - 1; y >= 0; y--) {
      if (grid[y].every(v => v)) {
        grid.splice(y, 1);
        grid.unshift(Array(COLS).fill(null));
        cleared++;
        y++;
      }
    }
    if (cleared) {
      const points = [0, 40, 100, 300, 1200][cleared] * level;
      score += points;
      lines += cleared;
      if (cleared >= 1) SFX.play(cleared === 4 ? 'clear4' : ('clear' + cleared));
      const prevLevel = level;
      if (lines >= level * 10) {
        level++;
        dropInterval = Math.max(80, Math.floor(dropInterval * 0.85));
      }
      if (level !== prevLevel) SFX.play('level');
      updateHUD();
    }
  }

  function updateHUD() {
    scoreEl.textContent = String(score);
    linesEl.textContent = String(lines);
    levelEl.textContent = String(level);
  }

  function drawCell(x, y, color, ctx2=ctx, size=BLOCK) {
    ctx2.fillStyle = color;
    ctx2.fillRect(x * size, y * size, size, size);
    ctx2.strokeStyle = "rgba(255,255,255,.08)";
    ctx2.lineWidth = 2;
    ctx2.strokeRect(x * size + 1, y * size + 1, size - 2, size - 2);
  }

  function drawGhostPiece() {
    if (!current) return;
    const g = clonePiece(current);
    while (true) {
      const t = clonePiece(g); t.y += 1;
      if (collides(t)) break; g.y += 1;
    }
    // draw translucent ghost
    ctx.save();
    ctx.globalAlpha = 0.25;
    for (const {x,y} of g.shape) {
      const gx = g.x + x, gy = g.y + y;
      if (gy >= 0) drawCell(gx, gy, current.color);
    }
    ctx.restore();
  }

  function draw() {
    // background grid
    ctx.clearRect(0, 0, board.width, board.height);
    ctx.fillStyle = "#0a0d20";
    ctx.fillRect(0, 0, board.width, board.height);

    // placed cells
    for (let y = 0; y < ROWS; y++) {
      for (let x = 0; x < COLS; x++) {
        const c = grid[y][x];
        if (c) drawCell(x, y, c);
      }
    }
    // ghost then current piece
    if (current) drawGhostPiece();
    if (current) {
      for (const {x,y} of current.shape) {
        const gx = current.x + x, gy = current.y + y;
        if (gy >= 0) drawCell(gx, gy, current.color);
      }
    }
  }

  function drawMini(canvasCtx, type) {
    canvasCtx.clearRect(0, 0, 120, 120);
    if (!type) return;
    const size = 24; // match next/hold preview
    const offset = { x: 2, y: 2 };
    const color = COLORS[type];
    for (const p of SHAPES[type]) {
      const x = p[0] + offset.x, y = p[1] + offset.y;
      drawCell(x, y, color, canvasCtx, size);
    }
  }

  function drawNext() { drawMini(nctx, next?.type); }
  function drawHold() { drawMini(hctx, holdType); }

  function spawn() {
    current = next; next = randomPiece();
    current.x = 3; current.y = -2; current.rot = 0;
    holdUsed = false; // allow hold for the new piece
    if (collides(current)) {
      over = true; gameoverEl.classList.remove('hidden'); SFX.play('over');
    }
    drawNext();
  }

  function hardDrop() {
    if (!current) return;
    let moved = false;
    while (true) {
      const p = clonePiece(current); p.y += 1;
      if (collides(p)) break; current = p; moved = true;
    }
    if (moved) { SFX.play('drop'); tickLock(); }
  }

  function move(dx, dy) {
    const p = clonePiece(current); p.x += dx; p.y += dy;
    if (!collides(p)) { current = p; if (dx !== 0 || dy !== 0) SFX.play('move'); }
  }

  function rotateCurrent() {
    const p = rotate(current);
    if (!collides(p)) { current = p; SFX.play('rotate'); return; }
    // simple wall kicks: try left/right
    for (const k of [-1, 1, -2, 2]) {
      const w = clonePiece(p); w.x += k; if (!collides(w)) { current = w; SFX.play('rotate'); return; }
    }
  }

  function tickLock() {
    merge(current);
    clearLines();
    spawn();
  }

  function update(time = 0) {
    if (paused || over) return;
    const delta = time - lastTime; lastTime = time; dropAccum += delta;
    if (dropAccum > dropInterval) {
      dropAccum = 0;
      const p = clonePiece(current); p.y += 1;
      if (collides(p)) tickLock(); else current = p;
    }
    draw();
    requestAnimationFrame(update);
  }

  function reset() {
    grid = createGrid(COLS, ROWS);
    score = 0; lines = 0; level = 1; dropInterval = 800; over = false; paused = false; holdType = null; holdUsed = false;
    pausedEl.classList.add('hidden');
    gameoverEl.classList.add('hidden');
    current = null; next = randomPiece();
    updateHUD();
    drawHold();
    spawn();
    lastTime = performance.now(); dropAccum = 0;
    requestAnimationFrame(update);
  }

  function togglePause() {
    if (over) return;
    paused = !paused;
    pausedEl.classList.toggle('hidden', !paused);
    if (!paused) { lastTime = performance.now(); requestAnimationFrame(update); }
  }

  function doHold() {
    if (paused || over || holdUsed || !current) return;
    SFX.play('hold');
    const curType = current.type;
    if (holdType == null) {
      holdType = curType;
      drawHold();
      spawn();
    } else {
      const swapType = holdType;
      holdType = curType;
      current = pieceFromType(swapType);
      // check immediate collision (rare)
      if (collides(current)) { over = true; gameoverEl.classList.remove('hidden'); SFX.play('over'); }
    }
    holdUsed = true;
    drawHold();
    draw();
  }

  // State
  let grid = createGrid(COLS, ROWS);
  let score = 0, lines = 0, level = 1;
  let current = null, next = randomPiece();
  let dropInterval = 800; // ms
  let lastTime = 0;
  let dropAccum = 0;
  let paused = false;
  let over = false;
  let holdType = null;
  let holdUsed = false;

  // Input
  document.addEventListener('keydown', (e) => {
    SFX.init();
    if (over) return;
    if (e.code === 'KeyP') { togglePause(); return; }
    if (paused) return;
    switch (e.code) {
      case 'ArrowLeft': move(-1, 0); break;
      case 'ArrowRight': move(1, 0); break;
      case 'ArrowDown': move(0, 1); break;
      case 'ArrowUp': rotateCurrent(); break;
      case 'Space': hardDrop(); break;
      case 'ShiftLeft': case 'ShiftRight': case 'KeyC': doHold(); break;
    }
    draw();
  });

  // Touch controls: trigger on pointerdown
  function bindBtn(btn, fn) {
    if (!btn) return;
    const h = (e) => { e.preventDefault(); SFX.init(); fn(); draw(); };
    btn.addEventListener('pointerdown', h, { passive: false });
    btn.addEventListener('click', h, { passive: false });
  }
  bindBtn(btnLeft, () => { if (!paused && !over) move(-1, 0); });
  bindBtn(btnRight, () => { if (!paused && !over) move(1, 0); });
  bindBtn(btnDown, () => { if (!paused && !over) move(0, 1); });
  bindBtn(btnRotate, () => { if (!paused && !over) rotateCurrent(); });
  bindBtn(btnDrop, () => { if (!paused && !over) hardDrop(); });
  bindBtn(btnHold, () => { if (!paused && !over) doHold(); });
  bindBtn(btnPause, () => { if (!over) togglePause(); });

  restartBtn.addEventListener('click', () => { SFX.init(); reset(); });

  // boot
  reset();
})();
