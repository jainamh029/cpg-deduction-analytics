"""Seeded generator for the SYNTHETIC "Northfield Foods" dataset (fictional; not any real company).

All money is handled as integer cents internally and exposed as dollars with two decimals, so
reconciliation (invoice gross = sum of lines, payments + deductions = gross) is exact.
"""

from __future__ import annotations

import calendar
import hashlib
from datetime import date

import numpy as np
import pandas as pd

from .config import (
    ANOMALY_INVOICE_MONTH,
    ANOMALY_MULTIPLIER,
    CATEGORIES,
    CHANNELS,
    MONTH_SEASONALITY,
    NULL_DISPUTE_PROB,
    NULL_WIN_PROB,
    PROBLEM_SKUS,
    PROMO_TYPES,
    REASON_PARAMS,
    REASONS,
    RETAILER_A,
    RETAILER_ANOMALY,
    RETAILER_B,
    RETAILER_SHARES,
    WINNABILITY_SD,
    Config,
)

Tables = dict[str, pd.DataFrame]

RETAILER_TERMS = (30, 45, 60, 30, 45, 30, 60, 45, 30, 60, 45, 30)
RETAILER_DISCOUNT = (0.06, 0.08, 0.05, 0.09, 0.07, 0.10, 0.04, 0.08, 0.06, 0.07, 0.09, 0.05)
RETAILER_LATE_DAYS = (4, 6, 3, 7, 5, 8, 4, 6, 5, 7, 3, 5)  # average days paid after due date
RETAILER_REGIONS = (
    "National", "Northeast", "Southeast", "Midwest", "West", "National",
    "Southeast", "Midwest", "Northeast", "West", "National", "Midwest",
)  # fmt: skip
LINES_PER_INVOICE_MAX = 14
B_LAG_DRIFT_START = date(2025, 1, 1)
B_LAG_DRIFT_DAYS = 181  # drift ramps up over ~6 months, then plateaus
B_LAG_DRIFT_TOTAL = 12.0
FINE_PROBLEM_SKU_PROB = 0.80
PROBLEM_SKU_ON_INVOICE_PROB = 0.85
MAX_DEDUCTION_SHARE = 0.45
UNDISPUTED_STALE_DAYS = 90


def _streams(seed: int) -> dict[str, np.random.Generator]:
    names = (
        "skus",
        "invoices",
        "lines",
        "deductions",
        "disputes",
        "payments",
        "promotions",
        "bias",
    )
    children = np.random.SeedSequence(seed).spawn(len(names))
    return {n: np.random.default_rng(c) for n, c in zip(names, children, strict=True)}


def _month_starts(start: date, end: date) -> list[date]:
    months, cur = [], date(start.year, start.month, 1)
    while cur <= end:
        months.append(cur)
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    return months


def _d64(d: date) -> np.datetime64:
    return np.datetime64(d.isoformat(), "D")


def make_retailers() -> pd.DataFrame:
    n = len(RETAILER_SHARES)
    return pd.DataFrame(
        {
            "retailer_id": np.arange(1, n + 1),
            "name": [f"Retailer {chr(65 + i)}" for i in range(n)],
            "channel": [CHANNELS[i % len(CHANNELS)] for i in range(n)],
            "region": RETAILER_REGIONS,
            "payment_terms_days": RETAILER_TERMS,
        }
    )


def make_skus(cfg: Config, rng: np.random.Generator) -> pd.DataFrame:
    price = np.clip(rng.lognormal(np.log(18), 0.5, cfg.n_skus), 2.5, 90).round(2)
    cogs = (price * rng.uniform(0.45, 0.70, cfg.n_skus)).round(2)
    return pd.DataFrame(
        {
            "sku_id": np.arange(1, cfg.n_skus + 1),
            "category": [CATEGORIES[i % len(CATEGORIES)] for i in range(cfg.n_skus)],
            "list_price": price,
            "cogs": cogs,
        }
    )


class _Invoices:
    """Column arrays for invoices and the SKU list on each invoice (needed for deduction SKUs)."""

    def __init__(self, ret, inv_date, gross_cents, n_lines, inv_skus, lines):
        self.ret = ret
        self.date = inv_date
        self.gross_cents = gross_cents
        self.n_lines = n_lines
        self.skus = inv_skus
        self.lines = lines


