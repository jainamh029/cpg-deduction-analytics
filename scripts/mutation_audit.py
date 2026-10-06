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
        "having count(*) > 1);",
        "having count(*) > 2);",
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
]


def run_one(m: Mutation) -> dict:
    path = ROOT / m.path
    original = path.read_text()
    if original.count(m.old) != 1:
        return {"id": m.mid, "description": m.description, "status": "ERROR",
                "caught_by": f"pattern found {original.count(m.old)} times in {m.path}", "seconds": 0.0}  # fmt: skip
    path.write_text(original.replace(m.old, m.new))
    start = time.time()
    try:
        proc = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "-rfE", "-p", "no:cacheprovider"],
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
