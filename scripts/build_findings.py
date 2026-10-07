"""Build docs/findings.json (and README charts) from SQL on the built warehouse (SYNTHETIC data).

Every number in the README comes from this file, and every value in this file comes from a query against
marts.*/metrics.* (using the metrics macros), the analysis SQL files, or the forecast CSVs.

Usage: python -m scripts.build_findings   (requires `make build forecast`)
"""

from __future__ import annotations

import json
import re
import textwrap
from pathlib import Path

import duckdb
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from data_gen.config import Config  # noqa: E402
from data_gen.load import DEFAULT_PATH  # noqa: E402
from forecast.model import mape  # noqa: E402
from warehouse.validate import findings as validator_findings  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "findings.json"
IMG = ROOT / "docs" / "img"
ANALYSIS = ROOT / "sql" / "analysis"
FORECAST = ROOT / "forecast" / "results"
INK, GREY, ACCENT, ALERT = "#1f2937", "#94a3b8", "#2563eb", "#d9480f"


def analysis(con, prefix: str) -> pd.DataFrame:
    return con.execute(next(ANALYSIS.glob(f"{prefix}_*.sql")).read_text()).df()


def row(con, sql: str) -> dict:
    return con.execute(sql).df().iloc[0].to_dict()


def money_short(value: float) -> str:
    return f"${value / 1e6:.1f}M" if abs(value) >= 1e6 else f"${value / 1e3:.0f}K"


def headline(con, years: float) -> dict:
    h = row(
        con,
        """
        select sum(gross_amount) as gross, sum(deduction_amount) as deductions, sum(recovered_amount) as recovered,
               metrics.deduction_rate(sum(deduction_amount), sum(gross_amount)) as deduction_rate,
               metrics.recovery_rate(sum(recovered_amount), sum(deduction_amount)) as recovery_rate,
               metrics.net_revenue(sum(gross_amount), sum(deduction_amount), sum(recovered_amount)) as net_revenue,
               metrics.deduction_rate(sum(deduction_amount) - sum(recovered_amount), sum(gross_amount)) as net_leakage_rate
        from metrics.m_invoice_detail""",
    )
    h["mature_deduction_rate"] = float(
        con.execute(
            "select metrics.deduction_rate(sum(deduction_amount) filter (where is_mature_month), "
            "sum(gross_amount) filter (where is_mature_month)) from metrics.m_retailer_month"
        ).fetchone()[0]
    )
    oldest = con.execute(
        "select aging_bucket, sum(open_amount) from metrics.m_deduction_detail where open_amount > 0 "
        "group by 1 order by 1 desc limit 1"
    ).fetchone()
    h["open_balance"] = float(
        con.execute("select sum(open_amount) from metrics.m_deduction_detail").fetchone()[0]
    )
    h["open_oldest_bucket"], h["open_oldest_share"] = (
        oldest[0],
        float(oldest[1]) / h["open_balance"],
    )
    h["net_leakage"] = h["deductions"] - h["recovered"]
    grid = analysis(con, "10").set_index(["window_days", "scenario"])["recoverable_amount"]
    h["recoverable_180_low"], h["recoverable_180_base"], h["recoverable_180_high"] = (
        grid[(180, s)] for s in ("low", "base", "high")
    )
    h["recoverable_180_history"] = h[
        "recoverable_180_high"
    ]  # realization factor 1.0 = pure historical rates
    h["recoverable_365_base"] = grid[(365, "base")]
    h["net_leakage_per_year"] = h["net_leakage"] / years
    return h


