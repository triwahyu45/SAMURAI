#!/usr/bin/env python3
"""
Samurai Engine Post-Render Video QA Auditor.
Measures what you cannot watch or hear:
  - Stream metadata (resolution, FPS, VFR check, duration, audio presence)
  - Frame 0 check, single-frame flashes, micro-pops, detected cuts, frozen stretches, flat frames
  - EBU R128 integrated loudness (LUFS) & true peak (dBFS)
  - Generates hook_sheet.jpg (0-3s every 0.5s @ 360px) and phone_sheet.jpg (sampled @ 360px)

Usage:
  python qa_video.py video.mp4 --out qa_dir [--freeze 1.0] [--freeze-eps 0.5]
"""
import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ANALYSIS_W = 192


def run_cmd(cmd) -> tuple[int, str, str]:
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return r.returncode, r.stdout.decode(errors="replace"), r.stderr.decode(errors="replace")


def parse_rate(s: str) -> float:
    if "/" in str(s):
        num, den = (int(x) for x in str(s).split("/"))
        return num / den if num and den else 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def probe_video(path: Path) -> dict:
    rc, out, err = run_cmd([
        "ffprobe", "-v", "error", "-show_entries",
        "stream=codec_type,width,height,r_frame_rate,avg_frame_rate:format=duration",
        "-of", "json", str(path),
    ])
    if rc != 0:
        raise RuntimeError(f"ffprobe failed: {err}")
    data = json.loads(out)
    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if v is None:
        raise RuntimeError("No video stream found")
    nom, avg = parse_rate(v.get("r_frame_rate", "0/1")), parse_rate(v.get("avg_frame_rate", "0/1"))
    dur = float(data["format"]["duration"])
    vfr = bool(nom and avg) and abs(nom - avg) / nom > 0.01
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))
    return {
        "w": int(v["width"]),
        "h": int(v["height"]),
        "fps": round(nom or avg, 3),
        "avg_fps": round(avg, 3),
        "dur": round(dur, 3),
        "vfr": vfr,
        "audio": has_audio,
    }


def runs_true(mask):
    out, start = [], None
    for i, m in enumerate(mask):
        if m and start is None:
            start = i
        elif not m and start is not None:
            out.append((start, i))
            start = None
    if start is not None:
        out.append((start, len(mask)))
    return out


