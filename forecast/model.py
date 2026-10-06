"""Forecast models and the rolling-origin backtest (SYNTHETIC data).

Two models only:
  * seasonal naive: the value from the same month one year earlier (the baseline)
  * Holt-Winters: damped additive trend + MULTIPLICATIVE seasonality (statsmodels ExponentialSmoothing).
    The specification was fixed before any backtest was run and is not tuned.

Backtest: expanding window, rolling origin. A fold with origin `o` trains on months [0, o) only and
forecasts months [o, o + horizon). Nothing at or after the origin ever reaches a model.
"""

from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
from scipy import stats
from statsmodels.tsa.holtwinters import ExponentialSmoothing

SEASON = 12
HORIZON = 3
FIRST_ORIGIN = 24  # two full seasonal cycles of training before the first forecast


def seasonal_naive(train: np.ndarray, horizon: int) -> np.ndarray:
    """Forecast for step h = the value 12 months before the target month."""
    return train[len(train) - SEASON + np.arange(horizon) % SEASON].astype(float)


def holt_winters(train: np.ndarray, horizon: int) -> np.ndarray:
    """Damped-trend, multiplicative-seasonal Holt-Winters; NaN if the fit fails. Floored at 0."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            fit = ExponentialSmoothing(
                np.asarray(train, dtype=float),
                trend="add",
                damped_trend=True,
                seasonal="mul",
                seasonal_periods=SEASON,
                initialization_method="estimated",
            ).fit()
            forecast = np.asarray(fit.forecast(horizon), dtype=float)
    except (ValueError, np.linalg.LinAlgError):
        return np.full(horizon, np.nan)
    return np.maximum(forecast, 0.0)


MODELS = {"seasonal_naive": seasonal_naive, "holt_winters": holt_winters}


def origins(n_months: int, first_origin: int = FIRST_ORIGIN, horizon: int = HORIZON) -> range:
    """Fold origins: each needs `horizon` months of actuals after it."""
    return range(first_origin, n_months - horizon + 1)


def backtest(
    monthly: pd.DataFrame, first_origin: int = FIRST_ORIGIN, horizon: int = HORIZON
) -> pd.DataFrame:
    """Long table: retailer_id, origin_month, target_month, horizon, actual, one column per model.

    `monthly` has one row per month (sorted DatetimeIndex) and one column per retailer.
    `origin_month` is the first month NOT in the training window.
    """
    rows = []
    for origin in origins(len(monthly), first_origin, horizon):
        train, test = monthly.iloc[:origin], monthly.iloc[origin : origin + horizon]
        for retailer in monthly.columns:
            history = train[retailer].to_numpy()
            forecasts = {name: fn(history, horizon) for name, fn in MODELS.items()}
            for h in range(horizon):
                rows.append(
                    {
                        "retailer_id": retailer,
                        "origin_month": monthly.index[origin],
                        "target_month": test.index[h],
                        "horizon": h + 1,
                        "actual": float(test[retailer].iloc[h]),
                        "mase_scale": seasonal_naive_scale(history),
                        **{name: float(f[h]) for name, f in forecasts.items()},
                    }
                )
    return pd.DataFrame(rows)


def seasonal_naive_scale(history: np.ndarray) -> float:
    """MASE scale: mean absolute in-sample error of the seasonal-naive method on the training window."""
    return float(np.mean(np.abs(history[SEASON:] - history[:-SEASON])))


def smape(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Symmetric MAPE: mean of 2|a - f| / (|a| + |f|); bounded, so tiny actuals cannot explode it."""
    return float(np.mean(2 * np.abs(actual - forecast) / (np.abs(actual) + np.abs(forecast))))


def mase(actual: np.ndarray, forecast: np.ndarray, scale: np.ndarray) -> float:
    """Mean absolute scaled error: |a - f| divided by the seasonal-naive in-sample MAE of its fold."""
    return float(np.mean(np.abs(actual - forecast) / scale))