def _make_invoices(cfg: Config, rngs: dict, skus: pd.DataFrame) -> _Invoices:
    rng_inv, rng_ln = rngs["invoices"], rngs["lines"]
    n_sku = len(skus)
    list_cents = np.round(skus["list_price"].to_numpy() * 100).astype(np.int64)
    popularity = rng_ln.lognormal(0, 0.6, n_sku)
    discount = np.array(RETAILER_DISCOUNT)
    shares = np.array(RETAILER_SHARES)
    mean_invoice = 10 * skus["list_price"].mean() * (1 - discount.mean()) * 50.0
    months = _month_starts(cfg.start_date, cfg.end_date)

    ret_parts, date_parts, gross_parts, k_parts, sku_parts, line_parts = [], [], [], [], [], []
    offset = 0
    for t, ms in enumerate(months):
        growth = (1 + (cfg.yoy_growth if cfg.planted else 0.0)) ** ((t - 17.5) / 12)
        season = MONTH_SEASONALITY[ms.month - 1] if cfg.planted else 1.0
        revenue = cfg.annual_revenue / 12 * season * growth
        revenue *= rng_inv.lognormal(0, 0.03) * cfg.revenue_scale
        counts = rng_inv.poisson(revenue * shares / mean_invoice)
        ret = np.repeat(np.arange(1, len(shares) + 1), counts)
        n = ret.size
        day = rng_inv.integers(1, calendar.monthrange(ms.year, ms.month)[1] + 1, n)
        order = np.lexsort((ret, day))
        ret, day = ret[order], day[order]

        k = rng_ln.integers(6, LINES_PER_INVOICE_MAX + 1, n)
        keys = np.log(rng_ln.random((n, n_sku))) / popularity
        problem_prob = PROBLEM_SKU_ON_INVOICE_PROB if cfg.planted else 0.0
        has_problem = (ret == RETAILER_A) & (rng_ln.random(n) < problem_prob)
        keys[has_problem, PROBLEM_SKUS[0] - 1] = 1.0  # force-include: larger than any log key
        keys[has_problem, PROBLEM_SKUS[1] - 1] = 2.0
        top = np.argsort(-keys, axis=1)[:, :LINES_PER_INVOICE_MAX]
        qty = rng_ln.integers(10, 91, top.shape)
        price = np.round(
            list_cents[top]
            * (1 - discount[ret - 1])[:, None]
            * rng_ln.uniform(0.97, 1.03, top.shape)
        ).astype(np.int64)
        valid = np.arange(LINES_PER_INVOICE_MAX)[None, :] < k[:, None]
        row, col = np.nonzero(valid)
        gross = np.bincount(row, weights=(qty * price)[row, col], minlength=n).astype(np.int64)

        line_parts.append(
            pd.DataFrame(
                {
                    "invoice_id": offset + row + 1,
                    "sku_id": top[row, col] + 1,
                    "qty": qty[row, col],
                    "unit_price": price[row, col] / 100,
                }
            )
        )
        ret_parts.append(ret)
        date_parts.append(_d64(ms) + (day - 1).astype("timedelta64[D]"))
        gross_parts.append(gross)
        k_parts.append(k)
        sku_parts.append((top + 1).astype(np.int16))
        offset += n

    return _Invoices(
        np.concatenate(ret_parts),
        np.concatenate(date_parts),
        np.concatenate(gross_parts),
        np.concatenate(k_parts),
        np.concatenate(sku_parts),
        pd.concat(line_parts, ignore_index=True),
    )


def _invoice_frame(inv: _Invoices) -> pd.DataFrame:
    terms = np.array(RETAILER_TERMS)[inv.ret - 1]
    return pd.DataFrame(
        {
            "invoice_id": np.arange(1, inv.ret.size + 1),
            "retailer_id": inv.ret,
            "invoice_date": inv.date,
            "due_date": inv.date + terms.astype("timedelta64[D]"),
            "gross_amount": inv.gross_cents / 100,
        }
    )


