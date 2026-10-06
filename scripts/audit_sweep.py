"""Audit: run the generator + dbt + the analysis SQL on many seeds, planted or NULL, and score each detector.

Usage: python -m scripts.audit_sweep --mode planted|null [--seeds 1-20] [--bias 1.0] --out docs/audit/<name>.json
For every run it records the effect size each analysis reports, whether each planted pattern would be called
"detected" (thresholds below), and false-positive counts. A NULL run has no planted pattern, so everything flagged
is a false positive.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from data_gen.config import PROBLEM_SKUS, Config
from data_gen.load import build_warehouse

ROOT = Path(__file__).resolve().parents[1]
ANALYSIS = ROOT / "sql" / "analysis"

# Thresholds a reader would apply to call a pattern "found" (same ranges the generator tests use).
FINE_RATIO_MIN = 2.0
FINE_TOP2_ATTRIBUTED_MIN = 0.50
SPIKE_MIN = 1.5
PROMO_DISPUTE_MAX = 0.15
LAG_CHANGE_MIN = 5.0
SHORTAGE_WIN_MIN = 0.65
PLANTED_ANOMALY_MONTHS = {"2025-04", "2025-05"}


def analysis(con, prefix: str) -> pd.DataFrame:
    return con.execute(next(ANALYSIS.glob(f"{prefix}_*.sql")).read_text()).df()


def run_dbt(path: Path) -> None:
    env = {**os.environ, "WAREHOUSE_PATH": str(path), "DBT_PROFILES_DIR": str(ROOT)}
    result = subprocess.run(
        [sys.executable, "-m", "dbt.cli.main", "run", "--target-path", str(path.parent / "target"), "--log-path", str(path.parent / "logs")],
        cwd=ROOT, env=env, capture_output=True, text=True, check=False,
    )  # fmt: skip
    if result.returncode != 0:
        raise RuntimeError(result.stdout[-2000:])


def retailer_fine_ratios(con) -> pd.Series:
    rates = (
        con.execute(
            """
        select g.retailer_id, metrics.deduction_rate(coalesce(f.fines, 0), g.gross) as rate
        from (select retailer_id, sum(gross_amount) as gross from metrics.m_invoice_detail group by 1) g
        left join (select retailer_id, sum(amount) as fines from metrics.m_deduction_detail
                   where reason_code = 'compliance_fine' group by 1) f using (retailer_id)
        """
        )
        .df()
        .set_index("retailer_id")["rate"]
        .astype(float)
    )
    return pd.Series({r: rates[r] / rates.drop(r).median() for r in rates.index})


def detect(con) -> dict:
    out: dict = {}
    # Pattern 1: one retailer's compliance fines far above peers and concentrated in two SKUs.
    a03 = analysis(con, "03")
    ratios = retailer_fine_ratios(con)
    top = ratios.idxmax()
    top2 = a03[a03["sku_rank"] <= 2]
    out["p1_top_retailer"] = int(top)
    out["p1_ratio"] = float(ratios.max())
    out["p1_top2_share_attributed"] = float(top2["share_of_attributed_fines"].sum())
    out["p1_top2_is_planted"] = set(int(k) for k in top2["sku_key"]) == set(PROBLEM_SKUS)
    out["p1_detected"] = bool(
        top == 1 and ratios.max() >= FINE_RATIO_MIN and out["p1_top2_is_planted"]
    )
    out["p1_flagged_any"] = bool(
        ratios.max() >= FINE_RATIO_MIN
        and out["p1_top2_share_attributed"] >= FINE_TOP2_ATTRIBUTED_MIN
    )
    out["p1_false_positives"] = int((ratios.drop(1) >= FINE_RATIO_MIN).sum())
    # Pattern 2: promo deductions spike in Jan-Feb and are rarely disputed.
    a09 = analysis(con, "09")
    out["p2_median_spike"] = float(a09["spike_index"].median())
    out["p2_retailer_years_spiking"] = int((a09["spike_index"] >= SPIKE_MIN).sum())
    out["p2_max_dispute_rate"] = float(a09["promo_dispute_rate"].max())
    out["p2_detected"] = bool(
        out["p2_median_spike"] >= SPIKE_MIN and out["p2_max_dispute_rate"] <= PROMO_DISPUTE_MAX
    )
    # Pattern 3: shortage wins often but is disputed rarely.
    a06 = analysis(con, "06").set_index("reason_code")
    flagged = set(a06.index[a06["under_invested"]])
    out["p3_shortage_win_rate"] = float(a06.loc["shortage", "win_rate"])
    out["p3_shortage_dispute_rate"] = float(a06.loc["shortage", "dispute_rate"])
    out["p3_flagged"] = sorted(flagged)
    out["p3_detected"] = "shortage" in flagged
    out["p3_false_positives"] = len(flagged - {"shortage"})
    # Pattern 4: one retailer's payment lag drifts up.
    a08 = analysis(con, "08")
    latest = (
        a08[a08["invoice_month"] == a08["invoice_month"].max()]
        .set_index("retailer_id")["change_vs_6m_ago"]
        .astype(float)
    )
    out["p4_top_retailer"] = int(latest.idxmax())
    out["p4_change_days"] = float(latest.max())
    out["p4_detected"] = bool(latest.idxmax() == 2 and latest.max() >= LAG_CHANGE_MIN)
    out["p4_false_positives"] = int((latest.drop(2) >= LAG_CHANGE_MIN).sum())
    # Pattern 5: seasonality + growth.
    monthly = con.execute(
        "select invoice_month, sum(gross_amount) as g from metrics.m_invoice_detail group by 1 order by 1"
    ).df()
    monthly["g"] = monthly["g"].astype(float)
    yearly = monthly.groupby(pd.to_datetime(monthly["invoice_month"]).dt.year)["g"].sum()
    q4 = pd.to_datetime(monthly["invoice_month"]).dt.month >= 10
    out["p5_growth"] = float(yearly.pct_change().dropna().mean())
    out["p5_q4_ratio"] = float(monthly.loc[q4, "g"].mean() / monthly.loc[~q4, "g"].mean())
    out["p5_detected"] = bool(0.04 <= out["p5_growth"] <= 0.12 and 1.1 <= out["p5_q4_ratio"] <= 1.5)
    # Pattern 7: one-off shortage spike (retailer 5, invoices in 2025-04).
    a07 = analysis(con, "07")
    hit = a07[(a07["retailer_id"] == 5) & (a07["reason_code"] == "shortage")]
    months = {m.strftime("%Y-%m") for m in hit["deduction_month"]}
    out["p7_anomalies_flagged"] = int(len(a07))
    out["p7_detected"] = bool(months & PLANTED_ANOMALY_MONTHS)
    out["p7_false_positives"] = int(
        len(a07)
        - len(
            hit[hit["deduction_month"].map(lambda m: m.strftime("%Y-%m") in PLANTED_ANOMALY_MONTHS)]
        )
    )
    # Filing-lag cohort effect and the recoverable-dollar figure.
    a05 = analysis(con, "05").dropna(subset=["win_rate"])
    out["filing_lag_win_gap"] = float(a05["win_rate"].iloc[0] - a05["win_rate"].iloc[-1])
    a10 = analysis(con, "10").set_index(["window_days", "scenario"])["recoverable_amount"]
    out["recoverable_180_base"] = float(a10[(180, "base")])
    out["recoverable_180_history"] = float(a10[(180, "high")])
    return out


def parse_seeds(text: str) -> list[int]:
    lo, _, hi = text.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["planted", "null"], default="planted")
    parser.add_argument("--seeds", default="1-20")
    parser.add_argument("--bias", type=float, default=None)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    results = []
    for seed in parse_seeds(args.seeds):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "warehouse.duckdb"
            build_warehouse(
                path, Config(seed=seed, planted=args.mode == "planted", dispute_bias=args.bias)
            )
            run_dbt(path)
            con = duckdb.connect(str(path), read_only=True)
            row = {"seed": seed, "mode": args.mode, **detect(con)}
            con.close()
        results.append(row)
        print(f"seed {seed}: p1={row['p1_ratio']:.2f}x p2={row['p2_median_spike']:.2f}x p3_flag={row['p3_flagged']} "
              f"p4={row['p4_change_days']:.1f}d anomalies={row['p7_anomalies_flagged']}", flush=True)  # fmt: skip
    args.out.write_text(
        json.dumps(results, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))
        + "\n"
    )
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
