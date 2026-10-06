"""Measure the planted patterns directly on the generated tables (pandas, no warehouse needed).

Used by the generator tests (assert tolerance ranges) and by scripts/pattern_report.py
(writes target vs observed into PLANTED_PATTERNS.md).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import ANOMALY_INVOICE_MONTH, RETAILER_A, RETAILER_ANOMALY, RETAILER_B
from .generate import Tables

LAG_WINDOW = ("2025-01", "2025-06")  # invoice months over which Retailer B's drift is measured


def fine_ratio_a_vs_peers(t: Tables) -> float:
    gross = t["invoices"].groupby("retailer_id")["gross_amount"].sum()
    fines = (
        t["deductions"]
        .query("reason_code == 'compliance_fine'")
        .groupby("retailer_id")["amount"]
        .sum()
    )
    rate = fines / gross
    return float(rate[RETAILER_A] / rate.drop(RETAILER_A).median())


def fine_top2_share(t: Tables, attributed_only: bool) -> tuple[float, set[int]]:
    fines = t["deductions"].query("reason_code == 'compliance_fine'")
    fines = fines[fines["retailer_id"] == RETAILER_A]
    total = (
        fines.loc[fines["sku_id"].notna(), "amount"].sum()
        if attributed_only
        else fines["amount"].sum()
    )
    by_sku = fines.dropna(subset=["sku_id"]).groupby("sku_id")["amount"].sum().nlargest(2)
    return float(by_sku.sum() / total), {int(s) for s in by_sku.index}


def promo_spike_ratio(t: Tables) -> float:
    """Mean monthly promo-deduction $ in Jan-Feb vs Mar-Sep, over 2024 and 2025."""
    promo = t["deductions"].query("reason_code == 'promo'")
    monthly = promo.groupby(promo["deduction_date"].dt.to_period("M"))["amount"].sum()
    ratios = []
    for year in (2024, 2025):
        in_year = monthly[monthly.index.year == year]
        jan_feb = in_year[in_year.index.month <= 2].mean()
        baseline = in_year[(in_year.index.month >= 3) & (in_year.index.month <= 9)].mean()
        ratios.append(jan_feb / baseline)
    return float(np.mean(ratios))


def promo_dispute_rate(t: Tables) -> float:
    promo = t["deductions"].query("reason_code == 'promo'")
    return float(promo["deduction_id"].isin(t["disputes"]["deduction_id"]).mean())


def dispute_stats(t: Tables, reason: str, *, invert: bool = False) -> tuple[float, float]:
    """(dispute rate by count, win rate among resolved disputes) for one reason, or all others."""
    ded = t["deductions"]
    sel = ded[(ded["reason_code"] != reason) if invert else (ded["reason_code"] == reason)]
    disputes = t["disputes"].merge(sel[["deduction_id"]], on="deduction_id")
    resolved = disputes[disputes["outcome"] != "pending"]
    return len(disputes) / len(sel), float(resolved["outcome"].isin(["won", "partial"]).mean())


def lag_by_retailer_month(t: Tables) -> pd.DataFrame:
    inv = t["invoices"].merge(t["payments"], on="invoice_id")
    inv["lag"] = (inv["paid_date"] - inv["invoice_date"]).dt.days
    inv["month"] = inv["invoice_date"].dt.to_period("M")
    return inv.groupby(["retailer_id", "month"])["lag"].mean().reset_index()


def lag_slopes(t: Tables) -> pd.Series:
    """OLS slope (days per month) of mean payment lag over LAG_WINDOW, per retailer."""
    lag = lag_by_retailer_month(t)
    lo, hi = (pd.Period(p, "M") for p in LAG_WINDOW)
    lag = lag[(lag["month"] >= lo) & (lag["month"] <= hi)]
    return lag.groupby("retailer_id").apply(
        lambda g: np.polyfit(np.arange(len(g)), g["lag"].to_numpy(), 1)[0], include_groups=False
    )


def lag_rise_b(t: Tables) -> float:
    lag = lag_by_retailer_month(t)
    b = lag[lag["retailer_id"] == RETAILER_B].set_index("month")["lag"]
    return float(b.loc["2025-04":"2025-06"].mean() - b.loc["2025-01"])


def revenue_growth_and_seasonality(t: Tables) -> tuple[float, float]:
    """(average YoY growth, Q4 vs Q1-Q3 monthly revenue ratio)."""
    inv = t["invoices"]
    yearly = inv.groupby(inv["invoice_date"].dt.year)["gross_amount"].sum()
    growth = float(yearly.pct_change().dropna().mean())
    monthly = inv.groupby(inv["invoice_date"].dt.to_period("M"))["gross_amount"].sum()
    is_q4 = monthly.index.month >= 10
    return growth, float(monthly[is_q4].mean() / monthly[~is_q4].mean())


def anomaly_cell(t: Tables) -> float:
    """Planted anomaly: shortage $ for the anomaly retailer vs its own median monthly shortage $."""
    ded = t["deductions"]
    ded = ded[(ded["reason_code"] == "shortage") & (ded["retailer_id"] == RETAILER_ANOMALY)]
    monthly = ded.groupby(ded["deduction_date"].dt.to_period("M"))["amount"].sum()
    peak = monthly.loc[
        str(ANOMALY_INVOICE_MONTH)[:7] : str(ANOMALY_INVOICE_MONTH.replace(month=6))[:7]
    ].max()
    return float(peak / monthly.median())
