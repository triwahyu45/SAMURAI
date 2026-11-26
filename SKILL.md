---
name: SAMURAI
description: Use when validating or rendering a scene_spec.json file into MP4 video, muxing audio to loudness targets, or running automated post-render QA metrics (validasi, render video dari spec, cek QA). Do NOT use when writing a creative brief, treatment, storyboard, timeline, or choosing visual style.
---

# Samurai — Katana Motion Execution & QA Engine

Pure deterministic rendering and post-render QA engine supporting dual backends (`canvas2d` and `webgl`). Consumes `scene_spec.json` validated against `schema/scene_spec.schema.json` and produces MP4 video + `qa_report.json`.

---

## Hard Rules (Non-Negotiable)

1. **Zero Creative Decisions**: NEVER choose or override creative style, color choices, timing, or renderer backend. Read `scene_spec.json` verbatim and execute. `dials = metadata, tidak mengubah render` (Engine never branches rendering behavior on `dials.register` or other `dials` fields). If invoked on a spec without a brief, render immediately — NEVER ask creative questions.
2. **Strict Schema Rejection**: ALWAYS validate input against `schema/scene_spec.schema.json` via `scripts/validate_spec.py` (or `render_samurai_cli.py --validate-only --spec <file>`) before rendering. Reject invalid specs with exact JSONPath errors — NEVER silently repair or guess missing fields.
3. **Strict Backend Type Enforcement**: Render using `meta.renderer` (`canvas2d` or `webgl`). If any layer uses a `type` not supported by the declared backend, reject immediately — NEVER silently fall back.
4. **Pure Determinism**: `window.renderFrame(t)` MUST remain stateless and deterministic (zero `Date.now()`, zero `THREE.Clock`, zero internal frame-rate-dependent integration).
5. **SwiftShader Parity Lock**: Parity and regression tests MUST run on `--gl-backend swiftshader` (D3D11/ANGLE GPU rasterization has minor driver-level subpixel variance).

---

## CLI Contract & Owned Pipeline Phases

- **Validation Gate (`--validate-only`)**:
  ```bash
  python scripts/validate_spec.py <scene_spec.json>
  python scripts/render_samurai_cli.py --spec <scene_spec.json> --validate-only
  ```
- **Phase 5 — Modular Build & Selective `--ranges` Render**:
  ```bash
  python scripts/render_samurai_cli.py --spec <scene_spec.json> --html <entry.html> --audio <audio.wav> --out <out.mp4> --fps 30 --duration <sec> --gl-backend d3d11 [--ranges a-b]
  ```
  - `--gl-backend`: `d3d11` (NVIDIA/hardware ANGLE) or `swiftshader` (CPU Vulkan). Locked explicitly and recorded in `frames_dir/render_meta.json`.
- **Phase 6 — Sound on Same Clock & Loudness Mastering**:
  - Synthesize deterministic SFX via `scripts/sfx_synth.py` aligned to `beats[].frame` and `beats[].sfx_id`.
  - Mux audio with transparent true-peak limiting (`-af "alimiter=limit=0.85:attack=5:release=50:level=false"`) targeting `-14 LUFS ±1` and true peak `<= -1.0 dBTP`.
- **Phase 7 — Automated Post-Render QA Gate**:
  ```bash
  python scripts/qa_video.py <out.mp4> --out <qa_dir> [--baseline-qa <prev_qa_report.json>]
  python scripts/audit_all_frames.py
  python scripts/audit_motion_ssim.py --ref-dir <ref> --sam-dir <sam> --out-dir <out>
  python scripts/strip_audit.py
  ```
  Produces `qa_report.json` (including `renderer_env`), `qa_report.md`, `hook_sheet.jpg`, and `phone_sheet.jpg`.

---

## Engine Assets & Contracts

- `schema/scene_spec.schema.json` — Scene specification contract (draft 2020-12).
- `schema/fix_card.schema.json` — Revision ticket contract (draft 2020-12).
- `engine/samurai-core.js` — Canvas2D primitives, `LAYER_REGISTRY_TYPES`, cut-clamped `4x/12x` shutter accumulator, optical finish, and `PBRCube3D`.
- `engine/three.min.js` — Vendored Three.js WebGL library.
- `scripts/validate_spec.py` & `scripts/test_schema_registry_sync.py` — Schema & registry parity validators.
- `scripts/render_samurai_cli.py`, `scripts/qa_video.py`, `scripts/strip_audit.py`, `scripts/audit_motion_ssim.py`, `scripts/audit_all_frames.py`, `scripts/sfx_synth.py`, `scripts/transcribe_beats.py`.
- **Optional Free SFX & Audio Sources** (complementing `scripts/sfx_synth.py`): `earshot` MCP (`Leonxlnx/earshot`, 922 procedural designs & 252 film SFX bank), `Bodila51/opus-sound-layer` (1,139 CC0 recordings), and `Openverse API` (`https://api.openverse.org/v1/audio/?q=...`, zero API key).

---

## Dead-Ends, Pitfalls & Verified Fixes

- `[Cross-Cut Shutter Color Bleed]` -> `12x @ 280°` samples backward into prior scene -> **Clamp `tk >= cutF / fps` using `sceneCuts`**.
- `[Missing ctx.restore() in Subframe]` -> Exponential camera drift -> **Wrap subframe calls in `offCtx.setTransform(1,0,0,1,0,0); offCtx.save(); ... offCtx.restore();`**.
- `[FFmpeg alimiter Auto-Normalizing Peak]` -> Default `level=true` pushes peak back to `0 dB` -> **Always pass `alimiter=limit=0.85:attack=5:release=50:level=false`**.
- `[Headless Chromium Defaulting to SwiftShader]` -> Default Windows headless ignores RTX GPU -> **Pass `--gl-backend d3d11` (`--use-gl=angle --use-angle=d3d11 --ignore-gpu-blocklist`)**.
- `[FFmpeg drawtext on Windows]` -> Fails without fontconfig -> **Draw QA sheet labels with Pillow in Python**.
---

## Vertical 9:16 & Delivery Pitfalls

- `engine/samurai-core.js` defaults to `W=1920, H=1080`. For `1080x1920` vertical output, build a standalone `index.html` exporting `window.renderFrame(t)` + `samuraiReady` at `1080x1920` and reuse the visual grammar (mask-up reveals, accent hairlines, grain, vignette) rather than the 16:9 compositor.
- Render via Playwright viewport `1080x1920`, `deviceScaleFactor=1`, parallel workers, JPEG q95, then `ffmpeg` H.264 CRF 21 + AAC `320 kb/s`.
- FFmpeg native AAC overshoots ~+3 dB true peak below `320 kb/s`; always encode `320 kb/s` and verify `ebur128 peak=true` (`-14 LUFS`, `TP <= -1`).
- `qa_video.py` freeze check (`192 px`, `MAD < 0.5`) flags static holds — keep low-frequency motion (120 BPM glow pulse + slow push-in) that survives x264 CRF 21, and use feathered radial ellipse gradients instead of hard rectangular light sweeps.

---

## Mandatory Self-Audit & Revise-Before-Delivery Gate

Before delivering any render:
1. Run `scripts/qa_video.py` and inspect generated micro-strips (`director_*.jpg` / `hook_sheet.jpg` / `phone_sheet.jpg`) via `read_file` to catch dead frames, clipping, or motion-blur bleed.
2. Verify final MP4 resolution, fps, codec, and `-14 LUFS` / `TP <= -1` via `ffprobe`; fix defects before presenting.
