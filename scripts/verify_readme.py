"""Independent check of README numbers (SYNTHETIC data).

Recomputes numbers with SQL/pandas written against the RAW tables (not marts, not metrics macros, not the
analysis files) and asserts they match docs/findings.json within rounding AND appear, formatted, in README.md.

Usage: python -m scripts.verify_readme [--warehouse PATH]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from data_gen.load import DEFAULT_PATH
from scripts.render_readme import FILTERS, FINDINGS, README, lookup

AS_OF = "date '2025-12-31'"
FORECAST = Path(__file__).resolve().parents[1] / "forecast" / "results"


def q(con, sql: str) -> float:
    return float(con.execute(sql).fetchone()[0])


def independent_values(
    con: duckdb.DuckDBPyConnection, forecast_dir: Path = FORECAST
) -> dict[str, tuple[float, str]]:
    """{findings path: (independently computed value, README filter)}."""
    gross = q(con, "select sum(gross_amount) from raw.invoices")
    ded = q(con, "select sum(amount) from raw.deductions")
    rec = q(con, "select sum(recovered_amount) from raw.disputes")
    sk = "d.reason_code = 'shortage'"
    short_dispute = q(
        con,
        f"select sum(d.amount) filter (where x.dispute_id is not null) / sum(d.amount) from raw.deductions d left join raw.disputes x using (deduction_id) where {sk}",
    )
    short_win = q(
        con,
        f"select count(*) filter (where x.outcome in ('won','partial')) * 1.0 / count(*) filter (where x.outcome <> 'pending') from raw.deductions d join raw.disputes x using (deduction_id) where {sk}",
    )

    rates = (
        con.execute(
            "select i.retailer_id, coalesce(max(f.fines), 0) / sum(i.gross_amount) as rate from raw.invoices i left join "
            "(select retailer_id, sum(amount) as fines from raw.deductions where reason_code = 'compliance_fine' group by 1) f using (retailer_id) group by 1"
        )
        .df()
        .set_index("retailer_id")["rate"]
        .astype(float)
    )
    top = rates.idxmax()
    ratio = rates[top] / rates.drop(top).median()
    fines = con.execute(
        "select sku_id, sum(amount) as amt from raw.deductions where reason_code = 'compliance_fine' and retailer_id = ? group by 1",
        [int(top)],
    ).df()
    attributed = fines.dropna(subset=["sku_id"])
    top2 = attributed.nlargest(2, "amt")["amt"].astype(float).sum()

    promo = con.execute(
        "select retailer_id, year(deduction_date) as y, month(deduction_date) as m, sum(amount) as amt from raw.deductions where reason_code = 'promo' and deduction_date >= date '2023-04-01' group by 1, 2, 3"
    ).df()
    promo["amt"] = promo["amt"].astype(float)
    spikes = []
    for (_, _year), g in promo[promo["y"].isin([2024, 2025])].groupby(["retailer_id", "y"]):
        spikes.append(g[g["m"] <= 2]["amt"].mean() / g[(g["m"] >= 3) & (g["m"] <= 9)]["amt"].mean())

    stats = (
        con.execute(
            "select d.reason_code, count(*) filter (where x.outcome in ('won','partial')) * 1.0 / count(*) filter (where x.outcome in ('won','partial','lost')) as w, sum(x.recovered_amount) filter (where x.outcome in ('won','partial')) / sum(d.amount) filter (where x.outcome in ('won','partial')) as r from raw.deductions d join raw.disputes x using (deduction_id) group by 1"
        )
        .df()
        .set_index("reason_code")
    )
    cands = con.execute(
        f"select reason_code, amount from raw.deductions where deduction_id not in (select deduction_id from raw.disputes) and status in ('open','written_off') and {AS_OF} - deduction_date <= 180"
    ).df()
    base180 = 0.75 * sum(
        float(a) * stats.loc[r, "w"] * stats.loc[r, "r"]
        for r, a in zip(cands["reason_code"], cands["amount"], strict=True)
    )

    null_count = q(
        con, "select avg(case when sku_id is null then 1 else 0 end) from raw.deductions"
    )
    null_amount = q(
        con, "select sum(amount) filter (where sku_id is null) / sum(amount) from raw.deductions"
    )

    def lag(month: str) -> float:
        return q(
            con,
            "select sum((p.paid_date - i.invoice_date) * p.paid_amount) / sum(p.paid_amount) "
            "from raw.invoices i join raw.payments p using (invoice_id) "
            f"where i.retailer_id = 2 and date_trunc('month', i.invoice_date) = date '{month}'",
        )

    fc = pd.read_csv(forecast_dir / "backtest_forecasts.csv").dropna()

    def pooled(col: str) -> float:
        return float(np.mean(np.abs(fc["actual"] - fc[col]) / fc["actual"]))

    return {
        "headline.gross": (gross, "money"),
        "headline.deductions": (ded, "money"),
        "headline.deduction_rate": (ded / gross, "pct1"),
        "headline.recovered": (rec, "money"),
        "headline.net_leakage": (ded - rec, "money"),
        "headline.recoverable_180_base": (base180, "money"),
        "finding1.shortage_dispute_rate": (short_dispute, "pct0"),
        "finding1.shortage_win_rate": (short_win, "pct0"),
        "finding2.ratio_to_peers": (ratio, "x1"),
        "finding2.top2_share_of_attributed": (
            top2 / float(attributed["amt"].astype(float).sum()),
            "pct0",
        ),
        "finding2.top2_share_of_all": (top2 / float(fines["amt"].astype(float).sum()), "pct0"),
        "finding3.median_spike_index": (float(np.median(spikes)), "x1"),
        "also.lag_change_6m": (lag("2025-08-01") - lag("2025-02-01"), "num1"),
        "data_quality.sku_null_rate_count": (null_count, "pct1"),
        "data_quality.sku_null_rate_amount": (null_amount, "pct1"),
        "forecast.pooled_mape_hw": (pooled("holt_winters"), "pct1"),
        "forecast.pooled_mape_naive": (pooled("seasonal_naive"), "pct1"),
    }


def verify(
    warehouse: Path,
    findings_path: Path = FINDINGS,
    readme_path: Path = README,
    forecast_dir: Path = FORECAST,
) -> list[str]:
    """Return a list of failure messages (empty = all checks passed); prints each check."""
    findings = json.loads(findings_path.read_text())
    readme = readme_path.read_text()
    con = duckdb.connect(str(warehouse), read_only=True)
    values = independent_values(con, forecast_dir)
    con.close()
    failures = []
    for path, (independent, fmt) in values.items():
        stored = float(lookup(findings, path))
        text = FILTERS[fmt](independent)
        close = abs(stored - independent) <= 1e-6 * max(1.0, abs(independent))
        in_readme = text in readme
        status = "ok" if close and in_readme else "FAIL"
        print(
            f"{status:<5}{path:<40} independent={independent:<16.6g} findings={stored:<16.6g} README shows {text!r}: {in_readme}"
        )
        if not (close and in_readme):
            failures.append(path)
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--warehouse", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    failures = verify(args.warehouse)
    print(f"{len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
