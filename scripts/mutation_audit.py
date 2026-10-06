"""Hand-written mutation audit: inject one bug at a time, run the test suite, record whether it was caught.

Usage: python -m scripts.mutation_audit [--only M01,M02] [--out docs/audit/mutation_results.json]
Each mutation edits ONE source file in place, runs `pytest -x`, and restores the file (even on error).
A mutation SURVIVES if the whole suite stays green. Needs a clean git tree.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MACROS = "macros/metric_definitions.sql"


@dataclass(frozen=True)
class Mutation:
    mid: str
    description: str
    path: str
    old: str
    new: str


MUTATIONS = [
    Mutation(
        "M01",
        "fan-out: fct_deductions joined to invoice lines (deduction x ~10 lines)",
        "models/marts/fct_deductions.sql",
        "left join {{ ref('stg_invoices') }} as i on i.invoice_id = d.invoice_id",
        "left join {{ ref('stg_invoices') }} as i on i.invoice_id = d.invoice_id\nleft join {{ ref('stg_invoice_lines') }} as l on l.invoice_id = d.invoice_id",
    ),
    Mutation(
        "M02",
        "fan-out: fct_invoices joined to raw deductions (gross repeated per deduction)",
        "models/marts/fct_invoices.sql",
        "left join {{ ref('int_invoice_deductions') }} as d on d.invoice_id = i.invoice_id",
        "left join {{ ref('int_invoice_deductions') }} as d on d.invoice_id = i.invoice_id\nleft join {{ ref('stg_deductions') }} as dd on dd.invoice_id = i.invoice_id",
    ),
    Mutation(
        "M03",
        "LEFT JOIN -> INNER JOIN: fct_invoices drops unpaid invoices",
        "models/marts/fct_invoices.sql",
        "left join {{ ref('int_invoice_payments') }} as p",
        "inner join {{ ref('int_invoice_payments') }} as p",
    ),
    Mutation(
        "M04",
        "LEFT JOIN -> INNER JOIN: fct_deductions drops orphaned deductions",
        "models/marts/fct_deductions.sql",
        "left join {{ ref('stg_invoices') }} as i on",
        "inner join {{ ref('stg_invoices') }} as i on",
    ),
    Mutation(
        "M05",
        "LEFT JOIN -> INNER JOIN: fct_disputes drops disputes without a deduction row",
        "models/marts/fct_disputes.sql",
        "left join {{ ref('fct_deductions') }} as d on",
        "inner join {{ ref('fct_deductions') }} as d on",
    ),
    Mutation(
        "M06",
        "aging boundary 30/31 (<= 30 -> < 30)",
        MACROS,
        "when age_days <= 30 then",
        "when age_days < 30 then",
    ),
    Mutation(
        "M07",
        "aging boundary 60/61 (<= 60 -> < 60)",
        MACROS,
        "when age_days <= 60 then",
        "when age_days < 60 then",
    ),
    Mutation(
        "M08",
        "aging boundary 90/91 (<= 90 -> < 90)",
        MACROS,
        "when age_days <= 90 then",
        "when age_days < 90 then",
    ),
    Mutation(
        "M09",
        "deduction rate: wrong denominator (gross + deductions)",
        MACROS,
        "deduction_amount / nullif(gross_amount, 0)",
        "deduction_amount / nullif(gross_amount + deduction_amount, 0)",
    ),
    Mutation(
        "M10",
        "recovery rate: wrong denominator (recovered + deducted)",
        MACROS,
        "recovered_amount / nullif(deduction_amount, 0)",
        "recovered_amount / nullif(recovered_amount + deduction_amount, 0)",
    ),
    Mutation(
        "M11",
        "win rate: wrong denominator (resolved + wins)",
        MACROS,
        "win_count / nullif(resolved_count, 0)",
        "win_count / nullif(resolved_count + win_count, 0)",
    ),
    Mutation(
        "M12",
        "unattributed SKU bucket dropped from dim_sku (key -1 -> -2)",
        "models/marts/dim_sku.sql",
        "-1 as sku_key",
        "-2 as sku_key",
    ),
    Mutation(
        "M13",
        "NULL sku_id no longer mapped to the bucket in fct_deductions",
        "models/marts/fct_deductions.sql",
        "coalesce(d.sku_id, -1) as sku_key",
        "d.sku_id as sku_key",
    ),
    Mutation(
        "M14",
        "unresolved (pending) disputes counted as resolved/lost",
        MACROS,
        "dispute_outcome in ('won', 'partial', 'lost');",
        "dispute_outcome in ('won', 'partial', 'lost', 'pending');",
    ),
    Mutation(
        "M15",
        "today's date instead of the fixed as-of date in ageing",
        "models/metrics/m_deduction_detail.sql",
        "cast('{{ var(\"as_of_date\") }}' as date) as as_of_date,",
        "current_date as as_of_date,",
    ),
    Mutation(
        "M16",
        "z-score baseline includes the current month (11 preceding .. current row)",
        "sql/analysis/07_anomaly_zscores.sql",
        "rows between 12 preceding and 1 preceding",
        "rows between 11 preceding and current row",
    ),
    Mutation(
        "M17",
        "z-score sign flipped",
        "sql/analysis/07_anomaly_zscores.sql",
        "(deduction_amount - baseline_mean) / baseline_stddev",
        "(baseline_mean - deduction_amount) / baseline_stddev",
    ),
    Mutation(
        "M18",
        "forecast leakage: training fold includes the origin month",
        "forecast/model.py",
        "train, test = monthly.iloc[:origin], monthly.iloc[origin : origin + horizon]",
        "train, test = monthly.iloc[: origin + 1], monthly.iloc[origin : origin + horizon]",
    ),
    Mutation(
        "M19",
        "dashboard: reason filter silently ignored in every page query",
        "dashboard/data.py",
        "    if reasons:\n",
        "    if False:\n",
    ),
    Mutation(
        "M20",
        "duplicate payments double-count (payments unioned with themselves)",
        "models/intermediate/int_invoice_payments.sql",
        "from {{ ref('stg_payments') }}",
        "from (select * from {{ ref('stg_payments') }} union all select * from {{ ref('stg_payments') }})",
    ),
    Mutation(
        "M21",
        "metric macro changed in one place: partial wins no longer wins",
        MACROS,
        "dispute_outcome in ('won', 'partial');\ncreate or replace macro metrics.is_resolved",
        "dispute_outcome in ('won');\ncreate or replace macro metrics.is_resolved",
    ),
    Mutation(
        "M22",
        "analysis 05 re-derives a bucket label instead of using the metrics layer",
        "sql/analysis/05_filing_lag_cohorts.sql",
        "select\n    filing_lag_bucket,\n    disputes,",
        "select\n    case when filing_lag_bucket = '0-14' then 'fast' else filing_lag_bucket end as filing_lag_bucket,\n    disputes,",
    ),
    Mutation(
        "M23",
        "net revenue formula subtracts recoveries",
        MACROS,
        "gross_amount - deduction_amount + recovered_amount",
        "gross_amount - deduction_amount - recovered_amount",
    ),
    Mutation(
        "M24",
        "open balance ignores pending-dispute deductions",
        MACROS,
        "deduction_status in ('open', 'disputed') then deduction_amount - recovered_amount",
        "deduction_status in ('open') then deduction_amount - recovered_amount",
    ),
    Mutation(
        "M25",
        "recoverable candidates include accepted (verified-valid) deductions",
        "models/metrics/m_recoverable_candidates.sql",
        "d.status in ('open', 'written_off')",
        "d.status in ('open', 'written_off', 'accepted')",
    ),
    Mutation(
        "M26",
        "seasonal naive off by one month",
        "forecast/model.py",
        "train[len(train) - SEASON + np.arange(horizon) % SEASON]",
        "train[len(train) - SEASON + 1 + np.arange(horizon) % SEASON]",
    ),
    Mutation(
        "M27",
        "generator: Retailer A fine multiplier 3 -> 1 (pattern 1 removed)",
        "data_gen/generate.py",
        "np.log(3.0)",
        "np.log(1.0)",
    ),
    Mutation(
        "M28",
        "validator: duplicate-payment rule threshold off (> 1 -> > 2)",
        "warehouse/validate.sql",
        "group by invoice_id, paid_date, paid_amount having count(*) > 1",
        "group by invoice_id, paid_date, paid_amount having count(*) > 2",
    ),
    Mutation(
        "M29",
        "days to resolve: arguments reversed (negative days)",
        MACROS,
        "date_diff('day', filed_date, resolved_date)",
        "date_diff('day', resolved_date, filed_date)",
    ),
    Mutation(
        "M30",
        "payment lag no longer weighted by amount paid",
        MACROS,
        "sum(days_to_pay * paid_amount) / nullif(sum(paid_amount), 0)",
        "avg(days_to_pay)",
    ),
    Mutation("M31", "recovery cap removed: re-filed disputes can recover more than the deduction", "models/intermediate/int_deduction_disputes.sql",
             "least(coalesce(x.recovered_amount, 0), greatest(d.amount, 0)) as recovered_amount", "coalesce(x.recovered_amount, 0) as recovered_amount"),
    Mutation("M32", "analysis 02: calendar scaffold join made inner (gap months vanish, LAG skips them)", "sql/analysis/02_deduction_rate_trend.sql",
             "left join metrics.m_retailer_month as m", "inner join metrics.m_retailer_month as m"),
    Mutation("M33", "make build no longer runs the validation gate", "Makefile", "build: validate\n", "build: data\n"),
    Mutation("M34", "validator: duplicate-deduction rule threshold off (> 1 -> > 2)", "warehouse/validate.sql",
             "group by invoice_id, reason_code, sku_id, deduction_date, amount having count(*) > 1", "group by invoice_id, reason_code, sku_id, deduction_date, amount having count(*) > 2"),
    Mutation("M35", "dashboard: retailer filter ignored (always retailer 1)", "dashboard/data.py",
             "list_contains(?::INTEGER[], {prefix}retailer_id)", "list_contains(?::INTEGER[], 1 + 0 * {prefix}retailer_id)"),
    Mutation("M36", "forecast: sMAPE missing its factor of 2", "forecast/model.py",
             "return float(np.mean(2 * np.abs(actual - forecast) / (np.abs(actual) + np.abs(forecast))))", "return float(np.mean(np.abs(actual - forecast) / (np.abs(actual) + np.abs(forecast))))"),
    Mutation("M37", "forecast: MASE scale ignores the seasonal lag (lag 1 instead of 12)", "forecast/model.py",
             "return float(np.mean(np.abs(history[SEASON:] - history[:-SEASON])))", "return float(np.mean(np.abs(history[1:] - history[:-1])))"),
    Mutation("M38", "analysis 06: under-invested margin removed (0.10 -> 0.0), the null-data false-positive fix undone", "sql/analysis/06_recovery_underinvestment.sql",
             "win_rate >= all_reason_win_rate + 0.10", "win_rate >= all_reason_win_rate + 0.0"),
    Mutation("M39", "analysis 07: z threshold back to 3 (null-data false positives return)", "sql/analysis/07_anomaly_zscores.sql",
             "where abs(z_score) >= 4.5", "where abs(z_score) >= 3"),
    Mutation("M40", "recovery scenarios: base realization factor 0.75 -> 0.70", "models/metrics/m_recovery_scenarios.sql", "('base', 0.75)", "('base', 0.70)"),
    Mutation("M41", "generator: Retailer B lag drift removed (pattern 4)", "data_gen/generate.py", "B_LAG_DRIFT_TOTAL = 12.0", "B_LAG_DRIFT_TOTAL = 0.0"),
    Mutation("M42", "atomic load replaced by an in-place rebuild of the final file", "data_gen/load.py",
             'building = path.with_name(f"{path.stem}.building{path.suffix}")', "building = path"),
]  # fmt: skip

# Cheap, high-signal files first, slow sweep/pipeline files last: a killed run stops at its first failure.
TEST_ORDER = [
    "tests/test_analysis.py", "tests/test_metrics.py", "tests/test_models.py", "tests/test_messy_conditions.py",
    "tests/test_hygiene.py", "tests/test_validator.py", "tests/test_forecast.py", "tests/test_dashboard.py",
    "tests/test_findings.py", "tests/test_repo_hygiene.py", "tests/test_toolchain.py", "tests/test_null_pipeline.py",
    "tests/test_pipeline_robustness.py", "tests/test_dashboard_robustness.py", "tests/test_generator.py",
    "tests/test_audit_modes.py",
]  # fmt: skip


def run_one(m: Mutation) -> dict:
    path = ROOT / m.path
    original = path.read_text()
    if original.count(m.old) != 1:
        return {"id": m.mid, "description": m.description, "status": "ERROR",
                "caught_by": f"pattern found {original.count(m.old)} times in {m.path}", "seconds": 0.0}  # fmt: skip
    path.write_text(original.replace(m.old, m.new))
    start = time.time()
    try:
        proc = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-rfE", "-p", "no:cacheprovider", *TEST_ORDER],
                              cwd=ROOT, capture_output=True, text=True, check=False)  # fmt: skip
    finally:
        path.write_text(original)
    failed = re.findall(r"^(?:FAILED|ERROR) (\S+)", proc.stdout, re.M)
    status = "SURVIVED" if proc.returncode == 0 else "KILLED"
    return {"id": m.mid, "description": m.description, "status": status,
            "caught_by": failed[0] if failed else ("" if status == "SURVIVED" else proc.stdout[-300:]),
            "seconds": round(time.time() - start, 1)}  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", default="")
    parser.add_argument(
        "--out", type=Path, default=ROOT / "docs" / "audit" / "mutation_results.json"
    )
    args = parser.parse_args()
    wanted = set(filter(None, args.only.split(",")))
    results = []
    for m in MUTATIONS:
        if wanted and m.mid not in wanted:
            continue
        result = run_one(m)
        results.append(result)
        print(
            f"{result['id']} {result['status']:<9} {result['caught_by'][:110]}  ({result['seconds']}s)",
            flush=True,
        )
    killed = sum(r["status"] == "KILLED" for r in results)
    print(f"killed {killed}/{len(results)} = {killed / len(results):.0%}")
    args.out.write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
