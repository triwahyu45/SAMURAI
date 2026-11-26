"""
4-Metric Samurai Motion & Visual Auditor (OpenCV + scikit-image SSIM).
Measures:
  1. Panel Regime Sync (%)
  2. Active Motion Frame Ratio (MAD > 2.0) & MAD correlation vs reference
  3. Foreground Bounding-Box Coverage Match (%)
  4. Per-Act SSIM & MAE + generates audit_act1..6.jpg and showcase_v4_1..2.jpg
"""
import argparse
import json
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageDraw
from skimage.metrics import structural_similarity as ssim


def classify_corner(r, g, b):
    if r < 45 and g < 45 and b < 45:
        return "BLACK"
    if r > 140 and (r - g) > 75 and (r - b) > 75:
        return "RED"
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    if lum >= 225 and max(abs(r - g), abs(g - b), abs(r - b)) < 25:
        return "OFF_WHITE"
    if lum >= 165 and max(abs(r - g), abs(g - b), abs(r - b)) < 25:
        return "LIGHT_GREY"
    return "TRANSITION"


def compatible(a, b):
    return a == b or ({a, b} <= {"OFF_WHITE", "LIGHT_GREY"})


def fg_bbox_area_ratio(arr_bgr):
    h, w = arr_bgr.shape[:2]
    border = np.concatenate([arr_bgr[:4].reshape(-1, 3), arr_bgr[-4:].reshape(-1, 3)], axis=0)
    bg_med = np.median(border, axis=0)
    diff = np.abs(arr_bgr.astype(np.float32) - bg_med).max(axis=2)
    mask = (diff > 35).astype(np.uint8)
    ys, xs = np.where(mask > 0)
    if len(xs) < 10:
        return 0.0
    return float((xs.max() - xs.min() + 1) * (ys.max() - ys.min() + 1)) / float(w * h)


