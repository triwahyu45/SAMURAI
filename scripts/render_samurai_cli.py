"""
Samurai Reusable Parallel Playwright Renderer (--fps 30|60, --ranges hot-reload, WebGL SwiftShader).
"""
import argparse
import asyncio
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path
from playwright.async_api import async_playwright

VALIDATOR_PATH = Path(__file__).resolve().parent / "validate_spec.py"
RUNNER_HTML_MAP = {
    "canvas2d": Path(__file__).resolve().parent.parent / "engine" / "runner_canvas2d.html",
}

GL_BACKEND_ARGS = {
    "d3d11": ["--enable-webgl", "--use-gl=angle", "--use-angle=d3d11", "--ignore-gpu-blocklist"],
    "swiftshader": ["--enable-webgl", "--use-gl=angle", "--use-angle=swiftshader"],
}


def parse_ranges(ranges_str: str | None, total_frames: int) -> list[int]:
    if not ranges_str:
        return list(range(total_frames))
    frames = set()
    for part in ranges_str.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            s, e = part.split("-", 1)
            frames.update(range(max(0, int(s)), min(total_frames - 1, int(e)) + 1))
        else:
            idx = int(part)
            if 0 <= idx < total_frames:
                frames.add(idx)
    return sorted(frames)


async def launch_browser(p, gl_backend: str = "d3d11"):
    args = [
        "--allow-file-access-from-files",
        "--disable-background-timer-throttling",
        "--disable-renderer-backgrounding",
        "--disable-dev-shm-usage",
        *GL_BACKEND_ARGS[gl_backend],
    ]
    try:
        return await p.chromium.launch(headless=True, args=args)
    except Exception:
        return await p.chromium.launch(channel="msedge", headless=True, args=args)


async def probe_renderer_env(html_uri: str | None, gl_backend: str) -> dict:
    async with async_playwright() as p:
        browser = await launch_browser(p, gl_backend)
        chromium_ver = browser.version
        page = await browser.new_page()
        gl_info = await page.evaluate("""() => {
            const c = document.createElement('canvas');
            const gl = c.getContext('webgl2') || c.getContext('webgl');
            if (!gl) return { gl_renderer: 'none', gl_vendor: 'none' };
            const dbg = gl.getExtension('WEBGL_debug_renderer_info');
            return {
                gl_renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
                gl_vendor: dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
            };
        }""")
        await browser.close()
    return {"gl_backend": gl_backend, "chromium_version": chromium_ver, **gl_info}


async def render_worker(worker_id: int, html_uri: str, frames_dir: Path, fps: int, indices: list[int], gl_backend: str, spec_data: dict | None = None):
    if not indices:
        return
    async with async_playwright() as p:
        browser = await launch_browser(p, gl_backend)
        page = await browser.new_page(viewport={"width": 1920, "height": 1080})
        await page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(("file://", "data:", "blob:")) else route.abort())
        await page.goto(html_uri, wait_until="load")
        if spec_data is not None:
            await page.evaluate("(s) => window.loadSamuraiSpec(s)", spec_data)
        await page.wait_for_function("window.samuraiReady === true", timeout=20000)
        await page.evaluate("() => document.fonts.ready")

        for count, f_idx in enumerate(indices):
            t = f_idx / fps
            await page.evaluate("() => document.fonts.ready")
            await page.evaluate(f"window.renderFrame({t:.8f})")
            await page.screenshot(path=str(frames_dir / f"frame_{f_idx:05d}.jpg"), type="jpeg", quality=95)
            if count % 120 == 0:
                print(f"[Worker {worker_id}] {count}/{len(indices)} (f={f_idx}, t={t:.2f}s)")
        await browser.close()