def _reason_lag(reason: str, q4: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    lo_hi = {
        "shortage": (5, 30), "compliance_fine": (20, 60), "pricing": (10, 45),
        "damage": (10, 40), "other": (10, 60),
    }  # fmt: skip
    if reason == "promo":  # post-Q4 promo claims arrive late, so they pile up in Jan-Feb
        return np.where(q4, rng.integers(45, 91, q4.size), rng.integers(25, 71, q4.size))
    lo, hi = lo_hi[reason]
    return rng.integers(lo, hi + 1, q4.size)


def _make_deductions(cfg: Config, rng: np.random.Generator, inv: _Invoices) -> pd.DataFrame:
    n_ret = len(RETAILER_SHARES)
    months = pd.DatetimeIndex(inv.date).month.to_numpy()
    years = pd.DatetimeIndex(inv.date).year.to_numpy()
    year_idx = years - cfg.start_date.year
    q4 = months >= 10
    effect = rng.lognormal(0, 0.2, (n_ret, len(REASONS)))
    effect[:, REASONS.index("compliance_fine")] = rng.lognormal(0, 0.25, n_ret)
    a_effect = rng.lognormal(np.log(3.0), 0.12)
    if cfg.planted:
        effect[RETAILER_A - 1, REASONS.index("compliance_fine")] = a_effect
    promo_mult = rng.lognormal(np.log(2.4), 0.25, (n_ret, 3))
    if not cfg.planted:
        promo_mult = np.ones((n_ret, 3))
    anomaly_month = (
        (pd.DatetimeIndex(inv.date).to_period("M") == pd.Period(ANOMALY_INVOICE_MONTH, "M"))
        & (inv.ret == RETAILER_ANOMALY)
    )  # fmt: skip
    problem_pair = (inv.skus[:, 0] == PROBLEM_SKUS[1]) & (inv.skus[:, 1] == PROBLEM_SKUS[0])

    parts = []
    for k, reason in enumerate(REASONS):
        par = REASON_PARAMS[reason]
        p = par["p"] * effect[inv.ret - 1, k]
        if reason == "promo":
            p = np.where(q4, p * promo_mult[inv.ret - 1, np.clip(year_idx, 0, 2)], p)
        if reason == "shortage":
            p = np.where(anomaly_month, p * (ANOMALY_MULTIPLIER if cfg.planted else 1.0), p)
        hit = np.nonzero(rng.random(inv.ret.size) < np.clip(p, 0, 0.95))[0]
        z = rng.standard_normal(hit.size)
        if "flat" in par:
            cents = par["flat"] * 100 * np.exp(0.5 * z - 0.125)
        else:
            cents = inv.gross_cents[hit] * par["frac"] * np.exp(0.6 * z - 0.18)
        lag = _reason_lag(reason, q4[hit], rng)
        attributed = rng.random(hit.size) >= par["sku_null"]
        pos = np.floor(rng.random(hit.size) * inv.n_lines[hit]).astype(int)
        if reason == "compliance_fine":
            pick_problem = (
                (inv.ret[hit] == RETAILER_A)
                & problem_pair[hit]
                & (rng.random(hit.size) < (FINE_PROBLEM_SKU_PROB if cfg.planted else 0.0))
            )
            pos = np.where(pick_problem, rng.integers(0, 2, hit.size), pos)
        sku = inv.skus[hit, pos].astype(float)
        sku[~attributed] = np.nan
        parts.append(
            pd.DataFrame(
                {
                    "inv_idx": hit,
                    "reason_code": reason,
                    "reason_order": k,
                    "cents": np.maximum(100, np.round(cents)),
                    "lag": lag,
                    "sku_id": sku,
                }
            )
        )
    ded = pd.concat(parts, ignore_index=True)

    total = ded.groupby("inv_idx")["cents"].transform("sum")
    cap = MAX_DEDUCTION_SHARE * inv.gross_cents[ded["inv_idx"].to_numpy()]
    ded["cents"] = np.where(
        total > cap, np.maximum(100, np.floor(ded["cents"] * cap / total)), ded["cents"]
    )
    idx = ded["inv_idx"].to_numpy()
    ded["deduction_date"] = inv.date[idx] + ded["lag"].to_numpy().astype("timedelta64[D]")
    ded = ded[ded["deduction_date"] <= _d64(cfg.end_date)]
    ded = ded.sort_values(["deduction_date", "inv_idx", "reason_order"], kind="stable")
    ded = ded.reset_index(drop=True)
    return pd.DataFrame(
        {
            "deduction_id": np.arange(1, len(ded) + 1),
            "invoice_id": ded["inv_idx"].to_numpy() + 1,
            "retailer_id": inv.ret[ded["inv_idx"].to_numpy()],
            "sku_id": pd.array(ded["sku_id"].to_numpy(), dtype="Int64"),
            "deduction_date": ded["deduction_date"].to_numpy(),
            "amount": ded["cents"].to_numpy().astype(np.int64) / 100,
            "reason_code": ded["reason_code"].to_numpy(),
            "status": "open",
        }
    )


def _make_disputes(
    cfg: Config, rng: np.random.Generator, ded: pd.DataFrame, bias_rng: np.random.Generator
) -> tuple:
    """Return (disputes, deductions-with-final-status, true win probability per deduction)."""
    n = len(ded)
    n_ret = len(RETAILER_SHARES)
    reason_idx = ded["reason_code"].map({r: i for i, r in enumerate(REASONS)}).to_numpy()
    base_d = np.array([REASON_PARAMS[r]["dispute"] for r in REASONS])
    base_w = np.array([REASON_PARAMS[r]["win"] for r in REASONS])
    if not cfg.planted:
        base_d, base_w = (
            np.full(len(REASONS), NULL_DISPUTE_PROB),
            np.full(len(REASONS), NULL_WIN_PROB),
        )
    ret = ded["retailer_id"].to_numpy() - 1
    dispute_jitter = rng.lognormal(0, 0.15, (n_ret, len(REASONS)))
    win_jitter = rng.normal(0, 0.04, n_ret)

    winnability = bias_rng.standard_normal(n) if cfg.dispute_bias is not None else np.zeros(n)
    selection = 0.0 if cfg.dispute_bias is None else cfg.dispute_bias
    p_dispute = base_d[reason_idx] * dispute_jitter[ret, reason_idx]
    p_dispute = np.clip(p_dispute * np.exp(selection * winnability - selection**2 / 2), 0, 0.9)
    disputed = rng.random(n) < p_dispute
    filing_lag = np.clip(np.round(rng.gamma(2.0, 12.0, n)) + 3, 1, 120).astype(int)
    ded_date = ded["deduction_date"].to_numpy()
    filed = ded_date + filing_lag.astype("timedelta64[D]")
    disputed &= filed <= _d64(cfg.end_date)

    lag_mult = np.select(
        [filing_lag <= 14, filing_lag <= 30, filing_lag <= 60], [1.10, 1.0, 0.85], 0.65
    )
    if not cfg.planted:
        lag_mult = np.ones(n)
    spread = WINNABILITY_SD * winnability if cfg.dispute_bias is not None else 0.0
    p_win = np.clip(base_w[reason_idx] * lag_mult + win_jitter[ret] + spread, 0.02, 0.97)
    win = rng.random(n) < p_win
    partial = win & (rng.random(n) < 0.30)
    resolve_days = np.round(rng.gamma(3.0, 12.0, n)).astype(int) + 7
    resolved = filed + resolve_days.astype("timedelta64[D]")
    pending = resolved > _d64(cfg.end_date)

    outcome = np.where(
        pending, "pending", np.where(partial, "partial", np.where(win, "won", "lost"))
    )
    cents = np.round(ded["amount"].to_numpy() * 100)
    recovered = np.where(
        pending | ~win, 0, np.where(partial, np.round(cents * rng.uniform(0.3, 0.8, n)), cents)
    )

    d_idx = np.nonzero(disputed)[0]
    disputes = pd.DataFrame(
        {
            "dispute_id": np.arange(1, d_idx.size + 1),
            "deduction_id": ded["deduction_id"].to_numpy()[d_idx],
            "filed_date": filed[d_idx],
            "resolved_date": np.where(pending[d_idx], np.datetime64("NaT"), resolved[d_idx]),
            "outcome": outcome[d_idx],
            "recovered_amount": recovered[d_idx] / 100,
        }
    )

    age = (_d64(cfg.end_date) - ded_date).astype(int)
    stale_u = rng.random(n)
    undisputed_status = np.where(
        age <= UNDISPUTED_STALE_DAYS,
        "open",
        np.select([stale_u < 0.25, stale_u < 0.70], ["open", "written_off"], "accepted"),
    )
    disputed_status = np.select(
        [outcome == "pending", outcome == "lost"], ["disputed", "accepted"], "recovered"
    )
    status = np.where(disputed, disputed_status, undisputed_status)
    return disputes, ded.assign(status=status), p_win


def _make_payments(cfg: Config, rng: np.random.Generator, inv: _Invoices, ded: pd.DataFrame):
    n = inv.ret.size
    ded_cents = np.bincount(
        ded["invoice_id"].to_numpy() - 1,
        weights=np.round(ded["amount"].to_numpy() * 100),
        minlength=n,
    )
    terms = np.array(RETAILER_TERMS)[inv.ret - 1]
    late = np.array(RETAILER_LATE_DAYS)[inv.ret - 1] + rng.normal(0, 4, n)
    days_in = (inv.date - _d64(B_LAG_DRIFT_START)).astype(int)
    drift = B_LAG_DRIFT_TOTAL * np.clip(days_in / B_LAG_DRIFT_DAYS, 0, 1)
    late = late + np.where((inv.ret == RETAILER_B) & cfg.planted, drift, 0)
    paid_date = inv.date + np.maximum(1, np.round(terms + late)).astype(int).astype(
        "timedelta64[D]"
    )
    keep = np.nonzero(paid_date <= _d64(cfg.end_date))[0]
    return pd.DataFrame(
        {
            "payment_id": np.arange(1, keep.size + 1),
            "invoice_id": keep + 1,
            "paid_date": paid_date[keep],
            "paid_amount": (inv.gross_cents[keep] - ded_cents[keep]) / 100,
        }
    )


def _make_promotions(cfg: Config, rng: np.random.Generator) -> pd.DataFrame:
    rows = []
    month_w = np.array(MONTH_SEASONALITY)
    month_w = np.where(np.arange(12) >= 9, 2.0, 1.0) * month_w
    month_w = month_w / month_w.sum()
    for year in range(cfg.start_date.year, cfg.end_date.year + 1):
        for r, share in enumerate(RETAILER_SHARES, start=1):
            for _ in range(rng.poisson(8 + 60 * share)):
                month = int(rng.choice(12, p=month_w)) + 1
                start = date(year, month, int(rng.integers(1, 29)))
                end = min(
                    date.fromordinal(start.toordinal() + int(rng.integers(14, 43))), cfg.end_date
                )
                rows.append(
                    {
                        "retailer_id": r,
                        "sku_id": int(rng.integers(1, cfg.n_skus + 1)),
                        "start_date": start,
                        "end_date": end,
                        "promo_type": PROMO_TYPES[int(rng.integers(0, len(PROMO_TYPES)))],
                        "planned_spend": round(
                            float(rng.lognormal(np.log(20000), 0.6)) * (0.5 + 3 * share), 2
                        ),
                    }
                )
    promos = pd.DataFrame(rows)
    promos = promos[promos["start_date"] <= cfg.end_date].sort_values(["start_date", "retailer_id"])
    promos = promos.reset_index(drop=True)
    promos.insert(0, "promo_id", np.arange(1, len(promos) + 1))
    for col in ("start_date", "end_date"):
        promos[col] = pd.to_datetime(promos[col])
    return promos


def generate_with_truth(cfg: Config | None = None) -> tuple[Tables, pd.DataFrame]:
    """Clean tables plus an ORACLE table (deduction_id, p_win_true): the probability each deduction would win
    if disputed. The oracle is for audits only; it is never loaded into the warehouse."""
    cfg = cfg or Config()
    rngs = _streams(cfg.seed)
    retailers = make_retailers()
    skus = make_skus(cfg, rngs["skus"])
    inv = _make_invoices(cfg, rngs, skus)
    deductions = _make_deductions(cfg, rngs["deductions"], inv)
    disputes, deductions, p_win = _make_disputes(cfg, rngs["disputes"], deductions, rngs["bias"])
    payments = _make_payments(cfg, rngs["payments"], inv, deductions)
    tables = {
        "retailers": retailers,
        "skus": skus,
        "invoices": _invoice_frame(inv),
        "invoice_lines": inv.lines,
        "payments": payments,
        "deductions": deductions,
        "disputes": disputes,
        "promotions": _make_promotions(cfg, rngs["promotions"]),
    }
    truth = pd.DataFrame(
        {"deduction_id": deductions["deduction_id"].to_numpy(), "p_win_true": p_win}
    )
    return tables, truth


def generate(cfg: Config | None = None) -> Tables:
    """Generate the clean dataset. Same config -> identical tables."""
    return generate_with_truth(cfg)[0]


def table_hashes(tables: Tables) -> dict[str, str]:
    """Content hash per table (used by the determinism test)."""
    out = {}
    for name, df in tables.items():
        row_hashes = pd.util.hash_pandas_object(df, index=False).to_numpy().tobytes()
        out[name] = hashlib.sha256(row_hashes + ",".join(df.columns).encode()).hexdigest()
    return out
