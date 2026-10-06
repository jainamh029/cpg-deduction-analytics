"""Phase 5: forecast tests. Baseline against hand values, no leakage, dates, and a stable output schema."""

import duckdb
import numpy as np
import pandas as pd
import pytest

from forecast import model
from forecast.model import HORIZON, backtest, mape, origins, seasonal_naive, wape
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
