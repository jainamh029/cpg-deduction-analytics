"""Phase 5: forecast tests. Baseline against hand values, no leakage, dates, and a stable output schema."""

import duckdb
import numpy as np
import pandas as pd
import pytest

from forecast import model
from forecast.model import (
    HORIZON,
    backtest,
    compare_models,
    interval_coverage,
    mape,
    mase,
    origins,
    seasonal_naive,
    seasonal_naive_scale,
    smape,
    wape,
)
from forecast.run import (
    FORECASTS_COLUMNS,
    FORWARD_COLUMNS,
    MAPE_COLUMNS,
    load_monthly,
)

START = "2023-04-01"
N_MONTHS = 33


def synthetic_monthly(n_retailers: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    months = pd.date_range(START, periods=N_MONTHS, freq="MS")
    season = 1 + 0.3 * np.sin(2 * np.pi * np.arange(N_MONTHS) / 12)
    data = {
        r: 1000
        * (r + 1)
        * season
        * (1 + 0.01 * np.arange(N_MONTHS))
        * rng.lognormal(0, 0.05, N_MONTHS)
        for r in range(1, n_retailers + 1)
    }
    return pd.DataFrame(data, index=months)


def test_seasonal_naive_matches_hand_computed_values():
    # Series 1..24 (Jan 2023 .. Dec 2024). Forecasting Jan, Feb, Mar 2025 = the same months of 2024
    # = positions 13, 14, 15 (1-based values 13, 14, 15).
    train = np.arange(1, 25, dtype=float)
    assert seasonal_naive(train, 3).tolist() == [13.0, 14.0, 15.0]
    assert seasonal_naive(train, 12).tolist() == list(range(13, 25))


def test_mape_and_wape_match_hand_computed_values():
    actual, forecast = np.array([100.0, 200.0]), np.array([110.0, 150.0])
    assert mape(actual, forecast) == pytest.approx((10 / 100 + 50 / 200) / 2)  # 0.175
    assert wape(actual, forecast) == pytest.approx((10 + 50) / (100 + 200))  # 0.2


def test_origins_and_horizon_dates():
    monthly = synthetic_monthly(1)
    assert list(origins(N_MONTHS)) == list(range(24, 31))  # 7 folds, each with 3 months of actuals
    table = backtest(monthly)
    assert len(table) == 7 * HORIZON
    first = table.iloc[0]
    assert first["origin_month"] == pd.Timestamp("2025-04-01")
    assert table["target_month"].min() == pd.Timestamp("2025-04-01")
    assert table["target_month"].max() == pd.Timestamp("2025-12-01")
    expected_target = table.apply(
        lambda r: r["origin_month"] + pd.DateOffset(months=int(r["horizon"]) - 1), axis=1
    )
    assert (table["target_month"] == expected_target).all()
    assert sorted(table["horizon"].unique()) == [1, 2, 3]


def test_every_fold_trains_only_on_months_before_its_origin(monkeypatch):
    monthly = synthetic_monthly(2)
    seen = []

    def spy(name, fn):
        def wrapped(train, horizon):
            seen.append((len(train), train.copy()))
            return fn(train, horizon)

        return wrapped

    for name, fn in dict(model.MODELS).items():
        monkeypatch.setitem(model.MODELS, name, spy(name, fn))
    backtest(monthly)
    assert seen
    for length, train in seen:
        # Training data is exactly an initial segment of one retailer's history: nothing at or after the origin.
        matches = [np.array_equal(train, monthly[c].to_numpy()[:length]) for c in monthly.columns]
        assert any(matches)
        assert length < N_MONTHS - HORIZON + 1


def test_changing_future_actuals_never_changes_forecasts():
    monthly = synthetic_monthly(2)
    altered = monthly.copy()
    altered.iloc[30:] = altered.iloc[30:] * 10  # the last three months only exist as targets
    a, b = backtest(monthly), backtest(altered)
    for col in model.MODELS:
        assert np.allclose(a[col], b[col], equal_nan=True)
    assert not np.allclose(a["actual"], b["actual"])  # sanity: the actuals did change


def test_backtest_is_deterministic():
    monthly = synthetic_monthly(1)
    first, second = backtest(monthly), backtest(monthly)
    pd.testing.assert_frame_equal(first, second)


def test_forecast_inputs_match_raw_deductions(built_warehouse):
    con = duckdb.connect(str(built_warehouse), read_only=True)
    monthly = load_monthly(con)
    raw_total = con.execute(
        "select sum(amount) from raw.deductions where deduction_date >= date '2023-04-01'"
    ).fetchone()[0]
    con.close()
    assert len(monthly) == N_MONTHS
    assert monthly.index.min() == pd.Timestamp(START)
    assert monthly.index.max() == pd.Timestamp("2025-12-01")
    assert monthly.to_numpy().sum() == pytest.approx(float(raw_total))


def test_result_files_schema_and_contents(forecast_results, built_warehouse):
    forecasts = pd.read_csv(forecast_results / "backtest_forecasts.csv")
    scores = pd.read_csv(forecast_results / "backtest_mape.csv")
    forward = pd.read_csv(forecast_results / "forward_forecast.csv", parse_dates=["month"])
    assert list(forecasts.columns) == FORECASTS_COLUMNS
    assert list(scores.columns) == MAPE_COLUMNS
    assert list(forward.columns) == FORWARD_COLUMNS
    assert len(forecasts) == 12 * 7 * HORIZON
    assert len(scores) == 12 * 2
    assert set(scores["model"]) == {"seasonal_naive", "holt_winters"}
    assert forward["month"].min() == pd.Timestamp("2026-01-01")
    assert forward["month"].max() == pd.Timestamp("2026-03-01")
    assert len(forward) == 12 * HORIZON
    assert (forward["hw_p10"] <= forward["hw_p90"]).all()
    # The seasonal-naive forward value for Jan 2026 is the Jan 2025 actual (independent raw query).
    con = duckdb.connect(str(built_warehouse), read_only=True)
    jan_2025 = con.execute(
        "select sum(amount) from raw.deductions where retailer_id = 1 "
        "and deduction_date >= date '2025-01-01' and deduction_date < date '2025-02-01'"
    ).fetchone()[0]
    con.close()
    row = forward[(forward["retailer_id"] == 1) & (forward["month"] == "2026-01-01")].iloc[0]
    assert row["seasonal_naive"] == pytest.approx(float(jan_2025))


def test_scores_match_recomputation_from_forecasts(forecast_results):
    forecasts = pd.read_csv(forecast_results / "backtest_forecasts.csv")
    scores = pd.read_csv(forecast_results / "backtest_mape.csv").set_index(["retailer_id", "model"])
    one = forecasts[forecasts["retailer_id"] == 3]
    expected = np.mean(np.abs(one["actual"] - one["seasonal_naive"]) / one["actual"])
    assert scores.loc[(3, "seasonal_naive"), "mape"] == pytest.approx(expected)


def test_smape_and_mase_match_hand_computed_values():
    actual, forecast = np.array([100.0, 200.0]), np.array([110.0, 150.0])
    # sMAPE = mean(2*10/(100+110), 2*50/(200+150)) = mean(20/210, 100/350) = (0.095238 + 0.285714) / 2
    assert smape(actual, forecast) == pytest.approx((20 / 210 + 100 / 350) / 2)
    # Training window 1..24: every 12-month difference is 12, so the seasonal-naive scale is 12.
    scale = seasonal_naive_scale(np.arange(1.0, 25.0))
    assert scale == 12.0
    # Errors 6 and 18 -> scaled 0.5 and 1.5 -> MASE = 1.0.
    assert mase(
        np.array([10.0, 30.0]), np.array([4.0, 12.0]), np.array([scale, scale])
    ) == pytest.approx(1.0)


def test_comparison_of_identical_models_shows_no_difference_and_is_deterministic():
    table = backtest(synthetic_monthly(3))
    table["holt_winters"] = table[
        "seasonal_naive"
    ]  # identical forecasts -> every origin difference is 0
    first = compare_models(table, n_boot=500)
    assert first["mean_diff_mape"] == 0 and first["boot_ci_low"] == 0 == first["boot_ci_high"]
    assert first["origins_hw_better"] == 0
    assert compare_models(table, n_boot=500) == first  # seeded


def test_comparison_detects_a_clearly_better_model():
    table = backtest(synthetic_monthly(3))
    table["holt_winters"] = table["actual"] * 1.01  # 1% error everywhere
    table["seasonal_naive"] = table["actual"] * 1.30  # 30% error everywhere
    result = compare_models(table, n_boot=2000)
    assert result["origins_hw_better"] == result["n_origins"]
    assert result["boot_ci_low"] > 0.2


def test_interval_coverage_is_a_fraction_and_out_of_sample_uses_earlier_origins_only():
    table = backtest(synthetic_monthly(3))
    cov = interval_coverage(table)
    assert 0 <= cov["out_of_sample_coverage"] <= 1 and 0 <= cov["in_sample_coverage"] <= 1
    assert (
        cov["out_of_sample_points"]
        == len(table) - table["origin_month"].eq(table["origin_month"].min()).sum()
    )


# ---- audit: hand-computed tests added after mutmut showed the comparison/coverage code was under-tested -------------


def small_table(rows):
    """rows: (retailer_id, origin_month, horizon, actual, mase_scale, naive, hw) -> a backtest-style frame."""
    cols = [
        "retailer_id",
        "origin_month",
        "horizon",
        "actual",
        "mase_scale",
        "seasonal_naive",
        "holt_winters",
    ]
    frame = pd.DataFrame(rows, columns=cols)
    frame["origin_month"] = pd.to_datetime(frame["origin_month"])
    return frame


def test_score_matches_hand_computed_errors():
    table = small_table([
        (1, "2025-01-01", 1, 100.0, 10.0, 110.0, 100.0),
        (1, "2025-02-01", 1, 200.0, 10.0, 150.0, 220.0),
    ])  # fmt: skip
    from forecast.model import score

    got = score(table).set_index("model")
    # Naive errors: 10 on 100 (10%), 50 on 200 (25%). MAPE = (0.10 + 0.25) / 2 = 0.175.
    assert got.loc["seasonal_naive", "mape"] == pytest.approx(0.175)
    assert got.loc["seasonal_naive", "smape"] == pytest.approx((20 / 210 + 100 / 350) / 2)
    assert got.loc["seasonal_naive", "mase"] == pytest.approx(
        (10 / 10 + 50 / 10) / 2
    )  # scale 10 -> (1 + 5) / 2 = 3
    assert got.loc["seasonal_naive", "wape"] == pytest.approx(60 / 300)
    # Holt-Winters errors: 0 on 100, 20 on 200 (10%). MAPE = 0.05; WAPE = 20 / 300.
    assert got.loc["holt_winters", "mape"] == pytest.approx(0.05)
    assert got.loc["holt_winters", "wape"] == pytest.approx(20 / 300)
    assert (got["n_forecasts"] == 2).all()


def test_origin_losses_are_mean_absolute_percentage_errors_per_origin():
    from forecast.model import origin_losses

    table = small_table([
        (1, "2025-01-01", 1, 100.0, 1.0, 110.0, 100.0),
        (2, "2025-01-01", 1, 200.0, 1.0, 150.0, 220.0),
        (1, "2025-02-01", 1, 50.0, 1.0, 50.0, 40.0),
    ])  # fmt: skip
    got = origin_losses(table)
    # Origin 1: naive APEs 10/100 = 0.10 and 50/200 = 0.25 -> 0.175; HW APEs 0 and 20/200 = 0.10 -> 0.05.
    assert got.loc[pd.Timestamp("2025-01-01"), "seasonal_naive"] == pytest.approx(0.175)
    assert got.loc[pd.Timestamp("2025-01-01"), "holt_winters"] == pytest.approx(0.05)
    # Origin 2: naive APE 0; HW APE 10/50 = 0.20.
    assert got.loc[pd.Timestamp("2025-02-01"), "seasonal_naive"] == 0
    assert got.loc[pd.Timestamp("2025-02-01"), "holt_winters"] == pytest.approx(0.20)


def test_comparison_statistics_match_hand_arithmetic():
    # 7 origins, one forecast each. Holt-Winters APE is a constant 0.10; the naive APE is 0.10 + d with
    # d = 0.02, 0.04, ..., 0.14, so the per-origin MAPE advantage is d: mean 0.08, sd = 0.02 * sqrt(7 * 8 / 12) = 0.043205.
    # DM = 0.08 / (0.043205 / sqrt(7)) = 4.899; HLN factor sqrt((7 + 1 - 2*3 + 3*2/7) / 7) = sqrt(2.857143 / 7) = 0.638877;
    # corrected statistic = 4.899 * 0.638877 = 3.130.
    d = [0.02, 0.04, 0.06, 0.08, 0.10, 0.12, 0.14]
    rows = [
        (1, f"2025-{m:02d}-01", 1, 100.0, 1.0, 100.0 * (1 + 0.10 + x), 110.0)
        for m, x in enumerate(d, start=1)
    ]
    result = compare_models(small_table(rows), n_boot=10_000)
    assert result["n_origins"] == 7 and result["origins_hw_better"] == 7
    assert result["mean_diff_mape"] == pytest.approx(0.08)
    assert result["dm_hln_statistic"] == pytest.approx(3.130, abs=0.002)
    # Bootstrap over the 7 origins, seed 20260101: recompute the percentiles independently.
    boot = (
        np.random.default_rng(20260101)
        .choice(np.array(d), size=(10_000, 7), replace=True)
        .mean(axis=1)
    )
    assert result["boot_ci_low"] == pytest.approx(np.percentile(boot, 2.5))
    assert result["boot_ci_high"] == pytest.approx(np.percentile(boot, 97.5))
    assert 0.02 <= result["boot_ci_low"] < 0.08 < result["boot_ci_high"] <= 0.14
    assert result["boot_p_value"] == pytest.approx(2 * min((boot <= 0).mean(), (boot >= 0).mean()))


def test_sign_test_over_retailers_matches_the_binomial_hand_value():
    table = backtest(synthetic_monthly(12))
    table["holt_winters"] = table["actual"] * 1.01
    table["seasonal_naive"] = table["actual"] * 1.30
    result = compare_models(table, n_boot=200)
    assert result["retailers"] == 12 and result["retailers_hw_better"] == 12
    assert result["sign_test_p_value"] == pytest.approx(2 * 0.5**12)  # 12 of 12 wins: 2 / 4096


def test_interval_coverage_matches_hand_counts():
    # Three origins x four retailers, horizon 1. Every ratio actual/forecast is 1 except one 2 in the LAST origin.
    rows = [(r, f"2025-0{o}-01", 1, 100.0, 1.0, 100.0, 100.0) for o in (1, 2) for r in range(4)]
    rows += [(r, "2025-03-01", 1, 200.0 if r == 0 else 100.0, 1.0, 100.0, 100.0) for r in range(4)]
    cov = interval_coverage(small_table(rows), nominal=0.8)
    # In-sample: 12 ratios, eleven 1s and one 2; the 10%-90% band is [1, 1], so 11 of 12 are inside.
    assert cov["in_sample_coverage"] == pytest.approx(11 / 12)
    # Out-of-sample: origin 2 is judged by origin 1's band [1, 1] (4 of 4 inside); origin 3 by origins 1-2 (3 of 4 inside).
    assert cov["out_of_sample_coverage"] == pytest.approx(7 / 8)
    assert cov["out_of_sample_points"] == 8 and cov["nominal"] == 0.8
