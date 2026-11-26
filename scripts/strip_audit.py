"""
Samurai Engine Micro-Strip QA Auditor.
Builds high-resolution 2-to-4-frame-interval visual contact sheets for every critical
animation beat so the agent MUST visually inspect per-frame motion before finishing.
"""
import argparse
from pathlib import Path
from PIL import Image, ImageDraw


def build_strip(ref_dir: Path, sam_dir: Path, frames: list[int], out_path: Path, cols=4, tw=440, th=248):
    rows = (len(frames) + cols - 1) // cols
    cw, ch = tw * 2, th + 22
    sheet = Image.new("RGB", (cols * cw, rows * ch), (12, 12, 14))
    draw = ImageDraw.Draw(sheet)
    for idx, f in enumerate(frames):
        r_path = ref_dir / f"frame_{f:05d}.jpg"
        s_path = sam_dir / f"frame_{f:05d}.jpg"
        if not s_path.exists():
            continue
        c, r = idx % cols, idx // cols
        x, y = c * cw, r * ch
        if r_path.exists():
            sheet.paste(Image.open(r_path).resize((tw, th), Image.Resampling.LANCZOS), (x, y + 22))
        sheet.paste(Image.open(s_path).resize((tw, th), Image.Resampling.LANCZOS), (x + tw, y + 22))
        draw.rectangle([x, y, x + cw, y + 22], fill=(22, 22, 26))
        draw.line([x + tw, y, x + tw, y + ch], fill=(255, 255, 255), width=2)
        draw.text((x + 8, y + 4), f"REF f={f}", fill=(255, 220, 100))
        draw.text((x + tw + 8, y + 4), f"SAM v6 f={f}", fill=(120, 255, 180))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path, quality=90)
    print(f"Saved {out_path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref-dir", required=True)
    ap.add_argument("--sam-dir", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    ref_dir, sam_dir, out_dir = Path(args.ref_dir), Path(args.sam_dir), Path(args.out_dir)
    strips = {
        "director_ae_split.jpg": list(range(278, 300, 2)),
        "director_mcp_led.jpg": list(range(438, 468, 4)),
        "director_filmstrip.jpg": list(range(694, 724, 4)),
        "director_fluid_cam.jpg": list(range(1018, 1040, 2)),
        "director_think.jpg": list(range(1428, 1456, 2)),
        "director_brand.jpg": [555, 575, 674, 1730, 2110, 2140],
    }
    for name, frames in strips.items():
        build_strip(ref_dir, sam_dir, frames, out_dir / name, cols=3 if len(frames) <= 6 else 4)


if __name__ == "__main__":
    main()
