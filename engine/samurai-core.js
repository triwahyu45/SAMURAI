/**
 * Samurai Core Engine v4 — Canvas2D Vector + Three.js WebGL + 6x Shutter Accumulator
 * 100% pure stateless deterministic renderer: window.renderFrame(t)
 */
(function (global) {
  'use strict';

  const W = 1920;
  const H = 1080;

  // ── PURE MATH & GRAPH EDITOR CURVES ──
  const clamp = (v, lo = 0, hi = 1) => Math.max(lo, Math.min(hi, v));
  const lerp = (a, b, t) => a + (b - a) * clamp(t);
  const prog = (x, x0, x1) => (x1 <= x0 ? 1 : clamp((x - x0) / (x1 - x0)));

  const easeIn = (t, p = 3) => Math.pow(clamp(t), p);
  const easeOut = (t, p = 3) => 1 - Math.pow(1 - clamp(t), p);
  const easeInOut = (t) => {
    t = clamp(t);
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2;
  };
  const expoOut = (t) => {
    t = clamp(t);
    return t === 1 ? 1 : 1 - Math.pow(2, -10 * t);
  };
  const whipInOut = (t) => {
    t = clamp(t);
    if (t === 0 || t === 1) return t;
    return t < 0.5
      ? Math.pow(2, 20 * t - 10) / 2
      : (2 - Math.pow(2, -20 * t + 10)) / 2;
  };
  const easeOutBack = (t, s = 1.65) => {
    t = clamp(t) - 1;
    return 1 + t * t * ((s + 1) * t + s);
  };

  // ── DETERMINISTIC ANIMATION SOLVER (Stateless, Analytical) ──
  const Anim = {
    SPRING_SETTLE_WARN_THRESHOLD: 0.005,
    lastWarnings: [],

    _cubicBezier(x1, y1, x2, y2, u) {
      if (u <= 0) return 0;
      if (u >= 1) return 1;
      const cx = 3 * x1, bx = 3 * (x2 - x1) - cx, ax = 1 - cx - bx;
      const cy = 3 * y1, by = 3 * (y2 - y1) - cy, ay = 1 - cy - by;
      const sampleX = (s) => ((ax * s + bx) * s + cx) * s;
      const sampleDX = (s) => (3 * ax * s + 2 * bx) * s + cx;
      const sampleY = (s) => ((ay * s + by) * s + cy) * s;
      let s = u;
      for (let i = 0; i < 6; i++) {
        const err = sampleX(s) - u;
        if (Math.abs(err) < 1e-7) return sampleY(s);
        const dx = sampleDX(s);
        if (Math.abs(dx) < 1e-6) break;
        s -= err / dx;
      }
      let lo = 0, hi = 1;
      s = clamp(s, 0, 1);
      for (let i = 0; i < 18; i++) {
        const x = sampleX(s);
        if (Math.abs(x - u) < 1e-7) break;
        if (u > x) lo = s; else hi = s;
        s = 0.5 * (lo + hi);
      }
      return sampleY(s);
    },

    _analyticSpringRaw(tau, { stiffness = 320, damping = 18, mass = 1 } = {}) {
      const m = Math.max(1e-6, mass);
      const k = Math.max(1e-6, stiffness);
      const c = Math.max(0, damping);
      const wn = Math.sqrt(k / m);
      const zeta = c / (2 * Math.sqrt(k * m));
      if (zeta < 1 - 1e-6) {
        const wd = wn * Math.sqrt(Math.max(1 - zeta * zeta, 1e-9));
        return 1 - Math.exp(-zeta * wn * tau) * (Math.cos(wd * tau) + (zeta * wn / wd) * Math.sin(wd * tau));
      }
      if (Math.abs(zeta - 1) <= 1e-6) {
        return 1 - Math.exp(-wn * tau) * (1 + wn * tau);
      }
      const root = Math.sqrt(zeta * zeta - 1);
      const s1 = wn * (-zeta + root);
      const s2 = wn * (-zeta - root);
      return 1 - (s1 * Math.exp(s2 * tau) - s2 * Math.exp(s1 * tau)) / (s1 - s2);
    },

    _analyticSpring(u, durSec = 1.0, opts = {}) {
      if (u <= 0) return 0;
      const d = Math.max(1e-6, durSec);
      if (u >= 1) {
        const res = Math.abs(1 - this._analyticSpringRaw(d, opts));
        if (res > this.SPRING_SETTLE_WARN_THRESHOLD) {
          const msg = `Anim.spring end-residual=${res.toExponential(3)} > threshold=${this.SPRING_SETTLE_WARN_THRESHOLD} (durSec=${d})`;
          this.lastWarnings.push(msg);
          if (typeof console !== 'undefined' && console.warn) console.warn(msg);
        }
        return 1;
      }
      return this._analyticSpringRaw(u * d, opts);
    },

    evalEase(ease, u, durSec = 1.0) {
      const uc = clamp(u);
      if (uc <= 0) return 0;
      if (uc >= 1) {
        if (ease && typeof ease === 'object' && ease.type === 'spring') {
          this._analyticSpring(1.0, durSec, ease);
        }
        return 1;
      }
      if (!ease || ease === 'linear') return uc;
      if (typeof ease === 'string') {
        if (ease === 'easeIn') return easeIn(uc);
        if (ease === 'easeOut') return easeOut(uc);
        if (ease === 'easeInOut') return easeInOut(uc);
        if (ease === 'expoOut') return expoOut(uc);
        if (ease === 'whipInOut') return whipInOut(uc);
        if (ease === 'easeOutBack' || ease === 'overshoot') return easeOutBack(uc);
        if (ease === 'spring') return this._analyticSpring(uc, durSec, {});
        if (ease === 'anticipate') return uc < 0.18 ? lerp(0, -0.14, easeOut(uc / 0.18, 2)) : lerp(-0.14, 1, expoOut((uc - 0.18) / 0.82));
        return uc;
      }
      const kind = ease.type || 'linear';
      if (kind === 'linear') return uc;
      if (kind === 'cubic-bezier' || kind === 'bezier') {
        const p = ease.p || [0.42, 0, 0.58, 1];
        return this._cubicBezier(p[0], p[1], p[2], p[3], uc);
      }
      if (kind === 'spring') {
        return this._analyticSpring(uc, durSec, ease);
      }
      if (kind === 'overshoot') {
        return easeOutBack(uc, ease.s != null ? ease.s : 1.65);
      }
      if (kind === 'anticipate') {
        const pull = ease.pull != null ? ease.pull : -0.14;
        return uc < 0.18 ? lerp(0, pull, easeOut(uc / 0.18, 2)) : lerp(pull, 1, expoOut((uc - 0.18) / 0.82));
      }
      if (kind === 'expoOut') return expoOut(uc);
      return uc;
    },

    solve(track, t) {
      if (typeof track === 'number') return track;
      const kfs = Array.isArray(track) ? track : (track && Array.isArray(track.keyframes) ? track.keyframes : null);
      if (!kfs || kfs.length === 0) return 0;
      if (kfs.length === 1 || t <= kfs[0].t) return kfs[0].v;
      const last = kfs[kfs.length - 1];
      if (t >= last.t) return last.v;
      for (let i = 0; i < kfs.length - 1; i++) {
        const k0 = kfs[i], k1 = kfs[i + 1];
        if (t <= k1.t) {
          const dur = k1.t - k0.t;
          if (dur <= 0) return k1.v;
          const u = (t - k0.t) / dur;
          const e = this.evalEase(k0.ease || k1.ease || 'linear', u, dur);
          return k0.v + (k1.v - k0.v) * e;
        }
      }
      return last.v;
    },
  };

  const spring = (t, { stiffness = 320, damping = 18 } = {}) =>
    Anim.evalEase({ type: 'spring', stiffness, damping }, t, 1.0);
  const anticipate = (t, pull = -0.14) =>
    Anim.evalEase({ type: 'anticipate', pull }, t, 1.0);
  const seededRand = (seed) => {
    const x = Math.sin(seed * 12.9898 + 78.233) * 43758.5453;
    return x - Math.floor(x);
  };

  // ── CAMERA RIG ──
  function applyCamera(ctx, { x = 0, y = 0, zoom = 1, rotDeg = 0, driftT = 0, driftZoom = 0.045, t = 0 } = {}) {
    const curT = t || (global.Samurai ? global.Samurai.currentT : 0) || 0;
    const wiggleX = curT > 0 ? (Math.sin(curT * 5.2) * 5.0 + Math.sin(curT * 13.7) * 2.4) : 0;
    const wiggleY = curT > 0 ? (Math.cos(curT * 4.4) * 4.0 + Math.cos(curT * 11.3) * 1.9) : 0;
    const wiggleZ = curT > 0 ? (1 + Math.sin(curT * 3.6) * 0.006) : 1;
    const wiggleRot = curT > 0 ? (Math.sin(curT * 4.0) * 0.12) : 0;

    const dz = zoom * (1 + driftZoom * driftT) * wiggleZ;
    const dx = x + Math.sin(driftT * Math.PI * 1.3) * 6 + wiggleX;
    const dy = y + Math.cos(driftT * Math.PI * 0.9) * 4 + wiggleY;
    ctx.translate(W / 2, H / 2);
    ctx.scale(dz, dz);
    if (rotDeg !== 0 || wiggleRot !== 0) ctx.rotate(((rotDeg + wiggleRot) * Math.PI) / 180);
    ctx.translate(-W / 2 - dx, -H / 2 - dy);
  }

  // ── BACKGROUND & ATMOSPHERE PRIMITIVES (3-STOP STUDIO GRADIENTS + 3-LAYER FIREFLIES) ──
  function drawPanelBg(ctx, hex, glowHex = null, dotMode = 'none', t = 0, { dots = true } = {}) {
    if (glowHex) {
      const g = ctx.createRadialGradient(W / 2, H / 2, 40, W / 2, H / 2, W * 0.72);
      g.addColorStop(0, glowHex);
      g.addColorStop(0.62, hex);
      g.addColorStop(1, dotMode === 'light' ? '#E4E0D6' : (hex === '#070709' || hex === '#070708' ? '#030304' : hex));
      ctx.fillStyle = g;
    } else {
      ctx.fillStyle = hex;
    }
    ctx.fillRect(0, 0, W, H);

    if (dotMode !== 'none' && dots !== false) {
      ctx.save();
      ctx.fillStyle = dotMode === 'dark' ? 'rgba(255,255,255,0.085)' : 'rgba(0,0,0,0.085)';
      const step = 38;
      const ox = (t * 6) % step;
      for (let x = ox; x < W; x += step) {
        for (let y = 19; y < H; y += step) {
          ctx.fillRect(x, y, 2.2, 2.2);
        }
      }
      ctx.restore();
    }
  }

  function drawEmbers(ctx, t, count = 22, cx = W / 2, cy = H / 2, sx = 1800, sy = 1000, color = '#FF5A2E', alpha = 0.45) {
    const f = t * 30;
    ctx.save();
    ctx.globalCompositeOperation = 'screen';

    // Layer 1: Foreground out-of-focus bokeh orbs (warm orange-red)
    const bokehCount = Math.max(4, Math.floor(count * 0.3));
    for (let i = 0; i < bokehCount; i++) {
      const rx = seededRand(i * 13 + 7) - 0.5;
      const ry = seededRand(i * 17 + 11) - 0.5;
      const r = 18 + seededRand(i * 19 + 3) * 24;
      const bx = cx + rx * sx + Math.sin(f * 0.025 + i * 2.1) * 42;
      const by = cy + ry * sy + Math.cos(f * 0.02 + i * 1.7) * 32;
      const tw = 0.45 + 0.55 * (0.5 + 0.5 * Math.sin(f * 0.06 + i * 3.1));
      const bg = ctx.createRadialGradient(bx, by, 0, bx, by, r);
      bg.addColorStop(0, `rgba(255,120,56,${alpha * 0.45 * tw})`);
      bg.addColorStop(0.55, `rgba(235,68,30,${alpha * 0.18 * tw})`);
      bg.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = bg;
      ctx.beginPath();
      ctx.arc(bx, by, r, 0, Math.PI * 2);
      ctx.fill();
    }

    // Layer 2: Midground glowing fireflies (hot cream core + orange halo + organic wander)
    const fireflyCount = Math.max(8, Math.floor(count * 0.6));
    for (let i = 0; i < fireflyCount; i++) {
      const rx = seededRand(i * 5 + 2) - 0.5;
      const ry = seededRand(i * 7 + 4) - 0.5;
      const spd = 0.35 + seededRand(i * 11 + 6) * 0.95;
      const r = 6 + seededRand(i * 23 + 8) * 7;
      const driftY = ((f * spd * 1.4) % sy) - sy * 0.5;
      const fx = cx + rx * sx + Math.sin(f * 0.045 + i * 1.9) * 36;
      const fy = cy + ry * sy - driftY * 0.25 + Math.cos(f * 0.035 + i * 2.3) * 20;
      const tw = 0.25 + 0.75 * (0.5 + 0.5 * Math.sin(f * 0.14 + i * 4.7));
      const fg = ctx.createRadialGradient(fx, fy, 0, fx, fy, r);
      fg.addColorStop(0, `rgba(255,245,214,${Math.min(1, alpha * 1.45 * tw)})`);
      fg.addColorStop(0.35, `rgba(255,115,48,${alpha * 0.78 * tw})`);
      fg.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = fg;
      ctx.beginPath();
      ctx.arc(fx, fy, r, 0, Math.PI * 2);
      ctx.fill();
    }

    // Layer 3: Background micro-sparks
    const sparkCount = Math.max(6, Math.floor(count * 0.4));
    for (let i = 0; i < sparkCount; i++) {
      const rx = seededRand(i * 3 + 1) - 0.5;
      const ry = seededRand(i * 3 + 2) - 0.5;
      const spd = 0.6 + seededRand(i * 3 + 3) * 1.5;
      const sz = 1.4 + seededRand(i * 7 + 5) * 2.0;
      const driftY = ((f * spd * 1.9) % sy) - sy * 0.5;
      const x = cx + rx * sx + Math.sin(f * 0.05 + i) * 18;
      const y = cy + ry * sy - driftY * 0.35;
      ctx.globalAlpha = alpha * (0.3 + 0.7 * seededRand(i * 11 + Math.floor(f / 5)));
      ctx.fillStyle = color;
      ctx.beginPath();
      ctx.arc(x, y, sz, 0, Math.PI * 2);
      ctx.fill();
    }
    ctx.restore();
  }

  function drawCenterFlare(ctx, cx, cy, radius, alpha = 1.0, rays = 0, rot = 0) {
    ctx.save();
    ctx.globalCompositeOperation = 'screen';
    const g = ctx.createRadialGradient(cx, cy, 0, cx, cy, Math.max(1, radius));
    g.addColorStop(0, `rgba(255,230,185,${alpha})`);
    g.addColorStop(0.22, `rgba(240,75,35,${alpha * 0.75})`);
    g.addColorStop(0.55, `rgba(180,20,15,${alpha * 0.25})`);
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(cx, cy, radius, 0, Math.PI * 2);
    ctx.fill();

    if (rays > 0) {
      ctx.strokeStyle = `rgba(255,140,90,${alpha * 0.55})`;
      for (let i = 0; i < rays; i++) {
        const ang = rot + (i / rays) * Math.PI * 2 + seededRand(i) * 0.2;
        const len = radius * (0.4 + seededRand(i + 50) * 0.85);
        ctx.lineWidth = 1 + seededRand(i + 90) * 1.8;
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(ang) * 12, cy + Math.sin(ang) * 12);
        ctx.lineTo(cx + Math.cos(ang) * len, cy + Math.sin(ang) * len);
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function drawRadialBurst(ctx, cx, cy, lines = 52, color = 'rgba(0,0,0,0.2)', innerR = 140, outerR = 980) {
    ctx.save();
    ctx.strokeStyle = color;
    for (let i = 0; i < lines; i++) {
      const ang = (i / lines) * Math.PI * 2;
      const r0 = innerR + seededRand(i * 5) * 90;
      const r1 = outerR * (0.7 + seededRand(i * 9) * 0.5);
      ctx.lineWidth = 1.5 + seededRand(i * 13) * 2.5;
      ctx.beginPath();
      ctx.moveTo(cx + Math.cos(ang) * r0, cy + Math.sin(ang) * r0);
      ctx.lineTo(cx + Math.cos(ang) * r1, cy + Math.sin(ang) * r1);
      ctx.stroke();
    }
    ctx.restore();
  }

  // ── ECHO SHAPES, GHOST TRAILS, OPTICAL FLARES & INK BURSTS ──
  function drawEchoShapes(ctx, drawShapeFn, {
    cx = W / 2, cy = H / 2, layers = 6, scaleStep = 0.08, rotStepDeg = 4.5,
    alphaStart = 0.42, alphaEnd = 0.06, mode = 'screen',
  } = {}) {
    ctx.save();
    if (mode && mode !== 'source-over') ctx.globalCompositeOperation = mode;
    for (let i = layers; i >= 1; i--) {
      const u = (i - 1) / Math.max(1, layers - 1);
      ctx.save();
      ctx.translate(cx, cy);
      if (rotStepDeg !== 0) ctx.rotate(((i * rotStepDeg) * Math.PI) / 180);
      const sc = 1 + i * scaleStep;
      ctx.scale(sc, sc);
      ctx.globalAlpha *= lerp(alphaStart, alphaEnd, u);
      drawShapeFn(ctx, i);
      ctx.restore();
    }
    ctx.restore();
    ctx.save();
    ctx.translate(cx, cy);
    drawShapeFn(ctx, 0);
    ctx.restore();
  }

  function drawEchoTextTrail(ctx, text, x, y, opts = {}) {
    const {
      echoes = 5, dxStep = -24, dyStep = 0, scaleStep = 0.04,
      alphaStart = 0.36, alphaEnd = 0.04, echoColor = null,
      ...textOpts
    } = opts;
    const baseSX = textOpts.scaleX !== undefined ? textOpts.scaleX : 1.28;
    const baseSY = textOpts.scaleY !== undefined ? textOpts.scaleY : 1.0;
    for (let i = echoes; i >= 1; i--) {
      const u = (i - 1) / Math.max(1, echoes - 1);
      ctx.save();
      ctx.globalAlpha *= lerp(alphaStart, alphaEnd, u);
      drawWideText(ctx, text, x + i * dxStep, y + i * dyStep, {
        ...textOpts,
        color: echoColor || textOpts.color || '#F4F1EA',
        scaleX: baseSX * (1 + i * scaleStep),
        scaleY: baseSY * (1 + i * scaleStep * 0.4),
      });
      ctx.restore();
    }
    drawWideText(ctx, text, x, y, textOpts);
  }

  function drawDirectionalSmearText(ctx, text, x, y, opts = {}) {
    const {
      steps = 16, dxTotal = -140, dyTotal = 0, scaleSpread = 0.08,
      alphaMax = 0.22, smearColor = null, ...textOpts
    } = opts;
    const baseSX = textOpts.scaleX !== undefined ? textOpts.scaleX : 1.28;
    const baseSY = textOpts.scaleY !== undefined ? textOpts.scaleY : 1.0;
    for (let i = steps; i >= 1; i--) {
      const u = i / steps;
      const weight = Math.pow(1 - u, 1.65) * alphaMax;
      if (weight <= 0.005) continue;
      ctx.save();
      ctx.globalAlpha *= weight;
      drawWideText(ctx, text, x + u * dxTotal, y + u * dyTotal, {
        ...textOpts,
        color: smearColor || textOpts.color || '#F4F1EA',
        scaleX: baseSX * (1 + u * scaleSpread),
        scaleY: baseSY * (1 + u * scaleSpread * 0.25),
      });
      ctx.restore();
    }
    drawWideText(ctx, text, x, y, textOpts);
  }

  function drawEchoTextWall(ctx, text, {
    rows = 5, yStart = 90, yStep = 225,
    font = '900 320px "Barlow Condensed", sans-serif',
    color = '#09090B', alpha = 0.085, scaleX = 1.08,
  } = {}) {
    ctx.save();
    ctx.globalAlpha *= alpha;
    for (let r = 0; r < rows; r++) {
      const oy = yStart + r * yStep;
      const ox = W / 2 + ((r % 2 === 0 ? -1 : 1) * 40);
      drawWideText(ctx, text, ox, oy, { font, color, scaleX });
    }
    ctx.restore();
  }

  function drawAnamorphicFlare(ctx, cx, cy, width = 1600, intensity = 0.85, color = '#FF5533') {
    ctx.save();
    ctx.globalCompositeOperation = 'screen';
    const hw = width * 0.5;
    const hg = ctx.createLinearGradient(cx - hw, cy, cx + hw, cy);
    hg.addColorStop(0, 'rgba(0,0,0,0)');
    hg.addColorStop(0.28, color + '33');
    hg.addColorStop(0.5, `rgba(255,245,225,${clamp(intensity)})`);
    hg.addColorStop(0.72, color + '33');
    hg.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = hg;
    ctx.fillRect(cx - hw, cy - 10, width, 20);

    const core = ctx.createLinearGradient(cx - hw * 0.7, cy, cx + hw * 0.7, cy);
    core.addColorStop(0, 'rgba(255,255,255,0)');
    core.addColorStop(0.5, `rgba(255,255,255,${clamp(intensity * 0.95)})`);
    core.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = core;
    ctx.fillRect(cx - hw * 0.7, cy - 2.5, width * 0.7, 5);

    const vg = ctx.createRadialGradient(cx, cy, 0, cx, cy, width * 0.22);
    vg.addColorStop(0, `rgba(255,140,85,${clamp(intensity * 0.42)})`);
    vg.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = vg;
    ctx.beginPath();
    ctx.arc(cx, cy, width * 0.22, 0, Math.PI * 2);
    ctx.fill();
    ctx.restore();
  }

  function drawInkBurst(ctx, cx, cy, {
    rays = 28, innerR = 170, outerR = 440, color = '#09090B', seed = 11, rot = 0,
  } = {}) {
    ctx.save();
    ctx.translate(cx, cy);
    if (rot) ctx.rotate(rot);
    ctx.fillStyle = color;
    for (let i = 0; i < rays; i++) {
      const ang = (i / rays) * Math.PI * 2 + (seededRand(seed + i * 3) - 0.5) * 0.16;
      const r0 = innerR + seededRand(seed + i * 7) * 75;
      const r1 = r0 + (outerR - innerR) * (0.45 + seededRand(seed + i * 11) * 0.75);
      const w0 = 0.012 + seededRand(seed + i * 13) * 0.022;
      ctx.beginPath();
      ctx.moveTo(Math.cos(ang - w0) * r0, Math.sin(ang - w0) * r0);
      ctx.lineTo(Math.cos(ang) * r1, Math.sin(ang) * r1);
      ctx.lineTo(Math.cos(ang + w0) * r0, Math.sin(ang + w0) * r0);
      ctx.closePath();
      ctx.fill();
    }
    ctx.restore();
  }

  function drawSlitWaveText(ctx, text, x, y, opts = {}) {
    const {
      slices = 16, ampX = 28, ampY = 0, phase = 0, bandH = 300,
      ...textOpts
    } = opts;
    const topY = y - bandH * 0.5;
    const sliceH = bandH / slices;
    for (let s = 0; s < slices; s++) {
      const sy = topY + s * sliceH;
      const ox = Math.sin(phase + s * 0.65) * ampX;
      const oy = Math.cos(phase + s * 0.55) * ampY;
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, sy, W, sliceH + 0.8);
      ctx.clip();
      drawWideText(ctx, text, x + ox, y + oy, textOpts);
      ctx.restore();
    }
  }

  // ── CANVAS2D VECTOR TYPOGRAPHY PRIMITIVES ──
  function drawWideText(ctx, text, x, y, {
    font = '900 220px "Archivo Black", sans-serif',
    color = '#F4F1EA',
    scaleX = 1.28,
    scaleY = 1.0,
    align = 'center',
    baseline = 'middle',
    strokeColor = null,
    strokeWidth = 3,
    shadowColor = null,
    shadowBlur = 0,
  } = {}) {
    ctx.save();
    ctx.font = font;
    ctx.textAlign = align;
    ctx.textBaseline = baseline;
    ctx.translate(x, y);
    ctx.scale(scaleX, scaleY);
    if (shadowColor && shadowBlur > 0) {
      ctx.shadowColor = shadowColor;
      ctx.shadowBlur = shadowBlur;
    }
    if (strokeColor) {
      ctx.strokeStyle = strokeColor;
      ctx.lineWidth = strokeWidth;
      ctx.strokeText(text, 0, 0);
    }
    if (color && color !== 'transparent') {
      ctx.fillStyle = color;
      ctx.fillText(text, 0, 0);
    }
    ctx.restore();
  }

  /**
   * Exact proportional per-character renderer using ctx.measureText() advance widths.
   * Eliminates fixed-pitch kerning gaps around narrow glyphs like 'I'.
   */
  function drawProportionalChars(ctx, text, x, y, {
    font = '300 185px "Inter", sans-serif',
    color = '#0A0A0A',
    align = 'left',
    letterSpacing = 0,
    scaleX = 1.0,
    perChar = null, // (ch, idx, cx, cy) => { dx, dy, rotDeg, sx, sy, alpha }
  } = {}) {
    ctx.save();
    ctx.font = font;
    ctx.textBaseline = 'alphabetic';
    ctx.textAlign = 'left';

    const chars = text.split('');
    const widths = chars.map((ch) => ctx.measureText(ch).width * scaleX + letterSpacing);
    const totalW = widths.reduce((a, b) => a + b, 0) - letterSpacing;
    let cursorX = align === 'center' ? x - totalW / 2 : (align === 'right' ? x - totalW : x);

    for (let i = 0; i < chars.length; i++) {
      const ch = chars[i];
      const w = widths[i];
      const tr = perChar ? perChar(ch, i, cursorX, y) : {};
      const dx = tr.dx || 0;
      const dy = tr.dy || 0;
      const rot = ((tr.rotDeg || 0) * Math.PI) / 180;
      const sx = tr.sx !== undefined ? tr.sx : scaleX;
      const sy = tr.sy !== undefined ? tr.sy : 1.0;
      const alpha = tr.alpha !== undefined ? tr.alpha : 1.0;

      if (alpha > 0.01) {
        ctx.save();
        ctx.globalAlpha *= alpha;
        ctx.translate(cursorX + w * 0.5 + dx, y + dy);
        if (rot !== 0) ctx.rotate(rot);
        ctx.scale(sx, sy);
        ctx.fillStyle = tr.color || color;
        ctx.fillText(ch, -(w / scaleX) * 0.5, 0);
        ctx.restore();
      }
      cursorX += w;
    }
    ctx.restore();
  }

  function drawDiagonalSliceText(ctx, text, cx, cy, {
    font = '900 420px "Barlow Condensed", sans-serif',
    color = '#09090B',
    scaleX = 1.15,
    sliceOffset = 0,
    sliceY0 = 35,
    sliceY1 = -35,
    showLine = false,
    lineColor = '#F4F1EA',
    lineWidth = 6,
  } = {}) {
    const drawHalf = (isTop, ox, oy) => {
      ctx.save();
      ctx.beginPath();
      if (isTop) {
        ctx.moveTo(0, 0);
        ctx.lineTo(W, 0);
        ctx.lineTo(W, cy + sliceY1);
        ctx.lineTo(0, cy + sliceY0);
      } else {
        ctx.moveTo(0, cy + sliceY0);
        ctx.lineTo(W, cy + sliceY1);
        ctx.lineTo(W, H);
        ctx.lineTo(0, H);
      }
      ctx.closePath();
      ctx.clip();
      drawWideText(ctx, text, cx + ox, cy + oy, { font, color, scaleX });
      ctx.restore();
    };

    drawHalf(true, sliceOffset, -sliceOffset * 0.32);
    drawHalf(false, -sliceOffset, sliceOffset * 0.32);

    if (showLine) {
      ctx.save();
      ctx.strokeStyle = lineColor;
      ctx.lineWidth = lineWidth;
      ctx.shadowColor = lineColor;
      ctx.shadowBlur = 18;
      ctx.beginPath();
      ctx.moveTo(0, cy + sliceY0);
      ctx.lineTo(W, cy + sliceY1);
      ctx.stroke();
      ctx.restore();
    }
  }

  // ── RENDERER-AGNOSTIC LAYER REGISTRY TYPES (SYNCED WITH scene_spec.schema.json) ──
  const LAYER_REGISTRY_TYPES = {
    canvas2d: [
      'panel_bg', 'wide_text', 'animated_text', 'proportional_chars',
      'floor_mask_stagger', 'fluid_wave_text', 'slit_wave_text',
      'directional_smear_text', 'echo_text_trail', 'echo_text_wall',
      'diagonal_slice_text', 'echo_shapes', 'embers', 'center_flare',
      'anamorphic_flare', 'ink_burst', 'radial_burst', 'brand_logo', 'framed_media',
    ],
    webgl: [
      'webgl_bg', 'text_plane', 'canvas_texture', 'mesh_cube',
      'mesh_plane', 'mesh_group', 'light_directional', 'light_ambient',
      'particle_field', 'post_fx',
    ],
  };

  // ── THREE.JS WEBGL 3D CUBE RENDERER (WITH SOFTWARE FALLBACK) ──
  const PBRCube3D = {
    initialized: false,
    useWebGL: false,
    canvas: null,
    renderer: null,
    scene: null,
    camera: null,
    mesh: null,

    init() {
      if (this.initialized) return;
      this.initialized = true;
      if (!global.THREE) return;
      try {
        const c = document.createElement('canvas');
        c.width = 560;
        c.height = 560;
        const renderer = new global.THREE.WebGLRenderer({
          canvas: c,
          alpha: true,
          antialias: true,
          preserveDrawingBuffer: true,
        });
        renderer.setSize(560, 560, false);
        const scene = new global.THREE.Scene();
        const camera = new global.THREE.PerspectiveCamera(32, 1, 0.1, 100);
        camera.position.set(0, 0, 5.4);

        // Beveled / chamfered box via ExtrudeGeometry of a rounded square
        const s = 0.88;
        const r = 0.08;
        const shape = new global.THREE.Shape();
        shape.moveTo(-s + r, -s);
        shape.lineTo(s - r, -s);
        shape.quadraticCurveTo(s, -s, s, -s + r);
        shape.lineTo(s, s - r);
        shape.quadraticCurveTo(s, s, s - r, s);
        shape.lineTo(-s + r, s);
        shape.quadraticCurveTo(-s, s, -s, s - r);
        shape.lineTo(-s, -s + r);
        shape.quadraticCurveTo(-s, -s, -s + r, -s);

        const geo = new global.THREE.ExtrudeGeometry(shape, {
          depth: 1.66,
          bevelEnabled: true,
          bevelThickness: 0.06,
          bevelSize: 0.06,
          bevelSegments: 3,
        });
        geo.center();

        const mat = new global.THREE.MeshStandardMaterial({
          color: 0xf02b1e,
          roughness: 0.30,
          metalness: 0.05,
        });
        const mesh = new global.THREE.Mesh(geo, mat);
        scene.add(mesh);

        const amb = new global.THREE.AmbientLight(0xffffff, 1.15);
        scene.add(amb);
        const topLight = new global.THREE.DirectionalLight(0xffc8a0, 2.8);
        topLight.position.set(-1.0, 5.0, 2.5);
        scene.add(topLight);
        const rimLight = new global.THREE.DirectionalLight(0xff4030, 0.55);
        rimLight.position.set(3.0, -1.0, 2.0);
        scene.add(rimLight);

        this.canvas = c;
        this.renderer = renderer;
        this.scene = scene;
        this.camera = camera;
        this.mesh = mesh;
        this.useWebGL = true;
      } catch (e) {
        this.useWebGL = false;
      }
    },

    draw(ctx, cx, cy, pitchDeg, yawDeg, size = 480, shadowScale = 1.0) {
      this.init();
      // Soft elliptical contact shadow
      ctx.save();
      const sg = ctx.createRadialGradient(cx, cy + size * 0.43, 8, cx, cy + size * 0.43, size * 0.34 * shadowScale);
      sg.addColorStop(0, 'rgba(0,0,0,0.34)');
      sg.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = sg;
      ctx.beginPath();
      ctx.ellipse(cx, cy + size * 0.43, size * 0.34 * shadowScale, size * 0.075 * shadowScale, 0, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();

      if (this.useWebGL) {
        this.mesh.rotation.set((pitchDeg * Math.PI) / 180, (yawDeg * Math.PI) / 180, 0);
        this.renderer.render(this.scene, this.camera);
        ctx.drawImage(this.canvas, cx - size / 2, cy - size / 2, size, size);
        return;
      }

      // Software 3D fallback with directional face shading
      const rx = (-pitchDeg * Math.PI) / 180;
      const ry = (yawDeg * Math.PI) / 180;
      const cxR = Math.cos(rx), sxR = Math.sin(rx);
      const cyR = Math.cos(ry), syR = Math.sin(ry);
      const verts = [
        [-1,-1,-1],[1,-1,-1],[1,1,-1],[-1,1,-1],
        [-1,-1, 1],[1,-1, 1],[1,1, 1],[-1,1, 1],
      ].map(([x, y, z]) => {
        const x1 = x * cyR + z * syR;
        const z1 = -x * syR + z * cyR;
        const y2 = y * cxR - z1 * sxR;
        const z2 = y * sxR + z1 * cxR;
        return [x1, y2, z2];
      });
      const focal = 4.4;
      const proj = verts.map(([x, y, z]) => {
        const s = focal / (focal - z);
        return [cx + x * size * 0.25 * s, cy - y * size * 0.25 * s, z];
      });
      const faces = [[4,5,6,7],[1,0,3,2],[0,4,7,3],[5,1,2,6],[3,7,6,2],[0,1,5,4]];
      const vis = [];
      for (const idx of faces) {
        const [a,b,c,d] = idx.map((i) => verts[i]);
        const nx = (b[1]-a[1])*(c[2]-a[2]) - (b[2]-a[2])*(c[1]-a[1]);
        const ny = (b[2]-a[2])*(c[0]-a[0]) - (b[0]-a[0])*(c[2]-a[2]);
        const nz = (b[0]-a[0])*(c[1]-a[1]) - (b[1]-a[1])*(c[0]-a[0]);
        if (nz <= 0.01) continue;
        const nLen = Math.hypot(nx, ny, nz);
        const dot = (-0.25*nx + 0.88*ny + 0.42*nz) / nLen;
        const fill = ny / nLen > 0.55 ? '#F28B56' : (dot > 0.2 ? '#EA261B' : (dot > -0.1 ? '#CC1D15' : '#A4150E'));
        vis.push({ z: (a[2]+b[2]+c[2]+d[2])*0.25, idx, fill });
      }
      vis.sort((u, v) => u.z - v.z);
      ctx.save();
      for (const v of vis) {
        ctx.fillStyle = v.fill;
        ctx.beginPath();
        v.idx.forEach((vi, k) => (k === 0 ? ctx.moveTo(proj[vi][0], proj[vi][1]) : ctx.lineTo(proj[vi][0], proj[vi][1])));
        ctx.closePath();
        ctx.fill();
      }
      ctx.restore();
    },
  };

  // ── REAL MEDIA INSERT HELPER (For User Photos/Videos in Future Projects) ──
  function drawFramedMediaInsert(ctx, imgOrCanvas, x, y, w, h, { radius = 16, border = '#444', rotDeg = 0 } = {}) {
    ctx.save();
    ctx.translate(x + w / 2, y + h / 2);
    if (rotDeg) ctx.rotate((rotDeg * Math.PI) / 180);
    ctx.beginPath();
    ctx.roundRect(-w / 2, -h / 2, w, h, radius);
    ctx.clip();
    if (imgOrCanvas) ctx.drawImage(imgOrCanvas, -w / 2, -h / 2, w, h);
    ctx.restore();
    ctx.save();
    ctx.translate(x + w / 2, y + h / 2);
    if (rotDeg) ctx.rotate((rotDeg * Math.PI) / 180);
    ctx.strokeStyle = border;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.roundRect(-w / 2, -h / 2, w, h, radius);
    ctx.stroke();
    ctx.restore();
  }

  // ── V5 TRANSITION, ENTRANCE & OPTICAL FINISH PRIMITIVES ──
  function applyWhipTransition(ctx, {
    f = 0, startF = 0, endF = 1000,
    inFrames = 5, outFrames = 4,
    inDir = [0, 0], outDir = [0, 0],
    zoomIn = 1.0, zoomOut = 1.0,
    rotIn = 0, rotOut = 0,
  } = {}) {
    let dx = 0, dy = 0, z = 1.0, rot = 0;
    if (inFrames > 0 && f < startF + inFrames) {
      const pIn = expoOut(prog(f, startF, startF + inFrames));
      dx += lerp(inDir[0], 0, pIn);
      dy += lerp(inDir[1], 0, pIn);
      z *= lerp(zoomIn, 1.0, pIn);
      rot += lerp(rotIn, 0, pIn);
    }
    if (outFrames > 0 && f > endF - outFrames) {
      const pOut = easeIn(prog(f, endF - outFrames, endF), 2.6);
      dx += lerp(0, outDir[0], pOut);
      dy += lerp(0, outDir[1], pOut);
      z *= lerp(1.0, zoomOut, pOut);
      rot += lerp(0, rotOut, pOut);
    }
    if (dx !== 0 || dy !== 0 || z !== 1.0 || rot !== 0) {
      ctx.translate(W / 2, H / 2);
      ctx.scale(z, z);
      if (rot !== 0) ctx.rotate((rot * Math.PI) / 180);
      ctx.translate(-W / 2 + dx, -H / 2 + dy);
    }
  }

  function drawAnimatedText(ctx, text, x, y, opts = {}) {
    const {
      f = 0, startF = 0, dur = 7, mode = 'slideUpMask',
      fromX = 420, cursor = false,
      font = '900 220px "Archivo Black", sans-serif',
      color = '#F4F1EA',
      scaleX = 1.28,
      scaleY = 1.0,
      align = 'center',
      baseline = 'middle',
      strokeColor = null,
      strokeWidth = 3,
      shadowColor = null,
      shadowBlur = 0,
      letterSpacing = 0,
    } = opts;
    if (f < startF) return;
    const p = prog(f, startF, startF + Math.max(0.1, dur));
    const textOpts = { font, color, scaleX, scaleY, align, baseline, strokeColor, strokeWidth, shadowColor, shadowBlur };

    if (mode === 'slideUpMask') {
      const e = Anim.evalEase('expoOut', p, 1.0);
      const m = font.match(/(\d+(?:\.\d+)?)px/);
      const fs = m ? parseFloat(m[1]) : 160;
      const bandTop = baseline === 'alphabetic' ? y - fs * 1.15 : y - fs * 0.72;
      const bandH = fs * 1.55;
      ctx.save();
      ctx.beginPath();
      ctx.rect(0, bandTop, W, bandH);
      ctx.clip();
      ctx.globalAlpha *= clamp(p * 2.5);
      drawWideText(ctx, text, x, y + lerp(fs * 0.65, 0, e), textOpts);
      ctx.restore();
    } else if (mode === 'slamScale') {
      const sc = lerp(1.45, 1.0, Anim.evalEase({ type: 'overshoot', s: 1.35 }, p, 1.0));
      ctx.save();
      ctx.globalAlpha *= clamp(p * 3.0);
      drawWideText(ctx, text, x, y, { ...textOpts, scaleX: scaleX * sc, scaleY: scaleY * sc });
      ctx.restore();
    } else if (mode === 'letterWave') {
      const yBase = baseline === 'middle' ? y + (parseFloat((font.match(/(\d+(?:\.\d+)?)px/) || [0, 160])[1]) * 0.34) : y;
      drawProportionalChars(ctx, text, x, yBase, {
        font, color, align, letterSpacing, scaleX,
        perChar: (ch, i) => {
          const st = startF + i * 0.9;
          const lp = prog(f, st, st + Math.max(3, dur * 0.65));
          return { dy: lerp(120, 0, Anim.evalEase('expoOut', lp, 1.0)), alpha: clamp(lp * 2.5) };
        },
      });
    } else if (mode === 'typewriter') {
      const n = Math.max(1, Math.ceil(p * text.length));
      const shown = text.slice(0, n) + (cursor && p < 1.0 && Math.floor(f / 2) % 2 === 0 ? '|' : '');
      drawWideText(ctx, shown, x, y, textOpts);
    } else if (mode === 'stretchWhip') {
      const e = Anim.evalEase('expoOut', p, 1.0);
      ctx.save();
      ctx.globalAlpha *= clamp(p * 3.0);
      drawWideText(ctx, text, x + lerp(fromX, 0, e), y, { ...textOpts, scaleX: scaleX * lerp(1.55, 1.0, e) });
      ctx.restore();
    } else {
      drawWideText(ctx, text, x, y, textOpts);
    }
  }

  function drawCrossSceneMask(ctx, renderOldFn, renderNewFn, buildMaskPathFn) {
    ctx.save();
    renderOldFn(ctx);
    ctx.restore();
    ctx.save();
    const maskPath = buildMaskPathFn(ctx);
    if (maskPath) ctx.clip(maskPath);
    renderNewFn(ctx);
    ctx.restore();
  }

  function impactScale(f, hitF, amp = 0.075) {
    const d = f - hitF;
    if (d < 0 || d > 8) return 1.0;
    return 1.0 + amp * Math.exp(-d * 0.55) * Math.cos(d * 1.4);
  }

  function drawImpactHit(ctx, f, hitF, { cx = W / 2, cy = H / 2, color = '#FF4D2E', maxR = 520, dur = 6 } = {}) {
    const d = f - hitF;
    if (d < 0 || d > dur) return;
    const p = clamp(d / dur);
    const al = 1 - easeOut(p, 2);
    ctx.save();
    ctx.globalCompositeOperation = 'screen';
    const fg = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxR * (0.4 + p * 0.6));
    fg.addColorStop(0, `rgba(255,240,210,${0.32 * al})`);
    fg.addColorStop(0.35, `rgba(255,77,46,${0.22 * al})`);
    fg.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = fg;
    ctx.beginPath();
    ctx.arc(cx, cy, maxR, 0, Math.PI * 2);
    ctx.fill();

    ctx.strokeStyle = color;
    ctx.globalAlpha = 0.65 * al;
    ctx.lineWidth = lerp(8, 1.5, p);
    ctx.beginPath();
    ctx.arc(cx, cy, lerp(80, maxR, easeOut(p, 2)), 0, Math.PI * 2);
    ctx.stroke();
    ctx.restore();
  }

  function drawFloorMaskStagger(ctx, text, x, y, opts = {}) {
    const {
      f = 0, startF = 0, dur = 10, stagger = 2.0, riseDist = 260, floorPad = 14,
      font = '900 280px "Archivo Black", sans-serif',
      color = '#F4F1EA', align = 'center', letterSpacing = 0, scaleX = 1.24,
    } = opts;
    if (f < startF) return;
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, W, y + floorPad);
    ctx.clip();
    drawProportionalChars(ctx, text, x, y, {
      font, color, align, letterSpacing, scaleX,
      perChar: (ch, i) => {
        const st = startF + i * stagger;
        const p = prog(f, st, st + dur);
        const s = Anim.evalEase({ type: 'spring', stiffness: 260, damping: 18 }, p, 1.0);
        return { dy: lerp(riseDist, 0, s), alpha: clamp(p * 3.0) };
      },
    });
    ctx.restore();
  }

  function drawFluidWaveText(ctx, text, x, y, opts = {}) {
    const {
      f = 0, startF = 0, endF = 30, waveAmp = 14, morphP = 0,
      font = '900 260px "Archivo Black", sans-serif',
      color = '#F4F1EA', hotColor = '#E2261C', align = 'center', letterSpacing = 8, scaleX = 1.24,
    } = opts;
    const sweepPos = prog(f, startF, endF) * (text.length + 1.5) - 0.5;
    drawProportionalChars(ctx, text, x, y, {
      font, color, align, letterSpacing, scaleX: scaleX * lerp(1.0, 0.88, morphP),
      perChar: (ch, i) => {
        const dist = Math.abs(i - sweepPos);
        const isHot = dist < 0.95;
        return {
          dy: Math.sin(f * 0.28 + i * 0.85) * waveAmp,
          rotDeg: Math.cos(f * 0.22 + i * 0.7) * 3.5,
          sx: scaleX * lerp(1.0, 0.82, morphP),
          color: isHot ? hotColor : color,
        };
      },
    });
  }

  let _grainCanvas = null;
  function getGrainCanvas() {
    if (_grainCanvas) return _grainCanvas;
    const c = document.createElement('canvas');
    c.width = 128;
    c.height = 128;
    const gctx = c.getContext('2d');
    const img = gctx.createImageData(128, 128);
    const d = img.data;
    for (let i = 0; i < 128 * 128; i++) {
      const v = Math.floor(seededRand(i * 1.37 + 17) * 255);
      const o = i * 4;
      d[o] = v; d[o + 1] = v; d[o + 2] = v; d[o + 3] = 255;
    }
    gctx.putImageData(img, 0, 0);
    _grainCanvas = c;
    return c;
  }

  let _bloomCanvas = null;
  function getBloomCanvas() {
    if (_bloomCanvas) return _bloomCanvas;
    const c = document.createElement('canvas');
    c.width = 240;
    c.height = 135;
    _bloomCanvas = c;
    return c;
  }

  function applyOpticalFinish(ctx, t, { bloomAlpha = 0.22, grainAlpha = 0.03, vignetteAlpha = 0.20 } = {}) {
    if (bloomAlpha > 0) {
      const bc = getBloomCanvas();
      const bctx = bc.getContext('2d');
      bctx.clearRect(0, 0, bc.width, bc.height);
      bctx.save();
      bctx.filter = 'blur(5px)';
      bctx.drawImage(ctx.canvas, 0, 0, bc.width, bc.height);
      bctx.restore();
      ctx.save();
      ctx.globalCompositeOperation = 'screen';
      ctx.globalAlpha = bloomAlpha;
      ctx.drawImage(bc, 0, 0, W, H);
      ctx.restore();
    }
    if (vignetteAlpha > 0) {
      ctx.save();
      const vg = ctx.createRadialGradient(W / 2, H / 2, H * 0.34, W / 2, H / 2, W * 0.68);
      vg.addColorStop(0, 'rgba(0,0,0,0)');
      vg.addColorStop(1, `rgba(0,0,0,${vignetteAlpha})`);
      ctx.fillStyle = vg;
      ctx.fillRect(0, 0, W, H);
      ctx.restore();
    }
    if (grainAlpha > 0) {
      const gc = getGrainCanvas();
      const fi = Math.floor(t * 30);
      const ox = Math.floor(seededRand(fi * 7.1 + 3) * 128);
      const oy = Math.floor(seededRand(fi * 13.7 + 9) * 128);
      ctx.save();
      ctx.globalAlpha = grainAlpha;
      ctx.globalCompositeOperation = 'overlay';
      const pat = ctx.createPattern(gc, 'repeat');
      ctx.translate(-ox, -oy);
      ctx.fillStyle = pat;
      ctx.fillRect(ox, oy, W, H);
      ctx.restore();
    }
  }

  // ── CUT-CLAMPED ADAPTIVE 4x/12x SUB-FRAME TEMPORAL SHUTTER ACCUMULATOR ──
  function createRenderer(canvasEl, renderSubframeFn, {
    fps = 30,
    shutterSamples = 4,
    shutterAngle = 180,
    highMotionSamples = 12,
    highMotionAngle = 280,
    isHighMotionFn = null,
    sceneCuts = [],
    opticalFinish = true,
  } = {}) {
    const mainCtx = canvasEl.getContext('2d');
    const offCanvas = document.createElement('canvas');
    offCanvas.width = W;
    offCanvas.height = H;
    const offCtx = offCanvas.getContext('2d');

    return function renderFrame(t) {
      const fCur = t * fps;
      let cutF = 0;
      for (let i = 0; i < sceneCuts.length; i++) {
        if (sceneCuts[i] <= fCur + 0.001) cutF = sceneCuts[i];
        else break;
      }
      const minT = cutF / fps;
      const isHigh = isHighMotionFn ? !!isHighMotionFn(t) : false;
      const samples = isHigh ? highMotionSamples : shutterSamples;
      const angle = isHigh ? highMotionAngle : shutterAngle;
      const shutterDt = (angle / 360) / fps;
      mainCtx.clearRect(0, 0, W, H);
      for (let k = 0; k < samples; k++) {
        const tk = Math.max(minT, t - (k / samples) * shutterDt);
        offCtx.setTransform(1, 0, 0, 1, 0, 0);
        offCtx.globalAlpha = 1;
        offCtx.clearRect(0, 0, W, H);
        if (global.Samurai) {
          global.Samurai.currentT = tk;
          global.Samurai.currentSample = k;
        }
        offCtx.save();
        renderSubframeFn(offCtx, tk, k);
        offCtx.restore();
        mainCtx.save();
        mainCtx.globalAlpha = 1 / (k + 1);
        mainCtx.drawImage(offCanvas, 0, 0);
        mainCtx.restore();
      }
      if (opticalFinish) {
        applyOpticalFinish(mainCtx, t);
      }
    };
  }

  global.Samurai = {
    W, H,
    LAYER_REGISTRY_TYPES,
    Anim,
    clamp, lerp, prog,
    easeIn, easeOut, easeInOut, expoOut, whipInOut, easeOutBack, spring, anticipate, seededRand,
    applyCamera, applyWhipTransition,
    drawPanelBg, drawEmbers, drawCenterFlare, drawRadialBurst,
    drawEchoShapes, drawEchoTextTrail, drawDirectionalSmearText, drawEchoTextWall, drawAnamorphicFlare, drawInkBurst, drawSlitWaveText,
    drawWideText, drawAnimatedText, drawProportionalChars, drawDiagonalSliceText,
    drawFloorMaskStagger, drawFluidWaveText, drawImpactHit, impactScale,
    drawCrossSceneMask, applyOpticalFinish,
    PBRCube3D, drawFramedMediaInsert, createRenderer,
  };
})(window);
