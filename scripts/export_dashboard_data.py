"""Export small, additive data cubes for the static (GitHub Pages) dashboard (SYNTHETIC data).

The browser filters and sums these cubes; ratios are computed there from the additive columns. Everything comes from
marts/metrics views (and the forecast CSVs); nothing is read from raw tables. Months, not days, are the finest date grain.
Usage: python -m scripts.export_dashboard_data [--out site/dashboard/data.json]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import pandas as pd

from data_gen.config import Config
from data_gen.load import DEFAULT_PATH

ROOT = Path(__file__).resolve().parents[1]
FORECAST = ROOT / "forecast" / "results"
WORKLIST_ROWS = 1000


def cube(con: duckdb.DuckDBPyConnection, sql: str) -> dict:
    """Columnar JSON: {cols: [...], rows: [[...], ...]}; floats rounded to cents, dates to YYYY-MM."""
    df = con.execute(sql).df()
    for col in df.columns:
        if str(df[col].dtype).startswith("datetime") or (
            len(df) and hasattr(df[col].iloc[0], "strftime")
        ):
            df[col] = pd.to_datetime(df[col]).dt.strftime("%Y-%m")
        elif df[col].dtype.kind == "f":
            df[col] = df[col].round(2)
    return {"cols": list(df.columns), "rows": json.loads(df.to_json(orient="values"))}


def export(warehouse: Path, forecast_dir: Path = FORECAST) -> dict:
    con = duckdb.connect(str(warehouse), read_only=True)
    windows = [
        r[0]
        for r in con.execute(
            "select distinct window_days from metrics.m_recovery_scenarios order by 1"
        ).fetchall()
    ]
    band = "case " + " ".join(f"when age_days <= {w} then {w}" for w in windows) + " end"
    data = {
        "meta": {
            "as_of": Config().end_date.isoformat(),
            "windows": windows,
            "worklist_rows": WORKLIST_ROWS,
        },
        "retailers": cube(
            con,
            "select retailer_id as id, retailer_name as name from marts.dim_retailer order by 1",
        ),
        "scenarios": cube(
            con,
            "select distinct scenario, realization_factor as factor from metrics.m_recovery_scenarios order by 2",
        ),
        "deductions": cube(
            con,
            """
            select retailer_id as r, reason_code as c, deduction_month as m, count(*) as n, sum(amount) as amt,
                   coalesce(sum(amount) filter (where is_disputed), 0) as disp, sum(recovered_amount) as rec,
                   count(*) filter (where is_resolved) as resolved, count(*) filter (where is_win) as wins,
                   coalesce(sum(days_to_resolve) filter (where is_resolved), 0) as days_sum,
                   count(days_to_resolve) filter (where is_resolved) as days_n,
                   sum(open_amount) as open_amt, count(*) filter (where open_amount > 0) as open_n,
                   bool_and(is_burn_in_month) as burn
            from metrics.m_deduction_detail group by 1, 2, 3 order by 1, 2, 3""",
        ),
        "open": cube(
            con,
            """
            select retailer_id as r, reason_code as c, deduction_month as m, aging_bucket as b, sum(open_amount) as amt
            from metrics.m_deduction_detail where open_amount > 0 group by 1, 2, 3, 4 order by 1, 2, 3, 4""",
        ),
        "lag": cube(
            con,
            """
            select retailer_id as r, reason_code as c, deduction_month as m, filing_lag_bucket as b,
                   count(*) filter (where is_resolved) as resolved, count(*) filter (where is_win) as wins
            from metrics.m_deduction_detail where is_disputed group by 1, 2, 3, 4 order by 1, 2, 3, 4""",
        ),
        "gross": cube(
            con,
            """
            select retailer_id as r, invoice_month as m, sum(gross_amount) as gross,
                   coalesce(sum(days_past_due * payments_amount), 0) as late_sum,
                   coalesce(sum(payments_amount) filter (where days_past_due is not null), 0) as late_w,
                   bool_and(is_mature_month) as mature
            from metrics.m_invoice_detail group by 1, 2 order by 1, 2""",
        ),
        "cohort": cube(
            con,
            """
            select retailer_id as r, reason_code as c, invoice_month as m, sum(amount) as amt, sum(recovered_amount) as rec
            from metrics.m_deduction_detail group by 1, 2, 3 order by 1, 2, 3""",
        ),
        "candidates": cube(
            con,
            f"""
            select c.retailer_id as r, c.reason_code as c, date_trunc('month', c.deduction_date)::date as m,
                   {band} as w, sum(c.amount) as amt, coalesce(sum(c.expected_recovery), 0) as exp
            from metrics.m_recoverable_candidates c where age_days <= {max(windows)} group by 1, 2, 3, 4 order by 1, 2, 3, 4""",
        ),
        "worklist": cube(
            con,
            f"""
            select c.deduction_id as id, c.retailer_id as r, c.reason_code as c, c.deduction_date as d, c.age_days as age,
                   m.aging_bucket as b, c.amount as amt, c.expected_recovery as exp
            from metrics.m_recoverable_candidates c join metrics.m_deduction_detail m using (deduction_id)
            where c.status = 'open' order by c.expected_recovery desc nulls last, c.amount desc limit {WORKLIST_ROWS}""",
        ),
    }
    con.close()
    forward = pd.read_csv(forecast_dir / "forward_forecast.csv", parse_dates=["month"])
    forward["month"] = forward["month"].dt.strftime("%Y-%m")
    data["forecast"] = {"cols": ["r", "m", "naive", "hw", "p10", "p90"],
                        "rows": json.loads(forward[["retailer_id", "month", "seasonal_naive", "holt_winters", "hw_p10", "hw_p90"]].round(2).to_json(orient="values"))}  # fmt: skip
    return data


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "site" / "dashboard" / "data.json")
    args = parser.parse_args()
    data = export(DEFAULT_PATH)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(data, separators=(",", ":")))
    sizes = {k: len(v["rows"]) for k, v in data.items() if isinstance(v, dict) and "rows" in v}
    print(
        f"wrote {args.out.relative_to(ROOT)} ({args.out.stat().st_size / 1e6:.2f} MB) rows: {sizes}"
    )


if __name__ == "__main__":
    main()
