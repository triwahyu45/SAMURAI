"""
2,166-Frame Automated Audit: compares every frame 0..2165 in ref_frames_all/ vs frames_samurai/.
Checks background panel regime match + structural thumbnail MAE, flags contiguous mismatch intervals,
and generates side-by-side contact sheets:
  - comparison/audit_act1.jpg .. audit_act6.jpg
  - comparison/audit_mismatches.jpg (if any mismatches exist)
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

BASE = Path(r"d:\Data_Lokal\Kuliah\Tri Wahyu (22518241023)\Short\Samurai_Katana_Replication")
REF_DIR = BASE / "ref_frames_all"
SAM_DIR = BASE / "frames_samurai"
COMP_DIR = BASE / "comparison"
COMP_DIR.mkdir(exist_ok=True)
REPORT_JSON = BASE / "audit_report.json"

TOTAL_FRAMES = 2166
FPS = 30.0


def classify_corner_rgb(r: float, g: float, b: float) -> str:
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


def regime_compatible(ref_reg: str, sam_reg: str) -> bool:
    if ref_reg == sam_reg:
        return True
    # Warm off-white & light grey are the same light-panel family in Katana vignettes
    if {ref_reg, sam_reg} <= {"OFF_WHITE", "LIGHT_GREY"}:
        return True
    return False


def get_corner_regime_and_arr(path: Path):
    img = Image.open(path).convert("RGB").resize((160, 90), Image.Resampling.BILINEAR)
    arr = np.asarray(img, dtype=np.float32)
    border = np.concatenate([
        arr[:4, :, :].reshape(-1, 3),
        arr[-4:, :, :].reshape(-1, 3),
        arr[:, :6, :].reshape(-1, 3),
        arr[:, -6:, :].reshape(-1, 3),
    ], axis=0)
    med = np.median(border, axis=0)
    return classify_corner_rgb(float(med[0]), float(med[1]), float(med[2])), arr


def build_pair_sheet(frame_indices: list[int], out_path: Path, title: str):
    if not frame_indices:
        return
    cols = 4  # each cell is [REF|SAM] side-by-side (320+320 = 640 x 180)
    rows = (len(frame_indices) + cols - 1) // cols
    cw, ch = 640, 200
    sheet = Image.new("RGB", (cols * cw, rows * ch), (12, 12, 12))
    draw = ImageDraw.Draw(sheet)

    for idx, f in enumerate(frame_indices):
        r_img = Image.open(REF_DIR / f"frame_{f:05d}.jpg").resize((320, 180), Image.Resampling.BILINEAR)
        s_img = Image.open(SAM_DIR / f"frame_{f:05d}.jpg").resize((320, 180), Image.Resampling.BILINEAR)
        c = idx % cols
        r = idx // cols
        x, y = c * cw, r * ch
        sheet.paste(r_img, (x, y + 20))
        sheet.paste(s_img, (x + 320, y + 20))
        draw.rectangle([x, y, x + cw, y + 20], fill=(25, 25, 30))
        draw.line([x + 320, y, x + 320, y + ch], fill=(255, 255, 255), width=2)
        draw.text((x + 6, y + 4), f"REF f={f} ({f/FPS:.2f}s)", fill=(255, 210, 100))
        draw.text((x + 326, y + 4), f"SAM f={f}", fill=(120, 255, 180))

    sheet.save(out_path, quality=88)
    print(f"Saved audit sheet: {out_path} ({len(frame_indices)} pairs)")


def main():
    non_trans_total = 0
    non_trans_match = 0
    mismatches = []
    mae_list = []

    for f in range(TOTAL_FRAMES):
        ref_p = REF_DIR / f"frame_{f:05d}.jpg"
        sam_p = SAM_DIR / f"frame_{f:05d}.jpg"
        if not sam_p.exists():
            mismatches.append({"f": f, "reason": "missing_sam_frame"})
            continue

        ref_reg, ref_arr = get_corner_regime_and_arr(ref_p)
        sam_reg, sam_arr = get_corner_regime_and_arr(sam_p)
        mae = float(np.abs(ref_arr - sam_arr).mean())
        mae_list.append(mae)

        if ref_reg != "TRANSITION":
            non_trans_total += 1
            if regime_compatible(ref_reg, sam_reg):
                non_trans_match += 1
            else:
                mismatches.append({
                    "f": f,
                    "t": round(f / FPS, 2),
                    "ref_reg": ref_reg,
                    "sam_reg": sam_reg,
                    "mae": round(mae, 1),
                })

    # Group contiguous mismatch intervals
    intervals = []
    for m in mismatches:
        if not intervals or m["f"] > intervals[-1]["f_end"] + 1:
            intervals.append({
                "f_start": m["f"],
                "f_end": m["f"],
                "ref_reg": m.get("ref_reg", "?"),
                "sam_reg": m.get("sam_reg", "?"),
            })
        else:
            intervals[-1]["f_end"] = m["f"]

    acc = (non_trans_match / max(non_trans_total, 1)) * 100.0
    mean_mae = float(np.mean(mae_list)) if mae_list else 999.0

    report = {
        "total_frames": TOTAL_FRAMES,
        "non_transition_frames": non_trans_total,
        "panel_match_count": non_trans_match,
        "panel_accuracy_pct": round(acc, 2),
        "mean_mae": round(mean_mae, 2),
        "mismatch_frame_count": len(mismatches),
        "mismatch_intervals": intervals,
    }
    REPORT_JSON.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"PANEL ACCURACY: {acc:.2f}% ({non_trans_match}/{non_trans_total}) | Mean MAE: {mean_mae:.2f} | Mismatch intervals: {len(intervals)}")
    for iv in intervals:
        print(f"  Mismatch f={iv['f_start']}..{iv['f_end']} ({iv['f_end']-iv['f_start']+1}f): REF={iv['ref_reg']} vs SAM={iv['sam_reg']}")

    # Build 6 act audit sheets (sampling every 15th frame = 24 pairs per 12s act)
    for act_idx in range(6):
        f0 = act_idx * 360
        f1 = min((act_idx + 1) * 360, TOTAL_FRAMES)
        sample_frames = list(range(f0, f1, 15))
        build_pair_sheet(sample_frames, COMP_DIR / f"audit_act{act_idx+1}.jpg", f"Act {act_idx+1}")

    # Build mismatch sheet (up to 24 representative mismatch frames)
    if intervals:
        rep_frames = [iv["f_start"] for iv in intervals[:24]]
        build_pair_sheet(rep_frames, COMP_DIR / "audit_mismatches.jpg", "Mismatches")


if __name__ == "__main__":
    main()