def build_pair_sheet(ref_dir: Path, sam_dir: Path, indices: list[int], out_path: Path, cols=4, tw=320, th=180):
    if not indices:
        return
    rows = (len(indices) + cols - 1) // cols
    cw, ch = tw * 2, th + 22
    sheet = Image.new("RGB", (cols * cw, rows * ch), (12, 12, 12))
    draw = ImageDraw.Draw(sheet)
    for idx, f in enumerate(indices):
        r_img = Image.open(ref_dir / f"frame_{f:05d}.jpg").resize((tw, th), Image.Resampling.LANCZOS)
        s_img = Image.open(sam_dir / f"frame_{f:05d}.jpg").resize((tw, th), Image.Resampling.LANCZOS)
        c, r = idx % cols, idx // cols
        x, y = c * cw, r * ch
        sheet.paste(r_img, (x, y + 22))
        sheet.paste(s_img, (x + tw, y + 22))
        draw.rectangle([x, y, x + cw, y + 22], fill=(24, 24, 28))
        draw.line([x + tw, y, x + tw, y + ch], fill=(255, 255, 255), width=2)
        draw.text((x + 6, y + 4), f"REF f={f} ({f/30:.2f}s)", fill=(255, 220, 100))
        draw.text((x + tw + 6, y + 4), f"SAM v4 f={f}", fill=(120, 255, 180))
    sheet.save(out_path, quality=90)
    print(f"Saved {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-dir", required=True)
    ap.add_argument("--sam-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--total", type=int, default=2166)
    args = ap.parse_args()

    ref_dir, sam_dir, out_dir = Path(args.ref_dir), Path(args.sam_dir), Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    non_trans, panel_ok = 0, 0
    ref_mads, sam_mads, maes, ssims, bbox_ratios = [], [], [], [], []
    prev_r, prev_s = None, None
    act_ssims = [[] for _ in range(6)]
    mismatches = []

    for f in range(args.total):
        r_bgr = cv2.resize(cv2.imread(str(ref_dir / f"frame_{f:05d}.jpg")), (160, 90))
        s_bgr = cv2.resize(cv2.imread(str(sam_dir / f"frame_{f:05d}.jpg")), (160, 90))

        # Corner regime
        r_rgb = cv2.cvtColor(r_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
        s_rgb = cv2.cvtColor(s_bgr, cv2.COLOR_BGR2RGB).astype(np.float32)
        rb = np.median(np.concatenate([r_rgb[:4].reshape(-1,3), r_rgb[-4:].reshape(-1,3), r_rgb[:,:6].reshape(-1,3), r_rgb[:,-6:].reshape(-1,3)]), axis=0)
        sb = np.median(np.concatenate([s_rgb[:4].reshape(-1,3), s_rgb[-4:].reshape(-1,3), s_rgb[:,:6].reshape(-1,3), s_rgb[:,-6:].reshape(-1,3)]), axis=0)
        rr, sr = classify_corner(*rb), classify_corner(*sb)
        if rr != "TRANSITION":
            non_trans += 1
            if compatible(rr, sr):
                panel_ok += 1
            else:
                mismatches.append((f, rr, sr))

        mae = float(np.abs(r_rgb - s_rgb).mean())
        maes.append(mae)

        if prev_r is not None:
            ref_mads.append(float(np.abs(r_rgb - prev_r).mean()))
            sam_mads.append(float(np.abs(s_rgb - prev_s).mean()))
        prev_r, prev_s = r_rgb, s_rgb

        if f % 4 == 0:
            r_g = cv2.cvtColor(r_bgr, cv2.COLOR_BGR2GRAY)
            s_g = cv2.cvtColor(s_bgr, cv2.COLOR_BGR2GRAY)
            sc = float(ssim(r_g, s_g))
            ssims.append(sc)
            act_ssims[min(5, f // 360)].append(sc)
            ra, sa = fg_bbox_area_ratio(r_bgr), fg_bbox_area_ratio(s_bgr)
            if ra > 0.05:
                bbox_ratios.append(min(sa, ra) / max(sa, ra, 1e-5))

    ref_act = sum(1 for m in ref_mads if m > 2.0) / max(len(ref_mads), 1) * 100
    sam_act = sum(1 for m in sam_mads if m > 2.0) / max(len(sam_mads), 1) * 100
    mad_corr = float(np.corrcoef(ref_mads, sam_mads)[0, 1]) if len(ref_mads) > 2 else 0.0
    panel_pct = panel_ok / max(non_trans, 1) * 100
    mean_mae = float(np.mean(maes))
    mean_ssim = float(np.mean(ssims))
    bbox_match = float(np.mean(bbox_ratios) * 100) if bbox_ratios else 0.0

    report = {
        "panel_accuracy_pct": round(panel_pct, 2),
        "ref_active_motion_pct": round(ref_act, 1),
        "sam_active_motion_pct": round(sam_act, 1),
        "motion_curve_corr": round(mad_corr, 3),
        "bbox_scale_match_pct": round(bbox_match, 1),
        "mean_mae": round(mean_mae, 2),
        "mean_ssim": round(mean_ssim, 4),
        "per_act_ssim": [round(float(np.mean(a)), 4) if a else 0.0 for a in act_ssims],
        "mismatch_count": len(mismatches),
        "mismatches_sample": mismatches[:20],
    }
    (out_dir.parent / "audit_v4_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    for act in range(6):
        f0, f1 = act * 360, min((act + 1) * 360, args.total)
        build_pair_sheet(ref_dir, sam_dir, list(range(f0, f1, 15)), out_dir / f"audit_act{act+1}.jpg")

    shots = [74, 242, 282, 456, 478, 575, 674, 885, 980, 992, 1010, 1052, 1132, 1142, 1360, 1395, 1408, 1522, 1675, 2042]
    build_pair_sheet(ref_dir, sam_dir, shots[:10], out_dir / "showcase_v4_1.jpg", cols=2, tw=480, th=270)
    build_pair_sheet(ref_dir, sam_dir, shots[10:], out_dir / "showcase_v4_2.jpg", cols=2, tw=480, th=270)


if __name__ == "__main__":
    main()
