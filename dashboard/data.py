"""Data access for the SYNTHETIC-data dashboard. Reads ONLY marts.*, metrics.* and forecast/results/.

Every ratio comes from a metrics.* macro; nothing here re-derives a metric. Functions take a DuckDB
connection and a Filters object so they can be tested without Streamlit.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_WAREHOUSE = ROOT / "warehouse" / "warehouse.duckdb"
DEFAULT_FORECAST_DIR = ROOT / "forecast" / "results"
WORKLIST_SIZE = 50
CFO_WINDOW_DAYS = 180
CFO_SCENARIO = "base"


def warehouse_path() -> Path:
    return Path(os.environ.get("WAREHOUSE_PATH", DEFAULT_WAREHOUSE))


def forecast_dir() -> Path:
    return Path(os.environ.get("FORECAST_DIR", DEFAULT_FORECAST_DIR))


def connect(path: Path | None = None) -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(path or warehouse_path()), read_only=True)


@dataclass(frozen=True)
class Filters:
    retailer_ids: tuple[int, ...]
    start: date
    end: date
    reasons: tuple[str, ...]


def _where(f: Filters, date_col: str, *, reasons: bool, alias: str = "") -> tuple[str, list]:
    """WHERE fragment and parameters for the retailer, date and (optionally) reason filters."""
    prefix = f"{alias}." if alias else ""
    parts = [f"list_contains(?::INTEGER[], {prefix}retailer_id)", f"{date_col} between ? and ?"]
    params: list = [list(f.retailer_ids), f.start, f.end]
    if reasons:
        parts.append(f"list_contains(?::VARCHAR[], {prefix}reason_code)")
        params.append(list(f.reasons))
    return " and ".join(parts), params


def _df(con: duckdb.DuckDBPyConnection, sql: str, params: list) -> pd.DataFrame:
    return con.execute(sql, params).df()


# ---------------------------------------------------------------- filter options


def retailers(con) -> pd.DataFrame:
    return con.execute("select retailer_id, retailer_name from marts.dim_retailer order by 1").df()


def reason_codes(con) -> list[str]:
    return [
        r[0]
        for r in con.execute(
            "select distinct reason_code from metrics.m_reason_recovery order by 1"
        ).fetchall()
    ]


def invoice_date_range(con) -> tuple[date, date]:
    lo, hi = con.execute(
        "select min(invoice_date), max(invoice_date) from marts.fct_invoices"
    ).fetchone()
    return lo, hi


# ---------------------------------------------------------------- page 1: retailer performance (VP Sales)


def sales_kpis(con, f: Filters) -> pd.Series:
    inv_where, inv_params = _where(f, "invoice_date", reasons=False)
    ded_where, ded_params = _where(f, "invoice_date", reasons=True)
    sql = f"""
        with g as (
            select sum(gross_amount) as gross_amount from metrics.m_invoice_detail where {inv_where}
        ),
        d as (
            select coalesce(sum(amount), 0) as deduction_amount,
                   coalesce(sum(recovered_amount), 0) as recovered_amount
            from metrics.m_deduction_detail where {ded_where}
        )
        select
            coalesce(g.gross_amount, 0) as gross_amount,
            d.deduction_amount,
            d.recovered_amount,
            metrics.net_revenue(coalesce(g.gross_amount, 0), d.deduction_amount, d.recovered_amount) as net_revenue,
            metrics.deduction_rate(d.deduction_amount, g.gross_amount) as deduction_rate,
            metrics.recovery_rate(d.recovered_amount, d.deduction_amount) as recovery_rate
        from g cross join d
    """
    return _df(con, sql, inv_params + ded_params).iloc[0]


def retailer_scorecard(con, f: Filters) -> pd.DataFrame:
    inv_where, inv_params = _where(f, "invoice_date", reasons=False)
    ded_where, ded_params = _where(f, "invoice_date", reasons=True)
    sql = f"""
        with inv as (
            select retailer_id,
                   sum(gross_amount) as gross_amount,
                   metrics.payment_lag(days_to_pay, payments_amount) as payment_lag_days,
                   metrics.payment_lag(days_past_due, payments_amount) as days_past_due
            from metrics.m_invoice_detail where {inv_where} group by retailer_id
        ),
        ded as (
            select retailer_id, sum(amount) as deduction_amount, sum(recovered_amount) as recovered_amount
            from metrics.m_deduction_detail where {ded_where} group by retailer_id
        )
        select
            r.retailer_id,
            r.retailer_name,
            inv.gross_amount,
            coalesce(ded.deduction_amount, 0) as deduction_amount,
            metrics.deduction_rate(coalesce(ded.deduction_amount, 0), inv.gross_amount) as deduction_rate,
            metrics.recovery_rate(coalesce(ded.recovered_amount, 0), ded.deduction_amount) as recovery_rate,
            inv.payment_lag_days,
            inv.days_past_due
        from inv
        inner join marts.dim_retailer as r on r.retailer_id = inv.retailer_id
        left join ded on ded.retailer_id = inv.retailer_id
        order by deduction_rate desc
    """
    return _df(con, sql, inv_params + ded_params)


def monthly_rate_by_retailer(con, f: Filters) -> pd.DataFrame:
    """Mature invoice months only (recent months are incomplete)."""
    inv_where, inv_params = _where(f, "invoice_month", reasons=False)
    ded_where, ded_params = _where(f, "invoice_month", reasons=True)
    sql = f"""
        with g as (
            select retailer_id, invoice_month, sum(gross_amount) as gross_amount
            from metrics.m_invoice_detail where is_mature_month and {inv_where} group by 1, 2
        ),
        d as (
            select retailer_id, invoice_month, sum(amount) as deduction_amount
            from metrics.m_deduction_detail where {ded_where} group by 1, 2
        )
        select r.retailer_name, g.invoice_month, g.gross_amount,
               metrics.deduction_rate(coalesce(d.deduction_amount, 0), g.gross_amount) as deduction_rate,
               coalesce(d.deduction_amount, 0) as deduction_amount
        from g
        inner join marts.dim_retailer as r on r.retailer_id = g.retailer_id
        left join d on d.retailer_id = g.retailer_id and d.invoice_month = g.invoice_month
        order by g.invoice_month, r.retailer_name
    """
    return _df(con, sql, inv_params + ded_params)


def trend_halves(con, f: Filters) -> pd.DataFrame:
    """Portfolio deduction rate in the first and second half of the mature months in range."""
    monthly = monthly_rate_by_retailer(con, f)
    if monthly.empty:
        return pd.DataFrame(columns=["half", "deduction_rate"])
    con.register("monthly_in", monthly)
    try:
        return con.execute(
            """
            with by_month as (
                select invoice_month, sum(gross_amount) as gross_amount, sum(deduction_amount) as deduction_amount
                from monthly_in group by invoice_month
            ),
            halves as (select *, ntile(2) over (order by invoice_month) as half from by_month)
            select half, metrics.deduction_rate(sum(deduction_amount), sum(gross_amount)) as deduction_rate
            from halves group by half order by half
            """
        ).df()
    finally:
        con.unregister("monthly_in")


# ---------------------------------------------------------------- page 2: deduction operations (AR manager)


def ops_kpis(con, f: Filters) -> pd.Series:
    where, params = _where(f, "deduction_date", reasons=True)
    sql = f"""
        select
            coalesce(sum(open_amount), 0) as open_balance,
            count(*) filter (where open_amount > 0) as open_items,
            metrics.dispute_rate(sum(amount) filter (where is_disputed), sum(amount)) as dispute_rate,
            metrics.dispute_win_rate(count(*) filter (where is_win), count(*) filter (where is_resolved)) as win_rate,
            median(days_to_resolve) as median_days_to_resolve
        from metrics.m_deduction_detail where {where}
    """
    return _df(con, sql, params).iloc[0]


def aging_by_reason(con, f: Filters) -> pd.DataFrame:
    where, params = _where(f, "deduction_date", reasons=True)
    sql = f"""
        select aging_bucket, reason_code, sum(open_amount) as open_balance
        from metrics.m_deduction_detail where open_amount > 0 and {where}
        group by aging_bucket, reason_code order by aging_bucket, reason_code
    """
    return _df(con, sql, params)


def reason_mix(con, f: Filters) -> pd.DataFrame:
    where, params = _where(f, "deduction_date", reasons=True)
    sql = f"""
        select reason_code,
               sum(amount) as deducted_amount,
               metrics.dispute_rate(sum(amount) filter (where is_disputed), sum(amount)) as dispute_rate,
               metrics.dispute_win_rate(count(*) filter (where is_win), count(*) filter (where is_resolved)) as win_rate
        from metrics.m_deduction_detail where {where}
        group by reason_code order by deducted_amount desc
    """
    return _df(con, sql, params)


def filing_cohorts(con, f: Filters) -> pd.DataFrame:
    where, params = _where(f, "deduction_date", reasons=True)
    sql = f"""
        select filing_lag_bucket,
               count(*) as disputes,
               metrics.dispute_win_rate(count(*) filter (where is_win), count(*) filter (where is_resolved)) as win_rate
        from metrics.m_deduction_detail where is_disputed and {where}
        group by filing_lag_bucket order by filing_lag_bucket
    """
    return _df(con, sql, params)


def worklist(con, f: Filters, limit: int = WORKLIST_SIZE) -> pd.DataFrame:
    """Open, never-disputed deductions ranked by expected recovery (reason win rate x recovery ratio)."""
    where, params = _where(f, "c.deduction_date", reasons=True, alias="c")
    sql = f"""
        select c.deduction_id, r.retailer_name, c.reason_code, c.deduction_date, c.age_days,
               d.aging_bucket, c.amount, c.expected_recovery
        from metrics.m_recoverable_candidates as c
        inner join metrics.m_deduction_detail as d on d.deduction_id = c.deduction_id
        inner join marts.dim_retailer as r on r.retailer_id = c.retailer_id
        where c.status = 'open' and {where}
        order by c.expected_recovery desc nulls last, c.amount desc
        limit {int(limit)}
    """
    return _df(con, sql, params)


# ---------------------------------------------------------------- page 3: cash impact (CFO)


def cash_kpis(con, f: Filters) -> pd.Series:
    where, params = _where(f, "deduction_date", reasons=True)
    sql = f"""
        select coalesce(sum(open_amount), 0) as cash_tied_up,
               coalesce(sum(amount), 0) as deducted_amount,
               coalesce(sum(recovered_amount), 0) as recovered_amount
        from metrics.m_deduction_detail where {where}
    """
    return _df(con, sql, params).iloc[0]


def recoverable_grid(con, f: Filters) -> pd.DataFrame:
    where, params = _where(f, "c.deduction_date", reasons=True, alias="c")
    sql = f"""
        select s.window_days, s.scenario,
               count(*) as candidate_deductions,
               sum(c.amount) as candidate_amount,
               sum(c.expected_recovery) * any_value(s.realization_factor) as recoverable_amount
        from metrics.m_recovery_scenarios as s
        inner join metrics.m_recoverable_candidates as c on c.age_days <= s.window_days
        where {where}
        group by s.window_days, s.scenario
        order by s.window_days, any_value(s.realization_factor)
    """
    return _df(con, sql, params)


def open_balance_by_retailer(con, f: Filters) -> pd.DataFrame:
    where, params = _where(f, "d.deduction_date", reasons=True, alias="d")
    sql = f"""
        select r.retailer_name, sum(d.open_amount) as open_balance
        from metrics.m_deduction_detail as d
        inner join marts.dim_retailer as r on r.retailer_id = d.retailer_id
        where d.open_amount > 0 and {where}
        group by r.retailer_name order by open_balance desc
    """
    return _df(con, sql, params)


def deduction_history(con, f: Filters) -> pd.DataFrame:
    """Monthly deduction dollars (deduction-date basis, all reasons, ramp-up excluded) in the date range."""
    where, params = _where(f, "deduction_month", reasons=False)
    sql = f"""
        select deduction_month as month, sum(deduction_amount) as amount
        from metrics.m_deductions_monthly where not is_burn_in_month and {where}
        group by deduction_month order by deduction_month
    """
    return _df(con, sql, params)


def forward_forecast(f: Filters, directory: Path | None = None) -> pd.DataFrame:
    """Next-3-month forecast summed over the selected retailers (all reasons)."""
    path = (directory or forecast_dir()) / "forward_forecast.csv"
    frame = pd.read_csv(path, parse_dates=["month"])
    frame = frame[frame["retailer_id"].isin(f.retailer_ids)]
    return frame.groupby("month", as_index=False)[
        ["seasonal_naive", "holt_winters", "hw_p10", "hw_p90"]
    ].sum()


def same_months_last_year(con, f: Filters, months: list[pd.Timestamp]) -> float:
    prior = [(m - pd.DateOffset(years=1)).date() for m in months]
    sql = """
        select coalesce(sum(deduction_amount), 0) from metrics.m_deductions_monthly
        where list_contains(?::DATE[], deduction_month) and list_contains(?::INTEGER[], retailer_id)
    """
    return float(con.execute(sql, [prior, list(f.retailer_ids)]).fetchone()[0])
