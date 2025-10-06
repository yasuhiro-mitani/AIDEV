/* Breakout (HTML5 Canvas) */
(function () {
  'use strict';

  const canvas = document.getElementById('game');
  const ctx = canvas.getContext('2d');

  // Handle device pixel ratio for crisp rendering
  const DPR = Math.max(1, Math.min(2, window.devicePixelRatio || 1));
  function resizeCanvas() {
    // CSS sets aspect ratio; compute CSS pixel size from bounding box
    const rect = canvas.getBoundingClientRect();
    const cssW = Math.max(300, Math.floor(rect.width));
    const cssH = Math.floor(cssW * 2 / 3); // 3:2 ratio
    canvas.width = Math.floor(cssW * DPR);
    canvas.height = Math.floor(cssH * DPR);
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
  }
  resizeCanvas();
  addEventListener('resize', resizeCanvas);

  // World params (in CSS pixels; drawing scaled by DPR transform)
  function world() {
    const W = Math.floor(canvas.width / DPR);
    const H = Math.floor(canvas.height / DPR);
    return { W, H };
  }

  // Game state
  let score = 0;
  let lives = 3;
  let paused = false;
  let won = false;

  // Paddle
  const paddle = {
    w: 86, h: 12,
    x: 0, y: 0, speed: 420,
    moveL: false, moveR: false,
  };

  // Ball
  const ball = {
    r: 7, x: 0, y: 0, dx: 240, dy: -240,
    speedUp: 1.03,
  };

  // Bricks
  const BR = { rows: 5, cols: 9, pad: 8, top: 48, margin: 16, h: 18 };
  let bricks = [];

  function resetPaddleAndBall() {
    const { W, H } = world();
    paddle.x = (W - paddle.w) / 2;
    paddle.y = H - paddle.h - 14;
    ball.x = W / 2;
    ball.y = H - paddle.h - 14 - 16;
    const baseSpeed = 260 + Math.min(160, score * 2);
    const angle = (-Math.PI / 4) - Math.random() * (Math.PI / 4);
    const sdx = Math.cos(angle) * baseSpeed;
    const sdy = Math.sin(angle) * baseSpeed;
    ball.dx = sdx;
    ball.dy = sdy;
  }

  function makeBricks() {
    const { W } = world();
    const totalPad = (BR.cols - 1) * BR.pad;
    const innerW = W - BR.margin * 2 - totalPad;
    const bw = Math.max(28, Math.floor(innerW / BR.cols));
    const bricksArr = [];
    for (let r = 0; r < BR.rows; r++) {
      for (let c = 0; c < BR.cols; c++) {
        const x = BR.margin + c * (bw + BR.pad);
        const y = BR.top + r * (BR.h + BR.pad);
        bricksArr.push({ x, y, w: bw, h: BR.h, alive: true, row: r });
      }
    }
    return bricksArr;
  }

  function resetGame(full = true) {
    if (full) {
      score = 0;
      lives = 3;
      won = false;
      bricks = makeBricks();
    }
    resetPaddleAndBall();
  }

  // Controls
  document.getElementById('pauseBtn').addEventListener('click', () => {
    paused = !paused;
    document.getElementById('pauseBtn').textContent = paused ? 'Resume' : 'Pause';
  });
  document.getElementById('resetBtn').addEventListener('click', () => resetGame(true));

  addEventListener('keydown', (e) => {
    if (e.key === 'ArrowLeft' || e.key === 'a') paddle.moveL = true;
    if (e.key === 'ArrowRight' || e.key === 'd') paddle.moveR = true;
    if (e.key === ' ' || e.key === 'Spacebar') {
      paused = !paused;
      const btn = document.getElementById('pauseBtn');
      btn.textContent = paused ? 'Resume' : 'Pause';
    }
  });
  addEventListener('keyup', (e) => {
    if (e.key === 'ArrowLeft' || e.key === 'a') paddle.moveL = false;
    if (e.key === 'ArrowRight' || e.key === 'd') paddle.moveR = false;
  });

  // Mouse / touch
  function setPaddleFromPoint(clientX) {
    const rect = canvas.getBoundingClientRect();
    const x = clientX - rect.left;
    paddle.x = Math.min(Math.max(0, x - paddle.w / 2), world().W - paddle.w);
  }
  canvas.addEventListener('mousemove', (e) => setPaddleFromPoint(e.clientX));
  canvas.addEventListener('touchstart', (e) => {
    if (e.touches[0]) setPaddleFromPoint(e.touches[0].clientX);
    e.preventDefault();
  }, { passive: false });
  canvas.addEventListener('touchmove', (e) => {
    if (e.touches[0]) setPaddleFromPoint(e.touches[0].clientX);
    e.preventDefault();
  }, { passive: false });

  // Drawing helpers
  function clear() {
    const { W, H } = world();
    ctx.clearRect(0, 0, W, H);
  }

  function drawHUD() {
    const { W } = world();
    ctx.fillStyle = '#94a3b8';
    ctx.font = '12px system-ui, sans-serif';
    ctx.textBaseline = 'top';
    ctx.fillText(`Score: ${score}`, 8, 6);
    const livesText = `Lives: ${lives}`;
    const w = ctx.measureText(livesText).width;
    ctx.fillText(livesText, W - w - 8, 6);
  }

  function drawPaddle() {
    ctx.fillStyle = '#22d3ee';
    ctx.fillRect(paddle.x, paddle.y, paddle.w, paddle.h);
  }

  function drawBall() {
    ctx.beginPath();
    ctx.arc(ball.x, ball.y, ball.r, 0, Math.PI * 2);
    ctx.closePath();
    ctx.fillStyle = '#fbbf24';
    ctx.fill();
  }

  function drawBricks() {
    for (const b of bricks) {
      if (!b.alive) continue;
      const hues = ['#60a5fa', '#34d399', '#f59e0b', '#f472b6', '#a78bfa'];
      ctx.fillStyle = hues[b.row % hues.length];
      ctx.fillRect(b.x, b.y, b.w, b.h);
    }
  }

  // Physics
  function step(dt) {
    const { W, H } = world();

    // Paddle movement by keys
    if (paddle.moveL) paddle.x -= paddle.speed * dt;
    if (paddle.moveR) paddle.x += paddle.speed * dt;
    if (paddle.x < 0) paddle.x = 0;
    if (paddle.x + paddle.w > W) paddle.x = W - paddle.w;

    // Ball movement
    ball.x += ball.dx * dt;
    ball.y += ball.dy * dt;

    // Wall collisions
    if (ball.x - ball.r < 0) { ball.x = ball.r; ball.dx *= -1; }
    if (ball.x + ball.r > W) { ball.x = W - ball.r; ball.dx *= -1; }
    if (ball.y - ball.r < 0) { ball.y = ball.r; ball.dy *= -1; }

    // Paddle collision
    if (ball.y + ball.r >= paddle.y && ball.y + ball.r <= paddle.y + paddle.h &&
        ball.x >= paddle.x && ball.x <= paddle.x + paddle.w && ball.dy > 0) {
      ball.y = paddle.y - ball.r;
      // Reflect angle based on hit position
      const hitPos = (ball.x - (paddle.x + paddle.w / 2)) / (paddle.w / 2);
      const angle = hitPos * (Math.PI / 3); // up to 60 degrees
      const speed = Math.hypot(ball.dx, ball.dy) * ball.speedUp;
      ball.dx = Math.sin(angle) * speed;
      ball.dy = -Math.cos(angle) * speed;
    }

    // Bottom - lose life
    if (ball.y - ball.r > H) {
      lives -= 1;
      if (lives <= 0) {
        // Game over -> reset everything
        bricks = makeBricks();
        lives = 3;
        score = 0;
        won = false;
      }
      resetPaddleAndBall();
      paused = true;
      document.getElementById('pauseBtn').textContent = 'Resume';
      return; // Skip brick checks this frame
    }

    // Brick collisions (AABB vs circle simple check)
    for (const b of bricks) {
      if (!b.alive) continue;
      const closestX = Math.max(b.x, Math.min(ball.x, b.x + b.w));
      const closestY = Math.max(b.y, Math.min(ball.y, b.y + b.h));
      const dx = ball.x - closestX;
      const dy = ball.y - closestY;
      if ((dx * dx + dy * dy) <= (ball.r * ball.r)) {
        b.alive = false;
        score += 1;
        // Determine collision side to reflect properly
        const overlapLeft = Math.abs((ball.x + ball.r) - b.x);
        const overlapRight = Math.abs((b.x + b.w) - (ball.x - ball.r));
        const overlapTop = Math.abs((ball.y + ball.r) - b.y);
        const overlapBottom = Math.abs((b.y + b.h) - (ball.y - ball.r));
        const minOverlap = Math.min(overlapLeft, overlapRight, overlapTop, overlapBottom);
        if (minOverlap === overlapLeft || minOverlap === overlapRight) ball.dx *= -1; else ball.dy *= -1;
        break; // one brick per frame
      }
    }

    // Win condition
    if (!won && bricks.every(b => !b.alive)) {
      won = true;
      paused = true;
      document.getElementById('pauseBtn').textContent = 'Resume';
      // Refill bricks for next round, keep score/lives
      setTimeout(() => { bricks = makeBricks(); won = false; }, 600);
    }
  }

  function drawOverlay(text) {
    const { W, H } = world();
    ctx.fillStyle = 'rgba(0,0,0,0.35)';
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = '#e5e7eb';
    ctx.font = 'bold 20px system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(text, W / 2, H / 2);
    ctx.textAlign = 'start';
  }

  // Main loop
  let last = performance.now();
  function loop(now) {
    const dt = Math.min(0.033, (now - last) / 1000); // clamp
    last = now;

    clear();
    drawHUD();
    drawBricks();
    drawPaddle();
    drawBall();
    if (!paused) step(dt);
    else drawOverlay('Paused (Space to resume)');

    requestAnimationFrame(loop);
  }

  // Boot
  bricks = makeBricks();
  resetPaddleAndBall();
  paused = false;
  requestAnimationFrame(loop);
})();

