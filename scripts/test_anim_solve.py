"""Unit tests for window.Samurai.Anim.solve and Anim.evalEase (all 5 curve types)."""
from pathlib import Path
from playwright.sync_api import sync_playwright

CORE_JS = Path(r"C:\Users\hando\.gemini\config\skills\samurai-engine\engine\samurai-core.js")


def rk4_spring(t_target: float, stiffness: float = 320.0, damping: float = 18.0, mass: float = 1.0, dt: float = 1e-4) -> float:
    """4th-order Runge-Kutta reference integrator for x'' = (k*(1-x) - c*x')/m with x(0)=0, x'(0)=0."""
    x, v = 0.0, 0.0
    steps = int(round(t_target / dt))
    h = t_target / max(1, steps) if steps > 0 else 0.0

    def acc(xx: float, vv: float) -> float:
        return (stiffness * (1.0 - xx) - damping * vv) / mass

    for _ in range(steps):
        k1x, k1v = v, acc(x, v)
        k2x, k2v = v + 0.5 * h * k1v, acc(x + 0.5 * h * k1x, v + 0.5 * h * k1v)
        k3x, k3v = v + 0.5 * h * k2v, acc(x + 0.5 * h * k2x, v + 0.5 * h * k2v)
        k4x, k4v = v + h * k3v, acc(x + h * k3x, v + h * k3v)
        x += (h / 6.0) * (k1x + 2 * k2x + 2 * k3x + k4x)
        v += (h / 6.0) * (k1v + 2 * k2v + 2 * k3v + k4v)
    return x


