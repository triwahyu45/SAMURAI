/**
 * Samurai Canvas2D Scene Spec Runner (Fase 6a)
 * Pure stateless execution of scene_spec.json via Samurai.Anim.solve & LAYER_REGISTRY_TYPES.canvas2d.
 * Zero silent fallback on unknown renderer or layer types.
 */
(function (global) {
  'use strict';

  function solveTrack(track, t, fallback = undefined) {
    if (track === undefined) return fallback;
    return global.Samurai.Anim.solve(track, t);
  }

  function resolveColor(baseColor, alpha) {
    if (alpha === undefined || alpha === null) return baseColor;
    if (typeof baseColor === 'string' && baseColor.startsWith('#') && (baseColor.length === 7 || baseColor.length === 4)) {
      let r, g, b;
      if (baseColor.length === 7) {
        r = parseInt(baseColor.slice(1, 3), 16);
        g = parseInt(baseColor.slice(3, 5), 16);
        b = parseInt(baseColor.slice(5, 7), 16);
      } else {
        r = parseInt(baseColor[1] + baseColor[1], 16);
        g = parseInt(baseColor[2] + baseColor[2], 16);
        b = parseInt(baseColor[3] + baseColor[3], 16);
      }
      return `rgba(${r},${g},${b},${alpha})`;
    }
    return baseColor;
  }

  const CANVAS2D_HANDLERS = {
    panel_bg(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      S.drawPanelBg(ctx, p.c1 || '#070709', p.c2 !== undefined ? p.c2 : null, p.dotsMode || 'dark', t, p.opts || {});
    },
    wide_text(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      const tr = layer.tracks || {};
      const tf = layer.transform || {};
      const x = solveTrack(tf.x, t, p.x !== undefined ? p.x : S.W / 2);
      const y = solveTrack(tf.y, t, p.y !== undefined ? p.y : S.H / 2);
      const alpha = solveTrack(tr.alpha, t, undefined);
      const color = resolveColor(p.color || '#F4F1EA', alpha);
      S.drawWideText(ctx, p.text || '', x, y, { ...(p.opts || {}), color });
    },
    animated_text(ctx, layer, t, fps) {
      const S = global.Samurai;
      const p = layer.props || {};
      const tf = layer.transform || {};
      const x = solveTrack(tf.x, t, p.x !== undefined ? p.x : S.W / 2);
      const y = solveTrack(tf.y, t, p.y !== undefined ? p.y : S.H / 2);
      S.drawAnimatedText(ctx, p.text || '', x, y, { ...(p.opts || {}), f: t * fps });
    },
    proportional_chars(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      const tf = layer.transform || {};
      const x = solveTrack(tf.x, t, p.x !== undefined ? p.x : S.W / 2);
      const y = solveTrack(tf.y, t, p.y !== undefined ? p.y : S.H / 2);
      S.drawProportionalChars(ctx, p.text || '', x, y, p.opts || {});
    },
    floor_mask_stagger(ctx, layer, t, fps) {
      const S = global.Samurai;
      const p = layer.props || {};
      const tf = layer.transform || {};
      const x = solveTrack(tf.x, t, p.x !== undefined ? p.x : S.W / 2);
      const y = solveTrack(tf.y, t, p.y !== undefined ? p.y : S.H / 2);
      S.drawFloorMaskStagger(ctx, p.text || '', x, y, { ...(p.opts || {}), f: t * fps });
    },
    fluid_wave_text(ctx, layer, t, fps) {
      const S = global.Samurai;
      const p = layer.props || {};
      S.drawFluidWaveText(ctx, p.text || '', p.x || S.W / 2, p.y || S.H / 2, { ...(p.opts || {}), f: t * fps });
    },
    slit_wave_text(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      const tr = layer.tracks || {};
      const progVal = solveTrack(tr.progress, t, p.progress || 0);
      S.drawSlitWaveText(ctx, p.text || '', p.x || S.W / 2, p.y || S.H / 2, progVal, p.opts || {});
    },
    directional_smear_text(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      S.drawDirectionalSmearText(ctx, p.text || '', p.x || S.W / 2, p.y || S.H / 2, p.opts || {});
    },
    echo_text_trail(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      const tr = layer.tracks || {};
      const tf = layer.transform || {};
      const x = solveTrack(tf.x, t, p.x !== undefined ? p.x : S.W / 2);
      const y = solveTrack(tf.y, t, p.y !== undefined ? p.y : S.H / 2);
      const dxStep = solveTrack(tr.dxStep, t, (p.opts && p.opts.dxStep) !== undefined ? p.opts.dxStep : -28);
      S.drawEchoTextTrail(ctx, p.text || '', x, y, { ...(p.opts || {}), dxStep });
    },
    echo_text_wall(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      const tr = layer.tracks || {};
      const progress = solveTrack(tr.progress, t, p.progress || 0);
      S.drawEchoTextWall(ctx, p.text || '', p.x || S.W / 2, p.y || S.H / 2, progress, p.opts || {});
    },
    diagonal_slice_text(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      const tr = layer.tracks || {};
      const progress = solveTrack(tr.progress, t, p.progress || 0);
      S.drawDiagonalSliceText(ctx, p.text || '', p.x || S.W / 2, p.y || S.H / 2, progress, p.opts || {});
    },
    echo_shapes() { throw new Error('echo_shapes requires procedural callback; not implemented in declarative runner yet'); },
    embers(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      S.drawEmbers(ctx, t, p.count || 20, p.cx || S.W / 2, p.cy || S.H / 2, p.rx || 1600, p.ry || 900, p.color || '#FF5A2E', p.alpha !== undefined ? p.alpha : 0.4);
    },
    center_flare(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      const tr = layer.tracks || {};
      const r = solveTrack(tr.radius, t, p.radius || 42);
      const alpha = solveTrack(tr.alpha, t, p.alpha !== undefined ? p.alpha : 0.9);
      S.drawCenterFlare(ctx, p.cx || S.W / 2, p.cy || S.H / 2, r, alpha, p.spikes !== undefined ? p.spikes : 0, p.rot || 0);
    },
    anamorphic_flare(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      const tr = layer.tracks || {};
      const w = solveTrack(tr.width, t, p.width || 1850);
      const alpha = solveTrack(tr.alpha, t, p.alpha !== undefined ? p.alpha : 0.88);
      S.drawAnamorphicFlare(ctx, p.cx || S.W / 2, p.cy || S.H * 0.52, w, alpha, p.color || '#E2261C');
    },
    ink_burst(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      const tr = layer.tracks || {};
      const progress = solveTrack(tr.progress, t, p.progress || 0);
      S.drawInkBurst(ctx, p.cx || S.W / 2, p.cy || S.H / 2, progress, p.opts || {});
    },
    radial_burst(ctx, layer, t) {
      const S = global.Samurai;
      const p = layer.props || {};
      S.drawRadialBurst(ctx, p.cx || S.W / 2, p.cy || S.H / 2, p.innerR || 40, p.outerR || 900, p.count || 24, p.color || '#F4F1EA', p.alpha || 0.25, p.rot || 0);
    },
    brand_logo() { throw new Error('brand_logo is workspace-external'); },
    framed_media() { throw new Error('framed_media requires media asset binding'); },
  };

  function createSpecRunner(canvas, spec) {
    const S = global.Samurai;
    if (!spec || !spec.meta || spec.meta.renderer !== 'canvas2d') {
      throw new Error(`SpecRunner requires meta.renderer === "canvas2d", got "${spec && spec.meta && spec.meta.renderer}"`);
    }
    const allowed = new Set(S.LAYER_REGISTRY_TYPES.canvas2d);
    for (const layer of spec.layers) {
      if (!allowed.has(layer.type) || !CANVAS2D_HANDLERS[layer.type]) {
        throw new Error(`Unsupported canvas2d layer type: "${layer.type}" (no silent fallback)`);
      }
    }

    const fps = spec.meta.fps || 30;
    const shutterSamples = spec.meta.shutter_samples || 4;
    const shutterAngle = spec.meta.shutter_angle !== undefined ? spec.meta.shutter_angle : 180;
    const trWithShutter = (spec.transitions || []).find((tr) => tr.params && (tr.params.high_motion_windows || tr.params.scene_cuts));
    const hmWindows = (trWithShutter && trWithShutter.params.high_motion_windows) || [];
    const hmSamples = (trWithShutter && trWithShutter.params.high_motion_samples) || 12;
    const hmAngle = (trWithShutter && trWithShutter.params.high_motion_angle) || 280;
    const sceneCuts = (trWithShutter && trWithShutter.params.scene_cuts) || [];
    const layersSorted = [...spec.layers].sort((a, b) => (a.z || 0) - (b.z || 0));

    return S.createRenderer(canvas, (ctx, tk) => {
      const f = tk * fps;
      // Find active scene (using exact legacy boundary semantics where applicable)
      const activeScene = spec.scenes.find((sc) => f >= sc.start_frame && f <= sc.end_frame + 0.5) || spec.scenes[0];
      const activeLayers = layersSorted.filter((ly) => {
        if (ly.scene_id && activeScene && ly.scene_id !== activeScene.id) return false;
        const vis = solveTrack(ly.tracks && ly.tracks.visible, tk, 1);
        return vis >= 0.5;
      });

      // Pre-camera layers (panel_bg and any layer with props.in_camera === false)
      for (const ly of activeLayers) {
        if (ly.type === 'panel_bg' || (ly.props && ly.props.in_camera === false)) {
          CANVAS2D_HANDLERS[ly.type](ctx, ly, tk, fps);
        }
      }

      // Camera + whip transition block
      ctx.save();
      const cam = spec.camera || {};
      const camZoom = solveTrack(cam.zoom, tk, 1.0);
      const camX = solveTrack(cam.position && cam.position.x, tk, 0);
      const camY = solveTrack(cam.position && cam.position.y, tk, 0);
      const camRot = solveTrack(cam.rotZ, tk, 0);
      const camTr = (activeScene && spec.transitions)
        ? spec.transitions.find((tr) => tr.type === 'whip_pan' && tr.params && tr.params.scene_id === activeScene.id)
        : null;
      const driftStart = (camTr && camTr.params.drift_start !== undefined) ? camTr.params.drift_start : activeScene.start_frame;
      const driftEnd = (camTr && camTr.params.drift_end !== undefined) ? camTr.params.drift_end : activeScene.end_frame;
      const driftZoom = (camTr && camTr.params.drift_zoom !== undefined) ? camTr.params.drift_zoom : 0.045;
      S.applyCamera(ctx, {
        x: camX,
        y: camY,
        zoom: camZoom,
        rotDeg: camRot,
        driftT: S.prog(f, driftStart, driftEnd),
        driftZoom,
        t: tk,
      });

      if (camTr && camTr.params && camTr.params.whip) {
        S.applyWhipTransition(ctx, { ...(camTr.params.whip), f });
      }

      for (const ly of activeLayers) {
        if (ly.type === 'panel_bg' || (ly.props && ly.props.in_camera === false)) continue;
        CANVAS2D_HANDLERS[ly.type](ctx, ly, tk, fps);
      }
      ctx.restore();
    }, {
      fps,
      shutterSamples,
      shutterAngle,
      highMotionSamples: hmSamples,
      highMotionAngle: hmAngle,
      sceneCuts,
      isHighMotionFn: (tk) => {
        const ff = tk * fps;
        return hmWindows.some(([a, b]) => ff >= a && ff <= b);
      },
      opticalFinish: true,
    });
  }

  global.SamuraiSpecRunner = { createSpecRunner };
})(window);