def analyze_frames(path: Path, info: dict, freeze_secs: float, freeze_eps: float) -> dict:
    aw = ANALYSIS_W
    ah = max(2, int(round(aw * info["h"] / info["w"] / 2)) * 2)
    fsize = aw * ah
    proc = subprocess.Popen(
        ["ffmpeg", "-v", "error", "-i", str(path), "-vf", f"scale={aw}:{ah}:flags=area,format=gray", "-f", "rawvideo", "-"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    means, stds, diffs, skips = [], [], [], []
    prev = prev2 = first = None
    assert proc.stdout is not None
    while True:
        buf = proc.stdout.read(fsize)
        if len(buf) < fsize:
            break
        f = np.frombuffer(buf, np.uint8).reshape(ah, aw).astype(np.int16)
        means.append(float(f.mean()))
        stds.append(float(f.std()))
        diffs.append(float(np.abs(f - prev).mean()) if prev is not None else 0.0)
        if prev2 is not None:
            skips.append(float(np.abs(f - prev2).mean()))
        if first is None:
            first = f
        prev2, prev = prev, f
    proc.wait()
    n = len(means)
    if n == 0:
        raise RuntimeError("No frames decoded")

    d = np.array(diffs)
    std = np.array(stds)
    skip = np.array(([math.nan] + skips + [math.nan])[:n]) if n >= 2 else np.array([math.nan] * n)
    fps = info["fps"]
    med = float(np.median(d[1:])) if n > 2 else 0.0

    t_flash = max(2.0, 4.0 * med)
    flashes = [
        i for i in range(1, n - 1)
        if d[i] > t_flash and d[i + 1] > t_flash and skip[i] < 0.35 * min(d[i], d[i + 1])
    ]
    flash_set = set(flashes) | {i + 1 for i in flashes}

    cuts = []
    for i in range(1, n):
        if i in flash_set:
            continue
        lo, hi = max(1, i - 15), min(n, i + 16)
        local = np.concatenate([d[lo:i], d[i + 1:hi]])
        lm = float(np.median(local)) if local.size else 0.0
        if d[i] > max(6.0, 3.5 * (lm + 0.5)):
            cuts.append(i)

    pops = [
        i for i in range(1, n - 1)
        if i not in flash_set and i not in cuts and d[i] > 2.0 and d[i] > 3.0 * max(d[i - 1], d[i + 1])
    ]

    still = d < freeze_eps
    still[0] = False
    frozen = [
        {"from_s": round((a - 1) / fps, 2), "to_s": round(b / fps, 2), "secs": round((b - a + 1) / fps, 2)}
        for a, b in runs_true(still) if (b - a + 1) / fps >= freeze_secs
    ]
    flat = [
        {"from_s": round(a / fps, 2), "to_s": round(b / fps, 2)}
        for a, b in runs_true(std < 6.0) if a > 0
    ]

    return {
        "frame_count": n,
        "frame0": {"mean": round(means[0], 1), "std": round(stds[0], 1)},
        "median_step_mad": round(med, 3),
        "flash_count": len(flashes),
        "flashes_s": [round(i / fps, 3) for i in flashes[:15]],
        "pop_count": len(pops),
        "pops_s": [round(i / fps, 3) for i in pops[:15]],
        "cut_count": len(cuts),
        "cuts_s": [round(i / fps, 2) for i in cuts[:25]],
        "frozen_stretches": frozen,
        "flat_stretches": flat,
    }


def analyze_audio(path: Path) -> dict:
    _, _, err = run_cmd([
        "ffmpeg", "-v", "info", "-i", str(path), "-af", "ebur128=peak=true", "-f", "null", "-"
    ])
    m_i = re.findall(r"I:\s*([-\d.]+)\s*LUFS", err)
    m_tp = re.findall(r"Peak:\s*([-\d.]+)\s*dBFS", err)
    lufs = float(m_i[-1]) if m_i else None
    peak = float(m_tp[-1]) if m_tp else None
    return {"integrated_lufs": lufs, "true_peak_dbfs": peak}


def build_time_sheet(video_path: Path, times: list[float], out_path: Path, tw: int = 360, cols: int = 4):
    if not times:
        return
    tmp_dir = out_path.parent / "_tmp_qa"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    imgs = []
    for idx, ts in enumerate(times):
        tile = tmp_dir / f"t_{idx:03d}.jpg"
        run_cmd([
            "ffmpeg", "-y", "-v", "error", "-ss", f"{ts:.3f}", "-i", str(video_path),
            "-frames:v", "1", "-vf", f"scale={tw}:-2", "-q:v", "3", str(tile),
        ])
        if tile.exists():
            imgs.append((ts, Image.open(tile).convert("RGB")))
    if not imgs:
        return
    th = imgs[0][1].height
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * tw, rows * (th + 20)), (14, 14, 16))
    draw = ImageDraw.Draw(sheet)
    for idx, (ts, im) in enumerate(imgs):
        c, r = idx % cols, idx // cols
        x, y = c * tw, r * (th + 20)
        sheet.paste(im, (x, y + 20))
        draw.rectangle([x, y, x + tw, y + 20], fill=(24, 24, 28))
        draw.text((x + 6, y + 4), f"t={ts:.2f}s", fill=(230, 230, 240))
        im.close()
    sheet.save(out_path, quality=88)
    for p in tmp_dir.glob("*"):
        p.unlink()
    tmp_dir.rmdir()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video", help="Path to MP4 video")
    ap.add_argument("--out", required=True, help="Output QA directory")
    ap.add_argument("--freeze", type=float, default=1.0, help="Frozen stretch threshold in seconds")
    ap.add_argument("--freeze-eps", type=float, default=0.5, help="MAD threshold below which a frame counts as still")
    ap.add_argument("--render-meta", default=None, help="Optional path to render_meta.json")
    ap.add_argument("--baseline-qa", default=None, help="Optional prior qa_report.json to check renderer parity")
    args = ap.parse_args()

    vpath = Path(args.video)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    meta_path = Path(args.render_meta) if args.render_meta else (vpath.parent / "frames_samurai" / "render_meta.json")
    renderer_env = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else None
    warnings = []
    if args.baseline_qa and Path(args.baseline_qa).exists() and renderer_env:
        base_env = json.loads(Path(args.baseline_qa).read_text(encoding="utf-8")).get("renderer_env")
        if base_env and (base_env.get("gl_backend") != renderer_env.get("gl_backend") or base_env.get("gl_renderer") != renderer_env.get("gl_renderer")):
            w = f"WARNING: renderer_env mismatch vs baseline ({renderer_env.get('gl_backend')} vs {base_env.get('gl_backend')}) — metrics/hashes are not comparable!"
            warnings.append(w)
            print(w)

    info = probe_video(vpath)
    pic = analyze_frames(vpath, info, args.freeze, args.freeze_eps)
    aud = analyze_audio(vpath) if info["audio"] else {"integrated_lufs": None, "true_peak_dbfs": None}

    hook_times = [round(t * 0.5, 2) for t in range(7) if t * 0.5 < info["dur"]]
    step = 1.0 if info["dur"] <= 30 else 2.0
    phone_times = [round(t, 2) for t in np.arange(0.0, info["dur"], step)]
    build_time_sheet(vpath, hook_times, out_dir / "hook_sheet.jpg", tw=360, cols=4)
    build_time_sheet(vpath, phone_times, out_dir / "phone_sheet.jpg", tw=360, cols=6)

    checks = {
        "has_audio": "PASS" if info["audio"] else "FAIL",
        "cfr_lock": "PASS" if not info["vfr"] else "WARN",
        "no_single_frame_flashes": "PASS" if pic["flash_count"] == 0 else f"WARN ({pic['flash_count']})",
        "no_long_freezes": "PASS" if len(pic["frozen_stretches"]) == 0 else f"WARN ({len(pic['frozen_stretches'])})",
        "loudness_ok": (
            "PASS"
            if aud["integrated_lufs"] is not None and -18.0 <= aud["integrated_lufs"] <= -10.0
            else f"WARN ({aud['integrated_lufs']} LUFS)"
        ),
    }
    report = {"video": str(vpath), "renderer_env": renderer_env, "warnings": warnings, "stream": info, "picture": pic, "audio": aud, "checks": checks}
    (out_dir / "qa_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    md = [
        f"# Samurai Engine QA Report — `{vpath.name}`",
        f"- **Stream**: `{info['w']}x{info['h']}` @ `{info['fps']} fps` (`{pic['frame_count']}` frames, `{info['dur']}s`), Audio: `{info['audio']}`",
        f"- **Motion**: median step MAD `{pic['median_step_mad']}`, flashes `{pic['flash_count']}`, pops `{pic['pop_count']}`, cuts `{pic['cut_count']}`, frozen `{len(pic['frozen_stretches'])}`",
        f"- **Audio**: `{aud['integrated_lufs']} LUFS`, true peak `{aud['true_peak_dbfs']} dBFS`",
        f"- **Sheets**: `hook_sheet.jpg`, `phone_sheet.jpg`",
    ]
    (out_dir / "qa_report.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
