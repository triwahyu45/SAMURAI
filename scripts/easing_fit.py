"""Pure measurement tool: extract pixel property series from video/frames and fit easing residuals.
No creative decisions or ease selection — outputs raw numbers and residuals only.
"""
import argparse
import json
import math
import subprocess
import tempfile
from pathlib import Path
import numpy as np
from PIL import Image


def _get_ffmpeg() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _cubic_bezier(x1: float, y1: float, x2: float, y2: float, u: float) -> float:
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    cx, bx = 3.0 * x1, 3.0 * (x2 - x1) - 3.0 * x1
    ax = 1.0 - cx - bx
    cy, by = 3.0 * y1, 3.0 * (y2 - y1) - 3.0 * y1
    ay = 1.0 - cy - by
    s = u
    for _ in range(6):
        x = ((ax * s + bx) * s + cx) * s - u
        if abs(x) < 1e-6:
            break
        dx = (3.0 * ax * s + 2.0 * bx) * s + cx
        if abs(dx) < 1e-6:
            break
        s -= x / dx
    lo, hi = 0.0, 1.0
    s = max(0.0, min(1.0, s))
    for _ in range(14):
        x = ((ax * s + bx) * s + cx) * s
        if abs(x - u) < 1e-6:
            break
        if u > x:
            lo = s
        else:
            hi = s
        s = 0.5 * (lo + hi)
    return ((ay * s + by) * s + cy) * s


def _analytic_spring(u: float, dur_sec: float, stiffness: float, damping: float, mass: float = 1.0) -> float:
    if u <= 0.0:
        return 0.0
    if u >= 1.0:
        return 1.0
    wn = math.sqrt(stiffness / mass)
    zeta = damping / (2.0 * math.sqrt(stiffness * mass))
    tau = u * max(1e-6, dur_sec)
    if zeta < 1.0 - 1e-6:
        wd = wn * math.sqrt(max(1.0 - zeta * zeta, 1e-9))
        return 1.0 - math.exp(-zeta * wn * tau) * (math.cos(wd * tau) + (zeta * wn / wd) * math.sin(wd * tau))
    if abs(zeta - 1.0) <= 1e-6:
        return 1.0 - math.exp(-wn * tau) * (1.0 + wn * tau)
    root = math.sqrt(zeta * zeta - 1.0)
    s1, s2 = wn * (-zeta + root), wn * (-zeta - root)
    return 1.0 - (s1 * math.exp(s2 * tau) - s2 * math.exp(s1 * tau)) / (s1 - s2)


def _eval_named(name: str, u: float) -> float:
    u = max(0.0, min(1.0, u))
    if name == "linear":
        return u
    if name == "ease-in":
        return u ** 3
    if name == "ease-out":
        return 1.0 - (1.0 - u) ** 3
    if name == "ease-in-out":
        return 4.0 * u * u * u if u < 0.5 else 1.0 - ((-2.0 * u + 2.0) ** 3) / 2.0
    if name == "expo-out":
        return 1.0 if u >= 1.0 else 1.0 - (2.0 ** (-10.0 * u))
    return u


def _metrics(pred: np.ndarray, target: np.ndarray) -> tuple[float, float]:
    res = np.abs(pred - target)
    return float(np.sqrt(np.mean(res ** 2))), float(np.max(res))


