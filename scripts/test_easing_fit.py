"""Ground-truth synthetic tests for easing_fit.py."""
from easing_fit import _analytic_spring, _cubic_bezier, fit_series


def run_tests():
    # 1. Ground-truth linear (30 frames -> high confidence)
    lin_series = [[round(i * (1000.0 / 30.0), 2), 100.0 + 400.0 * (i / 29.0)] for i in range(30)]
    res_lin = fit_series(lin_series, fps=30.0)
    assert res_lin["low_confidence"] is False and res_lin["moving_frames"] >= 10
    assert res_lin["candidates"][0]["name"] == "linear" and res_lin["candidates"][0]["rmse"] < 1e-5, res_lin

    # 2. Ground-truth cubic-bezier(0.16, 1, 0.3, 1)
    bez_series = [[round(i * (1000.0 / 30.0), 2), 50.0 + 300.0 * _cubic_bezier(0.16, 1.0, 0.3, 1.0, i / 29.0)] for i in range(30)]
    res_bez = fit_series(bez_series, fps=30.0)
    bez_cand = [c for c in res_bez["candidates"] if c["name"] == "cubic-bezier"][0]
    assert bez_cand["rmse"] < 0.015, f"Cubic-bezier RMSE too high: {bez_cand}"

    # 3. Ground-truth spring(320, 18)
    spr_series = [[round(i * (1000.0 / 30.0), 2), 0.0 + 500.0 * _analytic_spring(i / 29.0, 1.0, 320.0, 18.0)] for i in range(30)]
    res_spr = fit_series(spr_series, fps=30.0)
    assert res_spr["candidates"][0]["name"] == "spring" and res_spr["candidates"][0]["rmse"] < 1e-4, res_spr

    # 4. Low-confidence flag when moving_frames < 10
    short_series = [[round(i * (1000.0 / 30.0), 2), 10.0 + 90.0 * (i / 6.0)] for i in range(7)]
    res_short = fit_series(short_series, fps=30.0)
    assert res_short["low_confidence"] is True and res_short["moving_frames"] < 10
    assert abs(res_short["time_uncertainty_ms"] - 16.67) < 0.05

    print(
        f"PASS test_easing_fit: linear_rmse={res_lin['candidates'][0]['rmse']:.2e}, "
        f"bezier_rmse={bez_cand['rmse']:.4f}, spring_rmse={res_spr['candidates'][0]['rmse']:.2e}, "
        f"low_confidence_flag=OK (uncertainty=+/-{res_short['time_uncertainty_ms']}ms)"
    )


if __name__ == "__main__":
    run_tests()