def mape(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Mean absolute percentage error (actuals must be > 0)."""
    return float(np.mean(np.abs(actual - forecast) / actual))


def wape(actual: np.ndarray, forecast: np.ndarray) -> float:
    """Weighted absolute percentage error: sum|a - f| / sum a."""
    return float(np.sum(np.abs(actual - forecast)) / np.sum(actual))


def score(forecasts: pd.DataFrame) -> pd.DataFrame:
    """MAPE and WAPE per retailer and model, on points where every model produced a forecast."""
    complete = forecasts.dropna(subset=list(MODELS))
    rows = []
    for retailer, group in complete.groupby("retailer_id"):
        for model in MODELS:
            a, f = group["actual"].to_numpy(), group[model].to_numpy()
            rows.append(
                {
                    "retailer_id": retailer,
                    "model": model,
                    "mape": mape(a, f),
                    "smape": smape(a, f),
                    "mase": mase(a, f, group["mase_scale"].to_numpy()),
                    "wape": wape(a, f),
                    "n_forecasts": len(group),
                }
            )
    return pd.DataFrame(rows)


def forward_forecast(monthly: pd.DataFrame, backtested: pd.DataFrame, horizon: int = HORIZON):
    """Fit on all history and forecast the next `horizon` months.

    Intervals are empirical: the 10th/90th percentile of Holt-Winters' pooled backtest ratio
    actual / forecast at each horizon, applied to the forecast. They come from backtest errors only.
    """
    complete = backtested.dropna(subset=["holt_winters"]).assign(
        ratio=lambda d: d["actual"] / d["holt_winters"]
    )
    quantiles = complete.groupby("horizon")["ratio"].quantile([0.1, 0.9]).unstack()
    future = pd.date_range(monthly.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    rows = []
    for retailer in monthly.columns:
        history = monthly[retailer].to_numpy()
        naive, hw = seasonal_naive(history, horizon), holt_winters(history, horizon)
        for h in range(horizon):
            rows.append(
                {
                    "retailer_id": retailer,
                    "month": future[h],
                    "seasonal_naive": float(naive[h]),
                    "holt_winters": float(hw[h]),
                    "hw_p10": float(hw[h] * quantiles.loc[h + 1, 0.1]),
                    "hw_p90": float(hw[h] * quantiles.loc[h + 1, 0.9]),
                }
            )
    return pd.DataFrame(rows)


def origin_losses(forecasts: pd.DataFrame) -> pd.DataFrame:
    """Mean absolute percentage error per origin and model, pooled over retailers and horizons."""
    complete = forecasts.dropna(subset=list(MODELS))
    losses = {m: np.abs(complete["actual"] - complete[m]) / complete["actual"] for m in MODELS}
    frame = pd.DataFrame({"origin_month": complete["origin_month"], **losses})
    return frame.groupby("origin_month").mean()


def compare_models(forecasts: pd.DataFrame, n_boot: int = 10_000, seed: int = 20260101) -> dict:
    """Is Holt-Winters better than seasonal naive? Evidence from the backtest, resampling ORIGINS.

    d_o = pooled MAPE(naive) - pooled MAPE(Holt-Winters) at origin o (positive = Holt-Winters better).
    Reports a Diebold-Mariano style t statistic with the Harvey-Leybourne-Newbold small-sample correction
    (horizon h = 3), a bootstrap over origins, and a sign test across retailers.
    """
    losses = origin_losses(forecasts)
    d = (losses["seasonal_naive"] - losses["holt_winters"]).to_numpy()
    n, h = len(d), HORIZON
    spread = d.std(ddof=1)
    if spread == 0:  # identical loss at every origin: no evidence of any difference
        dm_hln, p_dm = 0.0, 1.0
    else:
        dm = d.mean() / (spread / np.sqrt(n))
        dm_hln = dm * np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
        p_dm = float(2 * stats.t.sf(abs(dm_hln), df=n - 1))
    rng = np.random.default_rng(seed)
    boot = rng.choice(d, size=(n_boot, n), replace=True).mean(axis=1)
    per_retailer = score(forecasts).pivot(index="retailer_id", columns="model", values="mape")
    wins = int((per_retailer["holt_winters"] < per_retailer["seasonal_naive"]).sum())
    return {
        "n_origins": n,
        "mean_diff_mape": float(d.mean()),  # naive - HW, in MAPE points (0.003 = 0.3 pts)
        "dm_hln_statistic": float(dm_hln),
        "dm_hln_p_value": p_dm,
        "boot_ci_low": float(np.percentile(boot, 2.5)),
        "boot_ci_high": float(np.percentile(boot, 97.5)),
        "boot_p_value": float(2 * min((boot <= 0).mean(), (boot >= 0).mean())),
        "origins_hw_better": int((d > 0).sum()),
        "retailers_hw_better": wins,
        "retailers": int(len(per_retailer)),
        "sign_test_p_value": float(stats.binomtest(wins, len(per_retailer), 0.5).pvalue),
    }


def interval_coverage(forecasts: pd.DataFrame, nominal: float = 0.8) -> dict:
    """Empirical coverage of the actual/forecast-ratio band used by the dashboard.

    in_sample: quantiles from ALL backtest ratios (what forward_forecast uses), so coverage is ~nominal by
    construction. out_of_sample: for each origin, quantiles come only from EARLIER origins; coverage is measured
    on that origin's points (the honest number).
    """
    complete = forecasts.dropna(subset=["holt_winters"]).assign(
        ratio=lambda d: d["actual"] / d["holt_winters"]
    )
    lo_q, hi_q = (1 - nominal) / 2, 1 - (1 - nominal) / 2
    q = complete.groupby("horizon")["ratio"].quantile([lo_q, hi_q]).unstack()
    inside = (complete["ratio"] >= complete["horizon"].map(q[lo_q])) & (
        complete["ratio"] <= complete["horizon"].map(q[hi_q])
    )
    hits, total = 0, 0
    origins_sorted = sorted(complete["origin_month"].unique())
    for origin in origins_sorted[1:]:
        past, now = (
            complete[complete["origin_month"] < origin],
            complete[complete["origin_month"] == origin],
        )
        bounds = past.groupby("horizon")["ratio"].quantile([lo_q, hi_q]).unstack()
        covered = (now["ratio"] >= now["horizon"].map(bounds[lo_q])) & (
            now["ratio"] <= now["horizon"].map(bounds[hi_q])
        )
        hits, total = hits + int(covered.sum()), total + len(now)
    return {
        "nominal": nominal,
        "in_sample_coverage": float(inside.mean()),
        "out_of_sample_coverage": hits / total,
        "out_of_sample_points": total,
    }


def small_denominator_report(forecasts: pd.DataFrame) -> dict:
    """How much do small series dominate MAPE? Compares MAPE and WAPE for the smallest and largest retailers."""
    complete = forecasts.dropna(subset=list(MODELS))
    by = complete.groupby("retailer_id")
    size = by["actual"].mean().sort_values()
    rows = {}
    for label, ids in (("smallest_3", size.index[:3]), ("largest_3", size.index[-3:])):
        sub = complete[complete["retailer_id"].isin(ids)]
        a, f = sub["actual"].to_numpy(), sub["seasonal_naive"].to_numpy()
        rows[label] = {
            "retailers": [int(i) for i in ids],
            "mape": mape(a, f),
            "wape": wape(a, f),
            "smape": smape(a, f),
        }
    ape = np.abs(complete["actual"] - complete["seasonal_naive"]) / complete["actual"]
    rows["corr_log_actual_vs_ape"] = float(np.corrcoef(np.log(complete["actual"]), ape)[0, 1])
    return rows