def fit_series(series: list[list[float]], fps: float = 30.0) -> dict:
    """Measure residuals for easing candidates on a [[t_ms, val], ...] series."""
    if len(series) < 2:
        raise ValueError("Need at least 2 samples in series")
    ts = np.array([p[0] for p in series], dtype=float)
    vs = np.array([p[1] for p in series], dtype=float)
    span = abs(vs[-1] - vs[0])
    eps = max(1e-6, span * 0.005)
    moving_frames = int(np.sum(np.abs(np.diff(vs)) > eps))
    low_confidence = moving_frames < 10
    time_uncertainty_ms = round(1000.0 / (2.0 * fps), 2)

    if span < 1e-9:
        return {
            "samples": len(series),
            "moving_frames": moving_frames,
            "low_confidence": True,
            "time_uncertainty_ms": time_uncertainty_ms,
            "series": series,
            "candidates": [],
        }

    t0, t1 = ts[0], ts[-1]
    dur_ms = max(1e-6, t1 - t0)
    dur_sec = dur_ms / 1000.0
    u = (ts - t0) / dur_ms
    y = (vs - vs[0]) / (vs[-1] - vs[0])

    candidates = []
    for name in ("linear", "ease-in", "ease-out", "ease-in-out", "expo-out"):
        pred = np.array([_eval_named(name, float(ui)) for ui in u])
        rmse, max_err = _metrics(pred, y)
        candidates.append({"name": name, "params": {}, "rmse": round(rmse, 6), "max_abs_residual": round(max_err, 6)})

    # Fit cubic-bezier via coarse grid + local coordinate refinement
    best_bez = (1e9, (0.25, 0.1, 0.25, 1.0))
    for x1 in (0.0, 0.16, 0.33, 0.5):
        for y1 in (0.0, 0.5, 1.0):
            for x2 in (0.2, 0.5, 0.8):
                for y2 in (0.5, 1.0, 1.2):
                    pred = np.array([_cubic_bezier(x1, y1, x2, y2, float(ui)) for ui in u])
                    rmse, _ = _metrics(pred, y)
                    if rmse < best_bez[0]:
                        best_bez = (rmse, (x1, y1, x2, y2))
    p = list(best_bez[1])
    for step in (0.1, 0.04, 0.015):
        improved = True
        while improved:
            improved = False
            for idx in range(4):
                for d in (-step, step):
                    cand = list(p)
                    lo, hi = (0.0, 1.0) if idx in (0, 2) else (-0.4, 1.6)
                    cand[idx] = max(lo, min(hi, cand[idx] + d))
                    pred = np.array([_cubic_bezier(cand[0], cand[1], cand[2], cand[3], float(ui)) for ui in u])
                    rmse, _ = _metrics(pred, y)
                    if rmse + 1e-7 < best_bez[0]:
                        best_bez = (rmse, tuple(cand))
                        p = cand
                        improved = True
    pred_bez = np.array([_cubic_bezier(*best_bez[1], float(ui)) for ui in u])
    rmse_b, max_b = _metrics(pred_bez, y)
    candidates.append({
        "name": "cubic-bezier",
        "params": {"p": [round(v, 4) for v in best_bez[1]]},
        "rmse": round(rmse_b, 6),
        "max_abs_residual": round(max_b, 6),
    })

    # Fit analytic spring (evaluated on normalized tau=u with effective stiffness/damping, and also physical dur_sec)
    best_spr = (1e9, (320.0, 18.0))
    for k in (120.0, 200.0, 260.0, 320.0, 450.0):
        for c in (10.0, 14.0, 18.0, 24.0, 32.0):
            pred = np.array([_analytic_spring(float(ui), 1.0, k, c) for ui in u])
            rmse, _ = _metrics(pred, y)
            if rmse < best_spr[0]:
                best_spr = (rmse, (k, c))
    sk, sc = best_spr[1]
    for dk, dc in ((40.0, 4.0), (15.0, 1.5), (5.0, 0.5)):
        improved = True
        while improved:
            improved = False
            for nk, nc in ((sk - dk, sc), (sk + dk, sc), (sk, sc - dc), (sk, sc + dc)):
                if nk < 20.0 or nc < 1.0:
                    continue
                pred = np.array([_analytic_spring(float(ui), 1.0, nk, nc) for ui in u])
                rmse, _ = _metrics(pred, y)
                if rmse + 1e-7 < best_spr[0]:
                    best_spr = (rmse, (nk, nc))
                    sk, sc = nk, nc
                    improved = True
    pred_spr = np.array([_analytic_spring(float(ui), 1.0, sk, sc) for ui in u])
    rmse_s, max_s = _metrics(pred_spr, y)
    candidates.append({
        "name": "spring",
        "params": {"stiffness": round(sk, 2), "damping": round(sc, 2), "mass": 1.0, "durSec_ref": 1.0, "observed_durSec": round(dur_sec, 4)},
        "rmse": round(rmse_s, 6),
        "max_abs_residual": round(max_s, 6),
    })

    candidates.sort(key=lambda c: c["rmse"])
    return {
        "samples": len(series),
        "moving_frames": moving_frames,
        "low_confidence": low_confidence,
        "time_uncertainty_ms": time_uncertainty_ms,
        "series": series,
        "candidates": candidates,
    }