def run_tests():
    js_src = CORE_JS.read_text(encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<script>" + js_src + "</script>")

        # 1. All 5 types: endpoints, monotonicity / expected non-monotonic behavior
        data = page.evaluate("""() => {
            const { Anim } = window.Samurai;
            const specs = [
                { name: 'linear',       ease: 'linear',                                                expectMono: true },
                { name: 'cubic-bezier', ease: { type: 'cubic-bezier', p: [0.16, 1, 0.3, 1] },          expectMono: true },
                { name: 'spring',       ease: { type: 'spring', stiffness: 320, damping: 18 },         expectMono: false },
                { name: 'overshoot',    ease: { type: 'overshoot', s: 1.65 },                          expectMono: false },
                { name: 'anticipate',   ease: { type: 'anticipate', pull: -0.14 },                     expectMono: false },
            ];
            return specs.map(s => {
                const tr = [{ t: 0.2, v: 10, ease: s.ease }, { t: 1.2, v: 50 }];
                const samples = Array.from({ length: 101 }, (_, i) => Anim.solve(tr, 0.2 + i * 0.01));
                const norm = Array.from({ length: 101 }, (_, i) => Anim.evalEase(s.ease, i / 100, 1.0));
                return {
                    name: s.name,
                    expectMono: s.expectMono,
                    before: Anim.solve(tr, 0.0),
                    atStart: Anim.solve(tr, 0.2),
                    atEnd: Anim.solve(tr, 1.2),
                    after: Anim.solve(tr, 2.0),
                    minNorm: Math.min(...norm),
                    maxNorm: Math.max(...norm),
                    isMono: samples.every((v, i) => i === 0 || v >= samples[i - 1] - 1e-12),
                };
            });
        }""")

        print("=== Per-Type Anim.solve Verification Table (5/5) ===")
        for row in data:
            ep_ok = (row["before"] == 10 and row["atStart"] == 10 and row["atEnd"] == 50 and row["after"] == 50)
            if row["expectMono"]:
                shape_ok = row["isMono"]
                shape_note = f"monotonic={row['isMono']}"
            else:
                # Non-monotonic expected: spring/overshoot > 1.0, anticipate < 0.0
                shape_ok = (not row["isMono"]) and (row["maxNorm"] > 1.001 or row["minNorm"] < -0.05)
                shape_note = f"non-mono(min={row['minNorm']:.4f}, max={row['maxNorm']:.4f})"
            status = "PASS" if (ep_ok and shape_ok) else "FAIL"
            print(f"  {row['name']:13s} | t0={row['atStart']} tEnd={row['atEnd']} | {shape_note:36s} | {status}")
            assert ep_ok and shape_ok, f"Failed for {row}"

        # 2. Spring snap jump & velocity at u -> 1- (no settle threshold; hard snap at u >= 1)
        snap_info = page.evaluate("""() => {
            const { Anim } = window.Samurai;
            const eps = 1e-6;
            const out = [];
            for (const durSec of [1.0, 0.35]) {
                const e = { type: 'spring', stiffness: 320, damping: 18, mass: 1 };
                const v1 = Anim.evalEase(e, 1.0 - eps, durSec);
                const v2 = Anim.evalEase(e, 1.0 - 2 * eps, durSec);
                const vAt1 = Anim.evalEase(e, 1.0, durSec);
                out.push({
                    durSec,
                    valBeforeSnap: v1,
                    snapJump: Math.abs(vAt1 - v1),
                    velBeforeSnapPerSec: (v1 - v2) / (eps * durSec),
                });
            }
            return out;
        }""")
        print("=== Spring End-Snap Telemetry (Hard Snap at u>=1, No Settle Blend) ===")
        for s in snap_info:
            print(f"  durSec={s['durSec']:4.2f}s | val(1-1e-6)={s['valBeforeSnap']:.6f} | snapJump={s['snapJump']:.6e} | vel={s['velBeforeSnapPerSec']:.4f}/s")

        warn_test = page.evaluate("""() => {
            const { Anim } = window.Samurai;
            Anim.lastWarnings = [];
            const vOk = Anim.evalEase({ type: 'spring', stiffness: 320, damping: 18, mass: 1 }, 1.0, 1.0);
            const c1 = Anim.lastWarnings.length;
            const vWarn = Anim.evalEase({ type: 'spring', stiffness: 320, damping: 18, mass: 1 }, 1.0, 0.35);
            const c2 = Anim.lastWarnings.length;
            return { vOk, c1, vWarn, c2, msg: Anim.lastWarnings[0] || '', thresh: Anim.SPRING_SETTLE_WARN_THRESHOLD };
        }""")
        assert warn_test["vOk"] == 1 and warn_test["c1"] == 0, f"Unexpected warning at durSec=1.0: {warn_test}"
        assert warn_test["vWarn"] == 1 and warn_test["c2"] == 1, f"Missing warning at durSec=0.35: {warn_test}"
        print(f"=== Spring Residual Warning (threshold={warn_test['thresh']}) ===\n  {warn_test['msg']}")

        # 3. Analytic spring vs RK4 reference (dt=1e-4)
        spr_js = page.evaluate("""() => {
            const { Anim } = window.Samurai;
            const ts = [0.05, 0.1, 0.2, 0.35, 0.5, 0.75, 0.9];
            return ts.map(t => ({
                t,
                under: Anim.evalEase({ type: 'spring', stiffness: 320, damping: 18, mass: 1 }, t, 1.0),
                crit: Anim.evalEase({ type: 'spring', stiffness: 100, damping: 20, mass: 1 }, t, 1.0),
                over: Anim.evalEase({ type: 'spring', stiffness: 100, damping: 30, mass: 1 }, t, 1.0),
            }));
        }""")
        max_rk4_err = 0.0
        for row in spr_js:
            t = row["t"]
            max_rk4_err = max(
                max_rk4_err,
                abs(row["under"] - rk4_spring(t, 320.0, 18.0, 1.0, 1e-4)),
                abs(row["crit"] - rk4_spring(t, 100.0, 20.0, 1.0, 1e-4)),
                abs(row["over"] - rk4_spring(t, 100.0, 30.0, 1.0, 1e-4)),
            )
        assert max_rk4_err < 1e-5, f"Analytic spring vs RK4 error too high: {max_rk4_err}"

        # 4. Two-run determinism across fresh Chromium processes
        run1 = page.evaluate("""() => [0, 0.13, 0.47, 0.89, 1.0].map(t => window.Samurai.Anim.evalEase({ type: 'spring', stiffness: 260, damping: 18 }, t, 1.0))""")
        browser.close()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content("<script>" + js_src + "</script>")
        run2 = page.evaluate("""() => [0, 0.13, 0.47, 0.89, 1.0].map(t => window.Samurai.Anim.evalEase({ type: 'spring', stiffness: 260, damping: 18 }, t, 1.0))""")
        browser.close()
    assert run1 == run2, f"Determinism failed: {run1} vs {run2}"
    print(f"PASS test_anim_solve: types=5/5, max_rk4_err={max_rk4_err:.2e} (RK4 dt=1e-4), determinism=EXACT")


if __name__ == "__main__":
    run_tests()