def finding1(con, years: float) -> dict:
    reasons = (
        con.execute("select * from metrics.m_reason_recovery order by reason_code")
        .df()
        .set_index("reason_code")
    )
    s = reasons.loc["shortage"]
    others = row(
        con,
        """
        select metrics.dispute_rate(sum(amount) filter (where is_disputed), sum(amount)) as dispute_rate,
               metrics.dispute_win_rate(count(*) filter (where is_win), count(*) filter (where is_resolved)) as win_rate
        from metrics.m_deduction_detail where reason_code <> 'shortage'""",
    )
    peers = row(
        con,
        """
        select metrics.dispute_rate(sum(amount) filter (where is_disputed), sum(amount)) as dispute_rate,
               metrics.dispute_win_rate(count(*) filter (where is_win), count(*) filter (where is_resolved)) as win_rate
        from metrics.m_deduction_detail where reason_code not in ('shortage', 'promo')""",
    )
    cand = row(
        con,
        """
        select count(*) as items, sum(amount) as amount, sum(expected_recovery) as expected
        from metrics.m_recoverable_candidates where reason_code = 'shortage'""",
    )
    cohorts = analysis(con, "05").dropna(subset=["win_rate"])
    return {
        "shortage_dispute_rate": float(s["dispute_rate"]),
        "shortage_win_rate": float(s["win_rate"]),
        "shortage_deducted": float(s["deduction_amount"]),
        "others_dispute_rate": float(others["dispute_rate"]),
        "others_win_rate": float(others["win_rate"]),
        "non_promo_peers_dispute_rate": float(peers["dispute_rate"]),
        "non_promo_peers_win_rate": float(peers["win_rate"]),
        "undisputed_items": int(cand["items"]),
        "undisputed_amount": float(cand["amount"]),
        "potential_recovery": float(cand["expected"]),
        "potential_recovery_per_year": float(cand["expected"]) / years,
        "fast_bucket": cohorts.iloc[0]["filing_lag_bucket"],
        "fast_win_rate": float(cohorts.iloc[0]["win_rate"]),
        "slow_bucket": cohorts.iloc[-1]["filing_lag_bucket"],
        "slow_win_rate": float(cohorts.iloc[-1]["win_rate"]),
        "by_reason": {
            r: {
                "dispute_rate": float(v["dispute_rate"]),
                "win_rate": float(v["win_rate"]),
                "deduction_amount": float(v["deduction_amount"]),
            }
            for r, v in reasons.iterrows()
        },
    }


def finding2(con, years: float) -> dict:
    sku = analysis(con, "03")
    name = sku["retailer_name"].iloc[0]
    rid = int(
        con.execute(
            "select retailer_id from marts.dim_retailer where retailer_name = ?", [name]
        ).fetchone()[0]
    )
    top2 = sku[sku["sku_rank"] <= 2]
    unattributed = sku[sku["sku_key"] == -1].iloc[0]
    fines = row(
        con,
        f"select sum(amount) as fines from metrics.m_deduction_detail where reason_code = 'compliance_fine' and retailer_id = {rid}",
    )
    gross = row(
        con,
        f"select sum(gross_amount) as gross from metrics.m_invoice_detail where retailer_id = {rid}",
    )
    peer_rate = float(sku["fine_rate"].iloc[0]) / float(sku["ratio_to_peer_median"].iloc[0])
    excess = float(fines["fines"]) - peer_rate * float(gross["gross"])
    cf = row(
        con,
        "select win_rate, dispute_rate from metrics.m_reason_recovery where reason_code = 'compliance_fine'",
    )
    return {
        "retailer": name,
        "ratio_to_peers": float(sku["ratio_to_peer_median"].iloc[0]),
        "fine_rate": float(sku["fine_rate"].iloc[0]),
        "peer_median_fine_rate": peer_rate,
        "fines_total": float(fines["fines"]),
        "excess_over_peer_rate": excess,
        "excess_per_year": excess / years,
        "top2_skus": [str(x) for x in top2["sku_label"]],
        "top2_share_of_all": float(top2["share_of_all_fines"].sum()),
        "top2_share_of_attributed": float(top2["share_of_attributed_fines"].sum()),
        "unattributed_share": float(unattributed["share_of_all_fines"]),
        "dilution_points": 100
        * float(top2["share_of_attributed_fines"].sum() - top2["share_of_all_fines"].sum()),
        "compliance_win_rate": float(cf["win_rate"]),
        "chart_rows": [
            {"label": r["sku_label"], "amount": float(r["fine_amount"])} for _, r in sku.iterrows()
        ],
    }


def finding3(con, total_deductions: float, years: float) -> dict:
    spike = analysis(con, "09")
    promo = row(
        con,
        "select deduction_amount, dispute_rate, win_rate from metrics.m_reason_recovery where reason_code = 'promo'",
    )
    cand = row(
        con,
        "select sum(amount) as amount, sum(expected_recovery) as expected from metrics.m_recoverable_candidates where reason_code = 'promo'",
    )
    monthly = con.execute("""
        select deduction_month as month, sum(deduction_amount) as amount from metrics.m_deductions_monthly
        where reason_code = 'promo' and not is_burn_in_month group by 1 order by 1""").df()
    return {
        "promo_amount": float(promo["deduction_amount"]),
        "promo_share_of_deductions": float(promo["deduction_amount"]) / total_deductions,
        "promo_dispute_rate": float(promo["dispute_rate"]),
        "promo_win_rate": float(promo["win_rate"]),
        "median_spike_index": float(spike["spike_index"].median()),
        "retailer_years_with_spike": int((spike["spike_index"] >= 1.5).sum()),
        "retailer_years": int(len(spike)),
        "undisputed_amount": float(cand["amount"]),
        "potential_recovery_upper_bound": float(cand["expected"]),
        "potential_recovery_per_year": float(cand["expected"]) / years,
        "monthly": [
            {"month": str(m)[:7], "amount": float(a)}
            for m, a in zip(monthly["month"], monthly["amount"], strict=True)
        ],
    }


