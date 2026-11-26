"""
Procedural Katana SFX Synthesizer (NumPy + SciPy).
Generates warm sub-bass drops, katana whooshes, mechanical clicks, and soft risers (no harsh snares).
"""
import argparse
import json
from pathlib import Path
import numpy as np
from scipy.io import wavfile
from scipy.signal import butter, lfilter

SR = 44100


def lowpass(sig, cutoff, order=3):
    b, a = butter(order, cutoff / (0.5 * SR), btype="low")
    return lfilter(b, a, sig)


def bandpass(sig, low, high, order=2):
    b, a = butter(order, [low / (0.5 * SR), high / (0.5 * SR)], btype="band")
    return lfilter(b, a, sig)


def gen_sub_drop(dur=0.45, f0=110.0, f1=38.0):
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    freq = f0 * (f1 / f0) ** (t / dur)
    phase = 2 * np.pi * np.cumsum(freq) / SR
    env = np.exp(-t * 7.0) * np.minimum(1.0, t / 0.008)
    return 0.75 * np.sin(phase) * env


def gen_whoosh(dur=0.28):
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    noise = np.random.default_rng(42).normal(0, 1, n)
    sig = bandpass(noise, 220, 1800)
    env = np.sin(np.pi * (t / dur)) ** 2
    return 0.45 * sig * env


def gen_click(dur=0.035):
    t = np.linspace(0, dur, int(SR * dur), endpoint=False)
    tone = np.sin(2 * np.pi * 1450 * t) + 0.5 * np.sin(2 * np.pi * 2900 * t)
    env = np.exp(-t * 140)
    return 0.35 * tone * env


def gen_riser(dur=0.9):
    n = int(SR * dur)
    t = np.linspace(0, dur, n, endpoint=False)
    noise = np.random.default_rng(7).normal(0, 1, n)
    sig = lowpass(noise, 900)
    env = (t / dur) ** 2.2
    return 0.35 * sig * env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cues", required=True, help="JSON list of {t, type: sub|whoosh|click|riser}")
    ap.add_argument("--duration", type=float, required=True)
    ap.add_argument("--out", default="samurai_sfx.wav")
    args = ap.parse_args()

    cues = json.loads(Path(args.cues).read_text(encoding="utf-8"))
    buf = np.zeros(int(SR * args.duration), dtype=np.float32)

    gens = {"sub": gen_sub_drop, "whoosh": gen_whoosh, "click": gen_click, "riser": gen_riser}
    for c in cues:
        fn = gens.get(c.get("type", "sub"))
        if not fn:
            continue
        clip = fn()
        idx = int(float(c["t"]) * SR)
        end = min(len(buf), idx + len(clip))
        if idx >= 0 and end > idx:
            buf[idx:end] += clip[: end - idx] * float(c.get("gain", 1.0))

    peak = np.max(np.abs(buf)) or 1.0
    if peak > 0.95:
        buf = buf * (0.95 / peak)
    wavfile.write(args.out, SR, (buf * 32767).astype(np.int16))
    print(f"Synthesized {len(cues)} SFX cues -> {args.out}")


if __name__ == "__main__":
    main()
