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
                        **{name: float(f[h]) for name, f in forecasts.items()},
                    }
                )
    return pd.DataFrame(rows)


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