def also_noticed(con) -> dict:
    lag = analysis(con, "08")
    latest = lag[lag["invoice_month"] == lag["invoice_month"].max()].sort_values("rank_by_change")
    first, second = latest.iloc[0], latest.iloc[1]
    anomalies = analysis(con, "07")
    planted = anomalies[(anomalies["retailer_id"] == 5) & (anomalies["reason_code"] == "shortage")]
    cells = row(con, "select count(*) as n from marts.dim_retailer")["n"] * 6 * 21
    return {
        "lag_retailer": first["retailer_name"],
        "lag_days": float(first["payment_lag_days"]),
        "lag_change_6m": float(first["change_vs_6m_ago"]),
        "lag_runner_up_change_6m": float(second["change_vs_6m_ago"]),
        "anomalies_flagged": int(len(anomalies)),
        "anomaly_cells_scored": int(cells),
        "planted_anomaly_months": sorted(m.strftime("%Y-%m") for m in planted["deduction_month"]),
    }


def forecast_summary(con) -> dict:
    fc = pd.read_csv(FORECAST / "backtest_forecasts.csv").dropna()
    scores = pd.read_csv(FORECAST / "backtest_mape.csv").pivot(
        index="retailer_id", columns="model", values="mape"
    )
    forward = pd.read_csv(FORECAST / "forward_forecast.csv", parse_dates=["month"])
    extra = json.loads((FORECAST / "comparison.json").read_text())
    comp, cov = extra["comparison"], extra["coverage"]
    months = [d.date().isoformat() for d in sorted(forward["month"].unique())]
    last_year = con.execute(
        "select coalesce(sum(deduction_amount), 0) from metrics.m_deductions_monthly where list_contains(?::DATE[], deduction_month)",
        [[(pd.Timestamp(m) - pd.DateOffset(years=1)).date() for m in months]],
    ).fetchone()[0]
    return {
        "pooled_mape_naive": mape(fc["actual"].to_numpy(), fc["seasonal_naive"].to_numpy()),
        "pooled_mape_hw": mape(fc["actual"].to_numpy(), fc["holt_winters"].to_numpy()),
        "retailers_hw_better": int((scores["holt_winters"] < scores["seasonal_naive"]).sum()),
        "retailers": int(len(scores)),
        "forward_total_hw": float(forward["holt_winters"].sum()),
        "forward_p10": float(forward["hw_p10"].sum()),
        "forward_p90": float(forward["hw_p90"].sum()),
        "same_months_last_year": float(last_year),
        "usable_months": int(
            con.execute(
                "select count(distinct deduction_month) from metrics.m_deductions_monthly where not is_burn_in_month"
            ).fetchone()[0]
        ),
        "mean_diff_points": 100 * comp["mean_diff_mape"],
        "boot_ci_low_points": 100 * comp["boot_ci_low"],
        "boot_ci_high_points": 100 * comp["boot_ci_high"],
        "boot_p": comp["boot_p_value"],
        "dm_p": comp["dm_hln_p_value"],
        "origins": comp["n_origins"],
        "origins_hw_better": comp["origins_hw_better"],
        "sign_test_p": comp["sign_test_p_value"],
        "coverage_out_of_sample": cov["out_of_sample_coverage"],
        "coverage_in_sample": cov["in_sample_coverage"],
        "coverage_nominal": cov["nominal"],
        "forward_first_month": months[0][:7],
        "forward_last_month": months[-1][:7],
    }


