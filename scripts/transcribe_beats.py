"""Extract word-level timestamps from audio/video via faster-whisper."""
import argparse
import json
from pathlib import Path
from faster_whisper import WhisperModel


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Audio or video file path")
    ap.add_argument("--out", default="timeline_words.json", help="Output JSON path")
    ap.add_argument("--model", default="base", help="Whisper model size")
    args = ap.parse_args()

    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(args.input, word_timestamps=True)

    out_segs = []
    for seg in segments:
        out_segs.append({
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
            "words": [
                {
                    "word": w.word.strip(),
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                    "prob": round(w.probability, 3),
                }
                for w in (seg.words or [])
            ],
        })

    Path(args.out).write_text(
        json.dumps({"language": info.language, "duration": info.duration, "segments": out_segs}, indent=2),
        encoding="utf-8",
    )
    print(f"Saved {len(out_segs)} segments to {args.out}")


if __name__ == "__main__":
    main()