def extract_series_from_frames(frame_paths: list[Path], roi: tuple[int, int, int, int] | None, prop: str, luma_thresh: float, fps: float) -> list[list[float]]:
    series = []
    for idx, p in enumerate(frame_paths):
        im = Image.open(p).convert("RGB")
        if roi is not None:
            x, y, w, h = roi
            im = im.crop((x, y, x + w, y + h))
        arr = np.asarray(im, dtype=np.float32)
        luma = 0.299 * arr[:, :, 0] + 0.587 * arr[:, :, 1] + 0.114 * arr[:, :, 2]
        ys, xs = np.where(luma > luma_thresh)
        if len(xs) == 0:
            val = 0.0
        else:
            bw = float(xs.max() - xs.min())
            bh = float(ys.max() - ys.min())
            cx = float(0.5 * (xs.min() + xs.max()))
            cy = float(0.5 * (ys.min() + ys.max()))
            if prop == "bbox_height":
                val = bh
            elif prop == "bbox_width":
                val = bw
            elif prop == "center_x":
                val = cx
            elif prop == "center_y":
                val = cy
            elif prop == "scale":
                val = math.hypot(bw, bh)
            else:
                raise ValueError(f"Unknown prop: {prop}")
        series.append([round((idx / fps) * 1000.0, 2), round(val, 4)])
    return series


def main():
    ap = argparse.ArgumentParser(description="Measure pixel series from video/frames and fit easing residuals.")
    ap.add_argument("--video", type=Path, help="Input .mp4 video")
    ap.add_argument("--frames-dir", type=Path, help="Directory of ordered PNG/JPG frames")
    ap.add_argument("--start-frame", type=int, default=0)
    ap.add_argument("--end-frame", type=int, default=60)
    ap.add_argument("--roi", type=str, default=None, help="Optional x,y,w,h crop")
    ap.add_argument("--prop", choices=["bbox_height", "bbox_width", "center_x", "center_y", "scale"], default="bbox_height")
    ap.add_argument("--luma-thresh", type=float, default=120.0)
    ap.add_argument("--fps", type=float, default=30.0)
    args = ap.parse_args()

    roi = tuple(int(v) for v in args.roi.split(",")) if args.roi else None
    if args.frames_dir:
        all_frames = sorted([p for p in args.frames_dir.iterdir() if p.suffix.lower() in (".png", ".jpg", ".jpeg")])
        chosen = all_frames[args.start_frame:args.end_frame + 1] if args.end_frame < len(all_frames) else all_frames
        series = extract_series_from_frames(chosen, roi, args.prop, args.luma_thresh, args.fps)
    elif args.video:
        with tempfile.TemporaryDirectory() as td:
            cmd = [
                _get_ffmpeg(), "-y", "-i", str(args.video),
                "-vf", f"select='between(n\\,{args.start_frame}\\,{args.end_frame})'",
                "-vsync", "0", str(Path(td) / "f%05d.png"),
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            chosen = sorted(Path(td).glob("f*.png"))
            series = extract_series_from_frames(chosen, roi, args.prop, args.luma_thresh, args.fps)
    else:
        raise SystemExit("Provide --video or --frames-dir")

    print(json.dumps(fit_series(series, fps=args.fps), indent=2))


if __name__ == "__main__":
    main()
