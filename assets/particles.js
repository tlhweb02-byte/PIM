// 首页粒子背景：Nike Swoosh 点阵随滚动拆解重组，鼠标视差与排斥。
// 纯 Canvas 2D，无依赖。离开首页时自动销毁。
(() => {
  if (window.__pimParticles) return;

  const SWOOSH_PATH = "M24 7.8L6.442 15.276c-1.456.616-2.679.925-3.668.925-1.12 0-1.933-.392-2.437-1.177-.317-.504-.41-1.143-.28-1.918.13-.775.476-1.6 1.036-2.478.467-.71 1.232-1.643 2.297-2.8a6.122 6.122 0 00-.784 1.848c-.28 1.195-.028 2.072.756 2.632.373.261.886.392 1.54.392.522 0 1.11-.084 1.764-.252L24 7.8z";
  const SECTION_SELECTOR = '[class*="st-key-home-sec-"]';
  const INK = "24, 24, 27";

  const reduceMotion = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const isMobile = matchMedia("(max-width: 768px), (pointer: coarse)").matches;
  const N = isMobile ? 900 : 2600;
  const physics = !isMobile && !reduceMotion;

  const rand = (a, b) => a + Math.random() * (b - a);
  const smooth = (t) => t * t * (3 - 2 * t);
  const lerp = (a, b, t) => a + (b - a) * t;

  // ---------- 目标形态：每个形态 N 个 [x, y, z]，范围约 [-1, 1] ----------
  function swoosh() {
    const W = 480, H = Math.round(W * 11.2 / 24);
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const g = c.getContext("2d");
    g.scale(W / 24, H / 11.2);
    g.translate(0, -5.5);
    g.fill(new Path2D(SWOOSH_PATH));
    const data = g.getImageData(0, 0, W, H).data;
    const on = (x, y) => x >= 0 && y >= 0 && x < W && y < H && data[(y * W + x) * 4 + 3] > 128;
    const fill = [], edge = [];
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      if (!on(x, y)) continue;
      (on(x + 1, y) && on(x - 1, y) && on(x, y + 1) && on(x, y - 1) ? fill : edge).push([x, y]);
    }
    const pts = [];
    for (let i = 0; i < N; i++) {
      const src = Math.random() < 0.45 ? edge : fill;
      const [px, py] = src[(Math.random() * src.length) | 0];
      const x = (px / W) * 2 - 1;
      const y = -((py / H) * 2 - 1) * (H / W);
      // 沿 x 方向弯出弧度 + 少量厚度，形成立体感
      pts.push([x, y + 0.08, 0.35 * Math.cos(x * 1.4) - 0.2 + rand(-0.06, 0.06)]);
    }
    return pts;
  }

  function grid() { // 表格转化：表格框线（横线 + 竖线），按线长分配粒子
    const rows = 9, cols = 6, nh = Math.round(N * 0.7), pts = [];
    for (let i = 0; i < N; i++) {
      if (i < nh) pts.push([rand(-0.9, 0.9), ((i % rows) / (rows - 1)) * 1.1 - 0.55, rand(-0.01, 0.01)]);
      else pts.push([(((i - nh) % cols) / (cols - 1)) * 1.8 - 0.9, rand(-0.55, 0.55), rand(-0.01, 0.01)]);
    }
    return pts;
  }

  function sphere() { // 图片压缩：致密球体
    const pts = [], ga = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < N; i++) {
      const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), th = ga * i, R = rand(0.52, 0.6);
      pts.push([Math.cos(th) * r * R, y * R, Math.sin(th) * r * R]);
    }
    return pts;
  }

  function ring() { // 智能扩图：向外扩开的圆环
    const pts = [];
    for (let i = 0; i < N; i++) {
      const a = rand(0, Math.PI * 2), b = rand(0, Math.PI * 2);
      const R = i % 3 === 0 ? rand(0.95, 1.15) : 0.8, r = 0.07;
      pts.push([(R + r * Math.cos(b)) * Math.cos(a), (R + r * Math.cos(b)) * Math.sin(a), r * Math.sin(b)]);
    }
    return pts;
  }

  function bars() { // 数据统计：柱状图
    const H = [0.45, 0.8, 0.6, 1.1, 0.9], pts = [];
    for (let i = 0; i < N; i++) {
      const k = i % H.length, x0 = -0.8 + k * 0.4;
      pts.push([x0 + rand(-0.12, 0.12), -0.6 + rand(0, H[k] * 1.2), rand(-0.12, 0.12)]);
    }
    return pts;
  }

  const SHAPES = [swoosh(), grid(), sphere(), ring(), bars()];
  // 每个章节的视角 [绕 X, 绕 Y]
  const VIEWS = [[0.12, -0.35], [0.5, 0.3], [0.25, 0.0], [0.15, 0.45], [0.2, -0.45]];

  const P = Array.from({ length: N }, (_, i) => {
    const s = SHAPES[0][i];
    const sv = [rand(-1, 1), rand(-1, 1), rand(-1, 1)];
    const len = Math.hypot(...sv) || 1;
    return {
      x: s[0], y: s[1], z: s[2], vx: 0, vy: 0, vz: 0,
      dx: 0, dy: 0, ddx: 0, ddy: 0, // 鼠标排斥的屏幕偏移
      scatter: sv.map((v) => (v / len) * rand(0.4, 1.0)),
      phase: rand(0, Math.PI * 2),
      size: rand(0.6, 1.4),
    };
  });

  // ---------- DOM ----------
  const canvas = document.createElement("canvas");
  canvas.setAttribute("aria-hidden", "true");
  canvas.style.cssText = "position:fixed;inset:0;width:100vw;height:100vh;z-index:0;pointer-events:none;";
  const host = document.querySelector('[data-testid="stApp"]') || document.body;
  host.prepend(canvas);
  const ctx = canvas.getContext("2d");

  const dots = document.createElement("nav");
  dots.setAttribute("aria-label", "章节");
  dots.style.cssText = "position:fixed;right:24px;top:50%;transform:translateY(-50%);z-index:5;display:flex;flex-direction:column;gap:10px;";
  host.append(dots);

  const sprite = document.createElement("canvas"); // 带光晕的粒子贴图
  sprite.width = sprite.height = 64;
  const sg = sprite.getContext("2d");
  const grad = sg.createRadialGradient(32, 32, 0, 32, 32, 32);
  grad.addColorStop(0, `rgba(${INK},1)`);
  grad.addColorStop(0.22, `rgba(${INK},0.9)`);
  grad.addColorStop(0.45, `rgba(${INK},0.18)`);
  grad.addColorStop(1, `rgba(${INK},0)`);
  sg.fillStyle = grad;
  sg.fillRect(0, 0, 64, 64);

  let W = 0, Hh = 0, DPR = 1;
  function resize() {
    DPR = Math.min(window.devicePixelRatio || 1, 2);
    W = innerWidth; Hh = innerHeight;
    canvas.width = W * DPR; canvas.height = Hh * DPR;
  }
  resize();
  addEventListener("resize", resize);

  const mouse = { x: 0, y: 0, nx: 0, ny: 0, active: false };
  const onMove = (e) => {
    mouse.x = e.clientX; mouse.y = e.clientY;
    mouse.nx = (e.clientX / W) * 2 - 1; mouse.ny = (e.clientY / Hh) * 2 - 1;
    mouse.active = true;
  };
  const onLeave = () => { mouse.active = false; };
  if (physics) {
    addEventListener("pointermove", onMove);
    document.addEventListener("pointerleave", onLeave);
  }

  // ---------- 滚动进度：根据各章节相对视口位置计算 0..4 ----------
  let sections = [];
  function progress() {
    sections = [...document.querySelectorAll(SECTION_SELECTOR)];
    if (sections.length < 2) return 0;
    // 章节停留时形态保持完整，只在离开章节的后半段过渡到下一个形态
    const line = Hh * 0.35, tops = sections.map((s) => s.getBoundingClientRect().top);
    for (let i = 0; i < tops.length - 1; i++) {
      if (line < tops[i + 1]) {
        const f = (line - tops[i]) / (tops[i + 1] - tops[i]);
        return i + Math.min(Math.max((f - 0.45) / 0.5, 0), 1);
      }
    }
    return tops.length - 1;
  }

  function syncDots(active) {
    if (dots.children.length !== sections.length) {
      dots.replaceChildren(...sections.map((s, i) => {
        const b = document.createElement("button");
        const label = s.querySelector("h1, h2")?.textContent || `第 ${i + 1} 屏`;
        b.setAttribute("aria-label", label); b.title = label;
        b.style.cssText = "width:6px;height:6px;padding:0;border:0;border-radius:3px;cursor:pointer;transition:all .5s cubic-bezier(.16,1,.3,1);";
        b.onclick = () => s.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth" });
        return b;
      }));
    }
    [...dots.children].forEach((b, i) => {
      const on = i === active;
      b.style.height = on ? "22px" : "6px";
      b.style.background = on ? `rgb(${INK})` : `rgba(${INK},0.25)`;
    });
  }

  // ---------- 主循环 ----------
  let rotX = VIEWS[0][0], rotY = VIEWS[0][1], seenHome = false, raf = 0;
  const started = performance.now();

  function destroy() {
    cancelAnimationFrame(raf);
    removeEventListener("resize", resize);
    removeEventListener("pointermove", onMove);
    document.removeEventListener("pointerleave", onLeave);
    canvas.remove(); dots.remove();
    window.__pimParticles = null;
  }

  function frame(now) {
    // 离开首页（章节不在页面上）就销毁
    const onHome = !!document.querySelector(SECTION_SELECTOR);
    if (onHome) seenHome = true;
    else if (seenHome || now - started > 5000) return destroy();

    const time = now / 1000;
    const p = progress();
    const a = Math.floor(p), b = Math.min(a + 1, SHAPES.length - 1), t = smooth(p - a);
    const burst = Math.sin(Math.PI * t) * 0.7; // 过渡中段拆解
    syncDots(Math.round(p));

    // 视角：章节视角 + 轻微摆动 + 鼠标视差（阻尼跟随）
    const sway = reduceMotion ? 0 : Math.sin(time * 0.25) * 0.12;
    const tx = lerp(VIEWS[a][0], VIEWS[b][0], t) + (physics && mouse.active ? mouse.ny * 0.18 : 0);
    const ty = lerp(VIEWS[a][1], VIEWS[b][1], t) + sway + (physics && mouse.active ? mouse.nx * 0.3 : 0);
    rotX += (tx - rotX) * (reduceMotion ? 1 : 0.05);
    rotY += (ty - rotY) * (reduceMotion ? 1 : 0.05);
    const cX = Math.cos(rotX), sX = Math.sin(rotX), cY = Math.cos(rotY), sY = Math.sin(rotY);

    // 画布位置：桌面端在右侧视觉重心，移动端居中偏下并变淡
    const cx = isMobile ? W * 0.5 : W * 0.7;
    const cy = isMobile ? Hh * 0.8 : Hh * 0.54;
    const scale = isMobile ? W * 0.38 : Math.min(W * 0.24, Hh * 0.42);
    const fade = isMobile ? 0.6 : 1;

    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    ctx.clearRect(0, 0, W, Hh);
    const A = SHAPES[a], B = SHAPES[b], R = 120;

    for (let i = 0; i < N; i++) {
      const q = P[i];
      const drift = reduceMotion ? 0 : 0.012;
      const gx = lerp(A[i][0], B[i][0], t) + q.scatter[0] * burst + Math.sin(time * 0.7 + q.phase) * drift;
      const gy = lerp(A[i][1], B[i][1], t) + q.scatter[1] * burst + Math.cos(time * 0.6 + q.phase) * drift;
      const gz = lerp(A[i][2], B[i][2], t) + q.scatter[2] * burst;

      if (reduceMotion) { q.x = gx; q.y = gy; q.z = gz; }
      else { // 弹簧阻尼：平滑游向目标
        q.vx = (q.vx + (gx - q.x) * 0.05) * 0.84; q.x += q.vx;
        q.vy = (q.vy + (gy - q.y) * 0.05) * 0.84; q.y += q.vy;
        q.vz = (q.vz + (gz - q.z) * 0.05) * 0.84; q.z += q.vz;
      }

      // 旋转 + 透视投影
      const x1 = q.x * cY + q.z * sY, z1 = -q.x * sY + q.z * cY;
      const y2 = q.y * cX - z1 * sX, z2 = q.y * sX + z1 * cX;
      const f = 3.2 / (3.2 - z2);
      let sx = cx + x1 * scale * f, sy = cy - y2 * scale * f;

      if (physics) { // 鼠标排斥，带弹性回位
        if (mouse.active) {
          const ex = sx + q.dx - mouse.x, ey = sy + q.dy - mouse.y, d2 = ex * ex + ey * ey;
          if (d2 < R * R) {
            const d = Math.sqrt(d2) || 1, force = (1 - d / R) * 2.4;
            q.ddx += (ex / d) * force; q.ddy += (ey / d) * force;
          }
        }
        q.ddx = (q.ddx - q.dx * 0.06) * 0.86; q.dx += q.ddx;
        q.ddy = (q.ddy - q.dy * 0.06) * 0.86; q.dy += q.ddy;
        sx += q.dx; sy += q.dy;
      }

      // 景深：前大前亮，后小后暗；呼吸微光
      const depth = Math.min(Math.max((z2 + 1.2) / 2.4, 0), 1);
      const breath = reduceMotion ? 1 : 0.8 + 0.2 * Math.sin(time * 1.4 + q.phase);
      const near = physics && mouse.active ? Math.max(0, 1 - Math.hypot(sx - mouse.x, sy - mouse.y) / R) * 0.4 : 0;
      ctx.globalAlpha = Math.min(1, (0.12 + 0.6 * depth) * breath * fade + near);
      const s = (1.4 + 4.2 * depth) * q.size * f;
      ctx.drawImage(sprite, sx - s, sy - s, s * 2, s * 2);
    }
    ctx.globalAlpha = 1;
    raf = requestAnimationFrame(frame);
  }

  window.__pimParticles = { destroy };
  raf = requestAnimationFrame(frame);
})();