def audit_summary() -> dict:
    """Numbers from the committed audit sweeps (docs/audit/*.json), recomputed here from the raw sweep files."""
    audit = ROOT / "docs" / "audit"

    def load(name: str) -> pd.DataFrame:
        return pd.DataFrame(json.loads((audit / name).read_text()))

    null_b, null_a, planted = (
        load("null_before.json"),
        load("null_after.json"),
        load("planted_after.json"),
    )
    bias = load("bias_results.json")
    bias["level"] = bias["bias"].fillna(-1)
    factors = bias.groupby("level")["implied_realization_factor"].mean()
    shortage = bias.groupby("level")[
        ["shortage_observed_win_rate", "shortage_true_win_prob_undisputed"]
    ].mean()
    mutations = json.loads((audit / "mutation_final.json").read_text())
    return {
        "mutations_total": len(mutations),
        "mutations_killed": sum(m["status"] == "KILLED" for m in mutations),
        "runs": int(len(null_a)),
        "null_anomalies_before": float(null_b["p7_anomalies_flagged"].mean()),
        "null_anomalies_after": float(null_a["p7_anomalies_flagged"].mean()),
        "null_p3_before_runs_flagged": int((null_b["p3_flagged"].map(len) > 0).sum()),
        "null_p3_after_runs_flagged": int((null_a["p3_flagged"].map(len) > 0).sum()),
        "null_max_fine_ratio": float(null_a["p1_ratio"].max()),
        "planted_min_fine_ratio": float(planted["p1_ratio"].min()),
        "null_max_spike": float(null_a["p2_median_spike"].max()),
        "null_max_lag_change": float(null_a["p4_change_days"].max()),
        "null_recoverable_base_mean": float(null_a["recoverable_180_base"].mean()),
        "planted_recoverable_base_mean": float(planted["recoverable_180_base"].mean()),
        **{
            f"detected_{p}": int(planted[f"{p}_detected"].sum())
            for p in ("p1", "p2", "p3", "p4", "p5", "p7")
        },
        "bias_factor_none": float(factors[0.0]),
        "bias_factor_mid": float(factors[1.0]),
        "bias_factor_strong": float(factors[1.5]),
        "bias_shortage_observed_none": float(shortage.loc[0.0, "shortage_observed_win_rate"]),
        "bias_shortage_observed_strong": float(shortage.loc[1.5, "shortage_observed_win_rate"]),
        "bias_shortage_true_strong": float(shortage.loc[1.5, "shortage_true_win_prob_undisputed"]),
    }


def data_quality(con) -> dict:
    sku = row(
        con,
        """
        select avg(case when is_sku_attributed then 0 else 1 end) as null_rate_count,
               sum(amount) filter (where not is_sku_attributed) as null_amount, sum(amount) as total_amount
        from marts.fct_deductions""",
    )
    return {
        "sku_null_rate_count": float(sku["null_rate_count"]),
        "sku_null_rate_amount": float(sku["null_amount"]) / float(sku["total_amount"]),
        "dirty_findings": validator_findings(con, "raw_dirty"),
        "clean_findings": validator_findings(con, "raw"),
    }


def short_step(step: str) -> str:
    if step.startswith("Less: "):
        return "-" + step.removeprefix("Less: ").removesuffix(" deductions").replace("_", " ")
    return {
        "Plus: recovered via disputes": "+recovered",
        "Net revenue after deductions": "Net revenue",
    }.get(step, step)


def wrap(text: str) -> str:
    return textwrap.fill(text, 78)


