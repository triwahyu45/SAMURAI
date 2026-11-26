"""Verify render_samurai_cli.py determinism across two separate CLI runs on SwiftShader."""
import subprocess
import sys
from pathlib import Path
from PIL import Image
import numpy as np

CLI = Path(r"C:\Users\hando\.gemini\config\skills\samurai-engine\scripts\render_samurai_cli.py")
HTML = Path(r"d:\Data_Lokal\Kuliah\Tri Wahyu (22518241023)\Short\Samurai_Katana_Replication\index_samurai.html")
SCRATCH = Path(r"C:\Users\hando\.gemini\antigravity\brain\280d9d0c-a2c1-4024-aeeb-2119d053de74\scratch\cli_det_test")


def run_test():
    d1, d2 = SCRATCH / "run1", SCRATCH / "run2"
    o1, o2 = SCRATCH / "out1.mp4", SCRATCH / "out2.mp4"
    for d in (d1, d2):
        d.mkdir(parents=True, exist_ok=True)
    frames = [43, 956, 1608]
    ranges = ",".join(str(f) for f in frames)
    for d, o in ((d1, o1), (d2, o2)):
        cmd = [
            sys.executable, str(CLI),
            "--html", str(HTML),
            "--duration", "55",
            "--fps", "30",
            "--workers", "1",
            "--gl-backend", "swiftshader",
            "--ranges", ranges,
            "--frames-only",
            "--frames-dir", str(d),
            "--out", str(o),
        ]
        subprocess.run(cmd, check=True, capture_output=True, text=True)

    for f in frames:
        p1, p2 = d1 / f"frame_{f:05d}.jpg", d2 / f"frame_{f:05d}.jpg"
        b1, b2 = p1.read_bytes(), p2.read_bytes()
        assert b1 == b2, f"Byte mismatch on frame {f}"
        a1 = np.asarray(Image.open(p1).convert("RGB"), dtype=np.int16)
        a2 = np.asarray(Image.open(p2).convert("RGB"), dtype=np.int16)
        assert int(np.abs(a1 - a2).max()) == 0
    print(f"PASS test_cli_determinism: frames={frames}, bytes_identical=True, max_abs_diff=0")


if __name__ == "__main__":
    run_test()