def mux(frames_dir: Path, out_mp4: Path, fps: int, audio: Path | None, ref_mp4: Path | None, split_mp4: Path | None):
    cmd = ["ffmpeg", "-y", "-framerate", str(fps), "-start_number", "0", "-i", str(frames_dir / "frame_%05d.jpg")]
    if audio and audio.exists():
        cmd += ["-i", str(audio), "-af", "alimiter=limit=0.85:attack=5:release=50:level=false", "-c:a", "aac", "-b:a", "320k", "-shortest"]
    cmd += ["-c:v", "libx264", "-preset", "faster", "-crf", "18", "-pix_fmt", "yuv420p", str(out_mp4)]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)

    if ref_mp4 and ref_mp4.exists() and split_mp4:
        cmd_s = [
            "ffmpeg", "-y", "-i", str(ref_mp4), "-i", str(out_mp4),
            "-filter_complex", "[0:v]scale=960:540[v0];[1:v]scale=960:540[v1];[v0][v1]hstack[outv]",
            "-map", "[outv]", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "copy", "-shortest",
            str(split_mp4),
        ]
        subprocess.run(cmd_s, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default=None, help="Path to scene_spec.json to validate")
    ap.add_argument("--validate-only", action="store_true", help="Validate spec and exit without rendering")
    ap.add_argument("--html", required=False)
    ap.add_argument("--frames-dir", default="frames_samurai")
    ap.add_argument("--out", default="Samurai_Output.mp4")
    ap.add_argument("--audio", default=None)
    ap.add_argument("--ref", default=None)
    ap.add_argument("--split-out", default=None)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--duration", type=float, default=None)
    ap.add_argument("--workers", type=int, default=None, help="Worker count (default: 4 for d3d11, min(6, cpu_count) for swiftshader)")
    ap.add_argument("--ranges", default=None)
    ap.add_argument("--runner", choices=["legacy", "spec"], default="legacy", help="Runner mode: legacy (--html) or spec (--spec)")
    ap.add_argument("--frames-only", action="store_true", help="Skip ffmpeg mp4 muxing")
    ap.add_argument("--gl-backend", choices=["d3d11", "swiftshader"], default="d3d11", help="Lock Chromium WebGL backend")
    args = ap.parse_args()
    if args.workers is None:
        args.workers = 4 if args.gl_backend == "d3d11" else min(6, os.cpu_count() or 4)

    spec_data = None
    if args.spec:
        res = subprocess.run([sys.executable, str(VALIDATOR_PATH), args.spec])
        if res.returncode != 0:
            sys.exit(res.returncode)
        spec_data = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    elif args.validate_only or args.runner == "spec":
        print("FAIL: --validate-only and --runner spec require --spec <scene_spec.json>")
        sys.exit(1)

    if args.validate_only:
        return

    if args.runner == "spec":
        renderer = spec_data["meta"]["renderer"]
        if renderer not in RUNNER_HTML_MAP:
            print(f"FAIL: --runner spec does not support renderer '{renderer}' yet")
            sys.exit(1)
        html_path = RUNNER_HTML_MAP[renderer]
        duration_sec = spec_data["meta"]["duration_frames"] / spec_data["meta"]["fps"]
        fps = int(spec_data["meta"]["fps"])
    else:
        if not args.html or args.duration is None:
            ap.error("--html and --duration are required in legacy runner mode")
        html_path = Path(args.html)
        duration_sec = args.duration
        fps = args.fps

    frames_dir = Path(args.frames_dir)
    frames_dir.mkdir(parents=True, exist_ok=True)
    render_meta = await probe_renderer_env(html_path.resolve().as_uri(), args.gl_backend)
    (frames_dir / "render_meta.json").write_text(json.dumps(render_meta, indent=2), encoding="utf-8")

    total = int(round(duration_sec * fps))
    targets = parse_ranges(args.ranges, total)

    t0 = time.time()
    buckets = [targets[i::args.workers] for i in range(args.workers)]
    await asyncio.gather(*(render_worker(w, html_path.resolve().as_uri(), frames_dir, fps, b, args.gl_backend, spec_data if args.runner == "spec" else None) for w, b in enumerate(buckets)))
    print(f"Rendered {len(targets)} frames in {time.time() - t0:.1f}s ({render_meta['gl_backend']} | {render_meta['gl_renderer']})")

    if not args.frames_only:
        mux(
            frames_dir,
            Path(args.out),
            fps,
            Path(args.audio) if args.audio else None,
            Path(args.ref) if args.ref else None,
            Path(args.split_out) if args.split_out else None,
        )
        print(f"Exported: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