def charts(f: dict, waterfall: pd.DataFrame) -> None:
    IMG.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.size": 9, "axes.spines.top": False, "axes.spines.right": False})

    def save(fig, name):
        fig.tight_layout()
        fig.savefig(IMG / name, dpi=110)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 3.6))
    labels = [short_step(step) for step in waterfall["step"]]
    running, bottoms, heights = 0.0, [], []
    for i, amt in enumerate(waterfall["amount"]):
        if i in (0, len(waterfall) - 1):
            bottoms.append(0), heights.append(amt), None
            running = amt if i == 0 else running
        else:
            bottoms.append(min(running, running + amt)), heights.append(abs(amt))
            running += amt
    colors = [INK] + [ALERT if a < 0 else ACCENT for a in waterfall["amount"][1:-1]] + [INK]
    ax.bar(labels, [h / 1e6 for h in heights], bottom=[b / 1e6 for b in bottoms], color=colors)
    ax.set_ylim(waterfall["amount"].iloc[-1] / 1e6 - 12, waterfall["amount"].iloc[0] / 1e6 + 3)
    ax.set_ylabel("$M (axis truncated)")
    ax.set_title(
        f"Retailers deducted {money_short(f['headline']['deductions'])} of {money_short(f['headline']['gross'])} gross; "
        f"{money_short(f['headline']['recovered'])} was won back",
        loc="left",
        fontsize=10,
        fontweight="bold",
    )
    plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
    save(fig, "waterfall.png")

    f1 = f["finding1"]
    reasons = sorted(
        f1["by_reason"],
        key=lambda r: f1["by_reason"][r]["win_rate"] - f1["by_reason"][r]["dispute_rate"],
        reverse=True,
    )
    fig, ax = plt.subplots(figsize=(8, 3.4))
    x = range(len(reasons))
    ax.bar(
        [i - 0.2 for i in x],
        [f1["by_reason"][r]["dispute_rate"] * 100 for r in reasons],
        0.4,
        color=GREY,
        label="Share of dollars disputed",
    )
    ax.bar(
        [i + 0.2 for i in x],
        [f1["by_reason"][r]["win_rate"] * 100 for r in reasons],
        0.4,
        color=ACCENT,
        label="Disputes won (full or partial)",
    )
    ax.set_xticks(list(x), [r.replace("_", " ") for r in reasons])
    ax.set_ylabel("%"), ax.legend(frameon=False)
    ax.set_title(
        wrap(
            f"Shortage deductions win {f1['shortage_win_rate']:.0%} of disputes but only {f1['shortage_dispute_rate']:.0%} of dollars are disputed"
        ),
        loc="left",
        fontsize=10,
        fontweight="bold",
    )
    save(fig, "finding1_recovery_gap.png")

    f2 = f["finding2"]
    rows = f2["chart_rows"]
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.barh(
        [r["label"] for r in rows][::-1],
        [r["amount"] / 1e3 for r in rows][::-1],
        color=[
            GREY
            if r["label"] == "(unattributed)"
            else (ALERT if r["label"] in f2["top2_skus"] else ACCENT)
            for r in rows
        ][::-1],
    )
    ax.set_xlabel("Compliance fines, $K (all 36 months)")
    ax.set_title(
        wrap(
            f"Two SKUs carry {f2['top2_share_of_all']:.0%} of {f2['retailer']}'s fines ({f2['top2_share_of_attributed']:.0%} of the attributable ones)"
        ),
        loc="left",
        fontsize=10,
        fontweight="bold",
    )
    save(fig, "finding2_fines_by_sku.png")

    f3 = f["finding3"]
    monthly = pd.DataFrame(f3["monthly"])
    monthly["month"] = pd.to_datetime(monthly["month"])
    fig, ax = plt.subplots(figsize=(8, 3.2))
    ax.plot(monthly["month"], monthly["amount"] / 1e3, color=ACCENT)
    for m in monthly["month"][monthly["month"].dt.month == 1]:
        ax.axvspan(m, m + pd.DateOffset(months=2), color=ALERT, alpha=0.15)
    ax.set_ylabel("Promo deductions, $K per month")
    ax.set_title(
        wrap(
            f"Promo deductions spike every Jan-Feb (median {f3['median_spike_index']:.1f}x the Mar-Sep level) and only {f3['promo_dispute_rate']:.0%} are disputed"
        ),
        loc="left",
        fontsize=10,
        fontweight="bold",
    )
    save(fig, "finding3_promo_spike.png")


def main() -> None:
    cfg = Config()
    con = duckdb.connect(str(DEFAULT_PATH), read_only=True)
    years = 36 / 12
    counts = row(
        con,
        """
        select (select count(*) from marts.fct_invoices) as invoices, (select sum(line_count) from marts.fct_invoices) as invoice_lines,
               (select count(*) from marts.fct_deductions) as deductions, (select count(*) from marts.fct_disputes) as disputes,
               (select count(*) from marts.dim_retailer) as retailers, (select count(*) from marts.dim_sku) - 1 as skus""",
    )
    wf = analysis(con, "01")
    result = {
        "meta": {
            "as_of": cfg.end_date.isoformat(),
            "seed": cfg.seed,
            "months": 36,
            "years": years,
            **{k: int(v) for k, v in counts.items()},
            "n_metrics": len(
                re.findall(r"^\| \d+ \|", (ROOT / "docs" / "METRICS.md").read_text(), re.M)
            ),
            "n_analysis_files": len(list(ANALYSIS.glob("*.sql"))),
        },
        "headline": headline(con, years),
    }
    result["finding1"] = finding1(con, years)
    result["finding2"] = finding2(con, years)
    result["finding3"] = finding3(con, result["headline"]["deductions"], years)
    result["also"] = also_noticed(con)
    result["forecast"] = forecast_summary(con)
    result["data_quality"] = data_quality(con)
    result["audit"] = audit_summary()
    result["waterfall"] = [
        {"step": s, "amount": float(a)} for s, a in zip(wf["step"], wf["amount"], strict=True)
    ]
    charts(result, wf)
    con.close()
    OUT.write_text(json.dumps(result, indent=2, default=float) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)} and {len(list(IMG.glob('*.png')))} charts in docs/img")


if __name__ == "__main__":
    main()
