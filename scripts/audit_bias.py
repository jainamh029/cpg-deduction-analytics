"""Audit: how wrong is the recoverable-dollar estimate when AR teams dispute the winnable deductions first?

For each bias level the generator gives every deduction a hidden winnability; disputes pick winnable ones more often
(selection strength `dispute_bias`), while the population-average win rate is unchanged. The pipeline estimates
recoverable dollars from HISTORICAL win rates on disputed deductions (what a real analyst would do). The generator
also knows the TRUE win probability of every never-disputed deduction, so we can compare estimate and truth.

Usage: python -m scripts.audit_bias [--seeds 1-3] --out docs/audit/bias_results.json
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import duckdb
import pandas as pd

from data_gen.config import Config
from data_gen.generate import generate_with_truth
from data_gen.load import build_warehouse
from scripts.audit_sweep import analysis, parse_seeds, run_dbt

WIN_RECOVERY_RATIO = (
    0.7 * 1.0 + 0.3 * 0.55
)  # generator: 70% of wins recover in full, 30% recover U(0.3, 0.8)
WINDOW_DAYS = 180
BIAS_LEVELS = [None, 0.0, 0.5, 1.0, 1.5]


def one_run(seed: int, bias: float | None) -> dict:
    cfg = Config(seed=seed, dispute_bias=bias)
    _, truth = generate_with_truth(cfg)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "warehouse.duckdb"
        build_warehouse(path, cfg)
        run_dbt(path)
        con = duckdb.connect(str(path), read_only=True)
        grid = analysis(con, "10").set_index(["window_days", "scenario"])["recoverable_amount"]
        history_estimate = float(
            grid[(WINDOW_DAYS, "high")]
        )  # realization factor 1.0: pure historical rates
        cands = (
            con.execute(
                "select deduction_id, reason_code, amount from metrics.m_recoverable_candidates where age_days <= ?",
                [WINDOW_DAYS],
            )
            .df()
            .merge(truth, on="deduction_id")
        )
        cands["amount"] = cands["amount"].astype(float)
        cands["oracle"] = cands["amount"] * cands["p_win_true"] * WIN_RECOVERY_RATIO
        short = analysis(con, "06").set_index("reason_code").loc["shortage"]
        short_c = (
            con.execute(
                "select deduction_id, amount, expected_recovery from metrics.m_recoverable_candidates where reason_code = 'shortage'"
            )
            .df()
            .merge(truth, on="deduction_id")
        )
        short_c["amount"] = short_c["amount"].astype(float)
        short_estimate = float(short_c["expected_recovery"].astype(float).sum())
        short_oracle = float((short_c["amount"] * short_c["p_win_true"] * WIN_RECOVERY_RATIO).sum())
        con.close()
    return {
        "seed": seed,
        "bias": bias,
        "history_estimate_180": history_estimate,
        "oracle_180": float(cands["oracle"].sum()),
        "implied_realization_factor": float(cands["oracle"].sum() / history_estimate),
        "shortage_observed_win_rate": float(short["win_rate"]),
        "shortage_true_win_prob_undisputed": float(short_c["p_win_true"].mean()),
        "shortage_potential_estimate": short_estimate,
        "shortage_potential_oracle": short_oracle,
        "shortage_flagged_under_invested": bool(short["under_invested"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", default="1-3")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    rows = []
    for bias in BIAS_LEVELS:
        for seed in parse_seeds(args.seeds):
            row = one_run(seed, bias)
            rows.append(row)
            print(f"bias={bias} seed={seed}: estimate ${row['history_estimate_180']:,.0f} oracle ${row['oracle_180']:,.0f} "
                  f"factor {row['implied_realization_factor']:.2f} | shortage win observed {row['shortage_observed_win_rate']:.2f} "
                  f"true-undisputed {row['shortage_true_win_prob_undisputed']:.2f}", flush=True)  # fmt: skip
    args.out.write_text(json.dumps(rows, indent=1) + "\n")
    summary = (
        pd.DataFrame(rows)
        .assign(bias=lambda d: d["bias"].astype(str))
        .groupby("bias")
        .mean(numeric_only=True)
    )
    print(
        summary[
            [
                "implied_realization_factor",
                "shortage_observed_win_rate",
                "shortage_true_win_prob_undisputed",
            ]
        ].round(3)
    )


if __name__ == "__main__":
    main()
