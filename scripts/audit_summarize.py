"""Summarize the audit sweeps into docs/audit/summary.json and docs/audit/sweep_tables.md (SYNTHETIC data).

Inputs (written by scripts.audit_sweep / scripts.audit_bias): docs/audit/{null,planted}_{before,after}.json and
bias_results.json. The recoverable-dollar sensitivity grid is computed from the built warehouse.
Usage: python -m scripts.audit_summarize
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import pandas as pd

from data_gen.load import DEFAULT_PATH

AUDIT = Path(__file__).resolve().parents[1] / "docs" / "audit"
WINDOWS = [60, 90, 120, 180, 270, 365]
FACTORS = [0.25, 0.5, 0.75, 1.0]
EFFECTS = {
    "p1": ("Retailer A fines vs peers (x)", "p1_ratio"),
    "p2": ("Jan-Feb promo spike (x)", "p2_median_spike"),
    "p3": ("Shortage win rate", "p3_shortage_win_rate"),
    "p4": ("Retailer B lag change over 6 months (days)", "p4_change_days"),
    "p5": ("YoY revenue growth", "p5_growth"),
}


def load(name: str) -> pd.DataFrame:
    return pd.DataFrame(json.loads((AUDIT / name).read_text()))


def detection_table(planted: pd.DataFrame) -> list[dict]:
    rows = []
    for key, (label, column) in EFFECTS.items():
        rows.append({
            "pattern": key, "effect": label, "detected": int(planted[f"{key}_detected"].sum()), "runs": len(planted),
            "mean": float(planted[column].mean()), "min": float(planted[column].min()), "max": float(planted[column].max()),
            "false_positives": int(planted[f"{key}_false_positives"].sum()) if f"{key}_false_positives" in planted else None,
        })  # fmt: skip
    rows.append({
        "pattern": "p7", "effect": "Planted anomaly flagged (abs z >= 4.5)", "detected": int(planted["p7_detected"].sum()), "runs": len(planted),
        "mean": float(planted["p7_anomalies_flagged"].mean()), "min": float(planted["p7_anomalies_flagged"].min()),
        "max": float(planted["p7_anomalies_flagged"].max()), "false_positives": float(planted["p7_false_positives"].mean()),
    })  # fmt: skip
    return rows


def null_table(null: pd.DataFrame) -> dict:
    return {
        "runs": len(null),
        "p1_max_ratio": float(null["p1_ratio"].max()), "p1_mean_ratio": float(null["p1_ratio"].mean()),
        "p1_flagged_runs": int(null["p1_flagged_any"].sum()),
        "p2_max_median_spike": float(null["p2_median_spike"].max()), "p2_detected_runs": int(null["p2_detected"].sum()),
        "p2_retailer_years_spiking_mean": float(null["p2_retailer_years_spiking"].mean()),
        "p3_runs_with_a_flag": int((null["p3_flagged"].map(len) > 0).sum()),
        "p3_flags_per_run": float(null["p3_flagged"].map(len).mean()),
        "p4_max_change_days": float(null["p4_change_days"].max()), "p4_detected_runs": int(null["p4_detected"].sum()),
        "p5_detected_runs": int(null["p5_detected"].sum()),
        "anomalies_mean": float(null["p7_anomalies_flagged"].mean()),
        "anomalies_min": int(null["p7_anomalies_flagged"].min()), "anomalies_max": int(null["p7_anomalies_flagged"].max()),
        "recoverable_180_base_mean": float(null["recoverable_180_base"].mean()),
        "filing_lag_win_gap_mean": float(null["filing_lag_win_gap"].mean()),
    }  # fmt: skip


def bias_table(bias: pd.DataFrame) -> list[dict]:
    frame = bias.assign(level=bias["bias"].map(lambda b: "off" if pd.isna(b) else f"{b:g}"))
    grouped = frame.drop(columns="bias").groupby("level", sort=False).mean(numeric_only=True)
    return [
        {"bias": level, **{k: float(v) for k, v in row.items() if k != "seed"}}
        for level, row in grouped.iterrows()
    ]


def sensitivity(path: Path) -> dict:
    con = duckdb.connect(str(path), read_only=True)
    grid = {}
    for window in WINDOWS:
        history = con.execute(
            "select coalesce(sum(expected_recovery), 0) from metrics.m_recoverable_candidates where age_days <= ?",
            [window],
        ).fetchone()[0]
        grid[window] = {f"{factor:g}": float(history) * factor for factor in FACTORS}
    con.close()
    return grid


def main() -> None:
    summary = {
        "planted_after": detection_table(load("planted_after.json")),
        "planted_before": detection_table(load("planted_before.json")),
        "null_before": null_table(load("null_before.json")),
        "null_after": null_table(load("null_after.json")),
        "bias": bias_table(load("bias_results.json")),
        "sensitivity_180d_windows_by_factor": sensitivity(DEFAULT_PATH),
    }
    (AUDIT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n")
    lines = [
        "| Pattern | Effect | Detected | Mean | Min | Max | False positives (sum / mean) |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in summary["planted_after"]:
        lines.append(
            f"| {r['pattern']} | {r['effect']} | {r['detected']}/{r['runs']} | {r['mean']:.3f} | {r['min']:.3f} | {r['max']:.3f} | {r['false_positives']} |"
        )
    (AUDIT / "sweep_tables.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: summary[k] for k in ("null_before", "null_after")}, indent=1))


if __name__ == "__main__":
    main()
