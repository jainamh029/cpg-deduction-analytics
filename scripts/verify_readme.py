"""Independent check of EVERY number in README.md (SYNTHETIC data).

1. Every `{{ path|filter }}` token in docs/README.template.md has an independently computed value (SQL/pandas written
   against the RAW tables, the forecast CSVs and the raw audit sweep files; not marts, not metrics macros, not the
   analysis files). The check fails if a token has no independent value, if findings.json differs from it, or if the
   README does not show it formatted.
2. Every numeric literal typed in the template outside tokens, code and links must be a registered design constant
   with a source-of-truth check (below), so no README number can exist without a check.

Usage: python -m scripts.verify_readme [--warehouse PATH]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from scipy import stats

from data_gen.config import Config
from data_gen.dirty import EXPECTED_DIRTY_FINDINGS
from data_gen.load import DEFAULT_PATH
from forecast import model as forecast_model
from scripts.render_readme import FILTERS, FINDINGS, README, TEMPLATE, TOKEN, lookup
from warehouse.validate import findings as validator_findings

ROOT = Path(__file__).resolve().parents[1]
AS_OF = pd.Timestamp(Config().end_date)
BURN_IN_END = pd.Timestamp("2023-04-01")  # first invoice month + 3 months
SPIKE_MIN = 1.5
Z_MIN = 4.5


def _win_stats(ded: pd.DataFrame) -> pd.DataFrame:
    """Per reason: win rate (count, resolved disputes) and recovery ratio on won/partial disputes."""
    d = ded[ded["outcome"].notna()]
    resolved = d[d["outcome"].isin(["won", "partial", "lost"])]
    wins = d[d["outcome"].isin(["won", "partial"])]
    return pd.DataFrame({
        "win_rate": resolved.groupby("reason_code").apply(lambda g: g["outcome"].isin(["won", "partial"]).mean(), include_groups=False),
        "ratio": wins.groupby("reason_code").apply(lambda g: g["recovered"].sum() / g["amount"].sum(), include_groups=False),
    })  # fmt: skip


def _bucket(days: int) -> str:
    return "0-14" if days <= 14 else "15-30" if days <= 30 else "31-60" if days <= 60 else "61+"


def compute(
    con: duckdb.DuckDBPyConnection, forecast_dir: Path, audit_dir: Path
) -> dict[str, object]:
    inv = con.execute("select * from raw.invoices").df()
    ded = con.execute("select * from raw.deductions").df()
    disp = con.execute("select * from raw.disputes").df()
    pay = con.execute("select * from raw.payments").df()
    retailers = con.execute("select * from raw.retailers").df().set_index("retailer_id")["name"]
    for frame, cols in (
        (inv, ["gross_amount"]),
        (ded, ["amount"]),
        (disp, ["recovered_amount"]),
        (pay, ["paid_amount"]),
    ):
        frame[cols] = frame[cols].astype(float)
    # one row per deduction with its dispute (raw guarantees at most one); recoveries capped at the amount
    ded = ded.merge(
        disp[["deduction_id", "outcome", "filed_date", "recovered_amount"]],
        on="deduction_id",
        how="left",
    )
    ded["recovered"] = np.minimum(ded["recovered_amount"].fillna(0), ded["amount"])
    ded["deduction_date"], ded["filed_date"] = (
        pd.to_datetime(ded["deduction_date"]),
        pd.to_datetime(ded["filed_date"]),
    )
    ded["age"] = (AS_OF - ded["deduction_date"]).dt.days
    ded["disputed"] = ded["outcome"].notna()
    inv["invoice_date"] = pd.to_datetime(inv["invoice_date"])
    out: dict[str, object] = {}

    # ---- meta
    out["meta.months"] = int(inv["invoice_date"].dt.to_period("M").nunique())
    out["meta.seed"], out["meta.as_of"] = Config().seed, Config().end_date.isoformat()
    out["meta.invoices"], out["meta.deductions"], out["meta.disputes"] = (
        len(inv),
        len(ded),
        len(disp),
    )
    out["meta.invoice_lines"] = con.execute("select count(*) from raw.invoice_lines").fetchone()[0]
    out["meta.retailers"], out["meta.skus"] = (
        len(retailers),
        con.execute("select count(*) from raw.skus").fetchone()[0],
    )
    out["meta.n_metrics"] = len(
        re.findall(r"^\| \d+ \|", (ROOT / "docs" / "METRICS.md").read_text(), re.M)
    )
    out["meta.n_analysis_files"] = len(list((ROOT / "sql" / "analysis").glob("*.sql")))

    # ---- headline
    gross, total_ded, recovered = (
        inv["gross_amount"].sum(),
        ded["amount"].sum(),
        ded["recovered"].sum(),
    )
    mature_invoices = inv[
        inv["invoice_date"] < AS_OF.replace(day=1) - pd.DateOffset(months=3)
    ]  # month + 4 months <= as-of
    mature_ded = ded[ded["invoice_id"].isin(mature_invoices["invoice_id"])]["amount"].sum()
    out.update({
        "headline.gross": gross, "headline.deductions": total_ded, "headline.recovered": recovered,
        "headline.deduction_rate": total_ded / gross, "headline.recovery_rate": recovered / total_ded,
        "headline.mature_deduction_rate": mature_ded / mature_invoices["gross_amount"].sum(),
        "headline.net_leakage": total_ded - recovered, "headline.net_leakage_rate": (total_ded - recovered) / gross,
    })  # fmt: skip
    stats_by_reason = _win_stats(ded)
    cand = ded[~ded["disputed"] & ded["status"].isin(["open", "written_off"])].copy()
    cand["expected"] = (
        cand["amount"]
        * cand["reason_code"].map(stats_by_reason["win_rate"])
        * cand["reason_code"].map(stats_by_reason["ratio"])
    )
    history = cand.loc[cand["age"] <= 180, "expected"].sum()
    out.update({
        "headline.recoverable_180_history": history, "headline.recoverable_180_high": history,
        "headline.recoverable_180_base": 0.75 * history, "headline.recoverable_180_low": 0.5 * history,
        "headline.recoverable_365_base": 0.75 * cand.loc[cand["age"] <= 365, "expected"].sum(),
    })  # fmt: skip

    # ---- finding 1: shortage
    short = ded[ded["reason_code"] == "shortage"]
    peers = ded[~ded["reason_code"].isin(["shortage", "promo"])]

    def rate(g: pd.DataFrame) -> float:
        return g.loc[g["disputed"], "amount"].sum() / g["amount"].sum()

    def win(g: pd.DataFrame) -> float:
        wins = g["outcome"].isin(["won", "partial"]).sum()
        return wins / g["outcome"].isin(["won", "partial", "lost"]).sum()

    s_cand = cand[cand["reason_code"] == "shortage"]
    lagged = ded[ded["disputed"]].assign(
        bucket=lambda d: (d["filed_date"] - d["deduction_date"]).dt.days.map(_bucket)
    )
    cohort_win = lagged.groupby("bucket").apply(win, include_groups=False)
    buckets = [b for b in ("0-14", "15-30", "31-60", "61+") if b in cohort_win.index]
    out.update({
        "finding1.shortage_deducted": short["amount"].sum(), "finding1.shortage_dispute_rate": rate(short), "finding1.shortage_win_rate": win(short),
        "finding1.non_promo_peers_dispute_rate": rate(peers), "finding1.non_promo_peers_win_rate": win(peers),
        "finding1.undisputed_items": len(s_cand), "finding1.undisputed_amount": s_cand["amount"].sum(),
        "finding1.potential_recovery": s_cand["expected"].sum(), "finding1.potential_recovery_per_year": s_cand["expected"].sum() / 3,
        "finding1.fast_bucket": buckets[0], "finding1.fast_win_rate": cohort_win[buckets[0]],
        "finding1.slow_bucket": buckets[-1], "finding1.slow_win_rate": cohort_win[buckets[-1]],
    })  # fmt: skip

    # ---- finding 2: compliance fines
    fines = ded[ded["reason_code"] == "compliance_fine"]
    gross_by = inv.groupby("retailer_id")["gross_amount"].sum()
    fine_rate = (
        fines.groupby("retailer_id")["amount"].sum().reindex(gross_by.index).fillna(0) / gross_by
    )
    ratios = pd.Series({r: fine_rate[r] / fine_rate.drop(r).median() for r in fine_rate.index})
    top = int(ratios.idxmax())
    mine = fines[fines["retailer_id"] == top]
    by_sku = mine.dropna(subset=["sku_id"]).groupby("sku_id")["amount"].sum().nlargest(2)
    attributed = mine["amount"][mine["sku_id"].notna()].sum()
    peer_rate = fine_rate.drop(top).median()
    excess = mine["amount"].sum() - peer_rate * gross_by[top]
    out.update({
        "finding2.retailer": retailers[top], "finding2.ratio_to_peers": ratios[top], "finding2.fine_rate": fine_rate[top],
        "finding2.peer_median_fine_rate": peer_rate, "finding2.fines_total": mine["amount"].sum(),
        "finding2.excess_over_peer_rate": excess, "finding2.top2_skus": [f"SKU {int(s):03d}" for s in by_sku.index],
        "finding2.top2_share_of_attributed": by_sku.sum() / attributed, "finding2.top2_share_of_all": by_sku.sum() / mine["amount"].sum(),
        "finding2.unattributed_share": mine.loc[mine["sku_id"].isna(), "amount"].sum() / mine["amount"].sum(),
        "finding2.dilution_points": 100 * (by_sku.sum() / attributed - by_sku.sum() / mine["amount"].sum()),
        "finding2.compliance_win_rate": win(fines),
    })  # fmt: skip

    # ---- finding 3: promo
    promo = ded[ded["reason_code"] == "promo"]
    p_cand = cand[cand["reason_code"] == "promo"]
    monthly = promo[promo["deduction_date"] >= BURN_IN_END].assign(
        y=lambda d: d["deduction_date"].dt.year, m=lambda d: d["deduction_date"].dt.month
    )
    monthly = monthly.groupby(["retailer_id", "y", "m"])["amount"].sum().reset_index()
    spikes = []
    for (_, _), g in monthly[monthly["y"].isin([2024, 2025])].groupby(["retailer_id", "y"]):
        spikes.append(
            g[g["m"] <= 2]["amount"].mean() / g[(g["m"] >= 3) & (g["m"] <= 9)]["amount"].mean()
        )
    out.update({
        "finding3.promo_amount": promo["amount"].sum(), "finding3.promo_share_of_deductions": promo["amount"].sum() / total_ded,
        "finding3.promo_dispute_rate": rate(promo), "finding3.promo_win_rate": win(promo),
        "finding3.median_spike_index": float(np.median(spikes)), "finding3.retailer_years_with_spike": int(sum(s >= SPIKE_MIN for s in spikes)),
        "finding3.retailer_years": len(spikes), "finding3.undisputed_amount": p_cand["amount"].sum(),
        "finding3.potential_recovery_upper_bound": p_cand["expected"].sum(),
    })  # fmt: skip

    # ---- also noticed: payment lag, anomalies
    paid = inv.merge(
        pay.groupby("invoice_id")
        .agg(paid=("paid_amount", "sum"), last=("paid_date", "max"))
        .reset_index(),
        on="invoice_id",
    )
    paid["days"] = (pd.to_datetime(paid["last"]) - paid["invoice_date"]).dt.days
    paid["month"] = paid["invoice_date"].dt.to_period("M").dt.to_timestamp()
    lag = paid.groupby(["retailer_id", "month"]).apply(
        lambda g: (g["days"] * g["paid"]).sum() / g["paid"].sum(), include_groups=False
    )
    latest, then = (
        pd.Timestamp("2025-08-01"),
        pd.Timestamp("2025-02-01"),
    )  # latest mature month and 6 months before
    change = pd.Series({r: lag[(r, latest)] - lag[(r, then)] for r in retailers.index}).sort_values(
        ascending=False
    )
    out.update({
        "also.lag_retailer": retailers[change.index[0]], "also.lag_days": lag[(change.index[0], latest)],
        "also.lag_change_6m": change.iloc[0], "also.lag_runner_up_change_6m": change.iloc[1],
    })  # fmt: skip
    series = ded[ded["deduction_date"] >= BURN_IN_END].assign(
        month=lambda d: d["deduction_date"].dt.to_period("M").dt.to_timestamp()
    )
    series = series.groupby(["retailer_id", "reason_code", "month"])["amount"].sum()
    months = pd.date_range(BURN_IN_END, "2025-12-01", freq="MS")
    flagged, scored, planted = 0, 0, []
    for r in retailers.index:
        for reason in ("shortage", "promo", "compliance_fine", "pricing", "damage", "other"):
            s = pd.Series([series.get((r, reason, m), 0.0) for m in months], index=months)
            for i in range(12, len(s)):
                base = s.iloc[i - 12 : i]
                if base.std(ddof=1) > 0:
                    scored += 1
                    if abs((s.iloc[i] - base.mean()) / base.std(ddof=1)) >= Z_MIN:
                        flagged += 1
                        if r == 5 and reason == "shortage":
                            planted.append(s.index[i].strftime("%Y-%m"))
    out.update(
        {
            "also.anomalies_flagged": flagged,
            "also.anomaly_cells_scored": scored,
            "also.planted_anomaly_months": sorted(planted),
        }
    )

    # ---- forecast (from the CSV artifacts; bootstrap/DM re-implemented here)
    fc = pd.read_csv(forecast_dir / "backtest_forecasts.csv").dropna()
    fc["ape_n"] = (fc["actual"] - fc["seasonal_naive"]).abs() / fc["actual"]
    fc["ape_h"] = (fc["actual"] - fc["holt_winters"]).abs() / fc["actual"]
    per_retailer = fc.groupby("retailer_id")[["ape_n", "ape_h"]].mean()
    d = (
        fc.groupby("origin_month")["ape_n"].mean() - fc.groupby("origin_month")["ape_h"].mean()
    ).to_numpy()
    n, h = len(d), 3
    dm = d.mean() / (d.std(ddof=1) / np.sqrt(n)) * np.sqrt((n + 1 - 2 * h + h * (h - 1) / n) / n)
    boot = np.random.default_rng(20260101).choice(d, size=(10_000, n), replace=True).mean(axis=1)
    fc["ratio"] = fc["actual"] / fc["holt_winters"]
    origins = sorted(fc["origin_month"].unique())
    hits = total = 0
    for origin in origins[1:]:
        past, now = fc[fc["origin_month"] < origin], fc[fc["origin_month"] == origin]
        lo, hi = (
            past.groupby("horizon")["ratio"].quantile(0.1),
            past.groupby("horizon")["ratio"].quantile(0.9),
        )
        ok = (now["ratio"] >= now["horizon"].map(lo)) & (now["ratio"] <= now["horizon"].map(hi))
        hits, total = hits + int(ok.sum()), total + len(now)
    fwd = pd.read_csv(forecast_dir / "forward_forecast.csv", parse_dates=["month"])
    prior = ded[(ded["deduction_date"] >= "2025-01-01") & (ded["deduction_date"] < "2025-04-01")][
        "amount"
    ].sum()
    out.update({
        "forecast.pooled_mape_hw": fc["ape_h"].mean(), "forecast.pooled_mape_naive": fc["ape_n"].mean(),
        "forecast.retailers_hw_better": int((per_retailer["ape_h"] < per_retailer["ape_n"]).sum()), "forecast.retailers": len(per_retailer),
        "forecast.origins": n, "forecast.mean_diff_points": 100 * d.mean(),
        "forecast.boot_ci_low_points": 100 * np.percentile(boot, 2.5), "forecast.boot_ci_high_points": 100 * np.percentile(boot, 97.5),
        "forecast.boot_p": 2 * min((boot <= 0).mean(), (boot >= 0).mean()), "forecast.dm_p": 2 * stats.t.sf(abs(dm), df=n - 1),
        "forecast.coverage_nominal": 0.8, "forecast.coverage_out_of_sample": hits / total,
        "forecast.forward_total_hw": fwd["holt_winters"].sum(), "forecast.forward_p10": fwd["hw_p10"].sum(), "forecast.forward_p90": fwd["hw_p90"].sum(),
        "forecast.forward_first_month": fwd["month"].min().strftime("%Y-%m"), "forecast.forward_last_month": fwd["month"].max().strftime("%Y-%m"),
        "forecast.same_months_last_year": prior,
        "forecast.usable_months": len(pd.date_range(BURN_IN_END, ded["deduction_date"].max(), freq="MS")),
    })  # fmt: skip

    # ---- data quality
    out["data_quality.sku_null_rate_count"] = float(ded["sku_id"].isna().mean())
    out["data_quality.sku_null_rate_amount"] = (
        ded.loc[ded["sku_id"].isna(), "amount"].sum() / total_ded
    )
    out["data_quality.dirty_findings"] = dict(EXPECTED_DIRTY_FINDINGS)
    out["data_quality.clean_findings"] = validator_findings(con, "raw")

    # ---- audit sweeps (recomputed from the raw sweep files)
    load = lambda name: pd.DataFrame(json.loads((audit_dir / name).read_text()))  # noqa: E731
    nb, na, pl, bias = (
        load("null_before.json"),
        load("null_after.json"),
        load("planted_after.json"),
        load("bias_results.json"),
    )
    bias["level"] = bias["bias"].fillna(-1)
    fac = bias.groupby("level")["implied_realization_factor"].mean()
    sh = bias.groupby("level")[
        ["shortage_observed_win_rate", "shortage_true_win_prob_undisputed"]
    ].mean()
    out.update({
        "audit.runs": len(na), "audit.null_anomalies_before": nb["p7_anomalies_flagged"].mean(), "audit.null_anomalies_after": na["p7_anomalies_flagged"].mean(),
        "audit.null_p3_before_runs_flagged": int((nb["p3_flagged"].map(len) > 0).sum()), "audit.null_p3_after_runs_flagged": int((na["p3_flagged"].map(len) > 0).sum()),
        "audit.null_max_fine_ratio": na["p1_ratio"].max(), "audit.planted_min_fine_ratio": pl["p1_ratio"].min(),
        "audit.null_max_spike": na["p2_median_spike"].max(), "audit.null_max_lag_change": na["p4_change_days"].max(),
        "audit.null_recoverable_base_mean": na["recoverable_180_base"].mean(),
        **{f"audit.detected_{p}": int(pl[f"{p}_detected"].sum()) for p in ("p1", "p2", "p3", "p4", "p5", "p7")},
        "audit.bias_factor_none": fac[0.0], "audit.bias_factor_strong": fac[1.5],
        "audit.bias_shortage_observed_none": sh.loc[0.0, "shortage_observed_win_rate"], "audit.bias_shortage_observed_strong": sh.loc[1.5, "shortage_observed_win_rate"],
        "audit.bias_shortage_true_strong": sh.loc[1.5, "shortage_true_win_prob_undisputed"],
    })  # fmt: skip
    return out


def design_constants(con) -> dict[str, tuple[str, bool]]:
    """Numeric literals allowed in the template, each with the source of truth it is checked against."""
    macros = (ROOT / "macros" / "metric_definitions.sql").read_text()
    scen = (
        con.execute("select window_days, realization_factor from metrics.m_recovery_scenarios").df()
        if _has(con)
        else None
    )
    windows = set(scen["window_days"]) if scen is not None else set()
    factors = {float(x) for x in scen["realization_factor"]} if scen is not None else set()
    py = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["requires-python"]
    return {
        "4": (
            "maturity rule: macros/metric_definitions.sql 'interval 4 month'",
            "interval 4 month" in macros,
        ),
        "180": ("dispute window in metrics.m_recovery_scenarios", 180 in windows),
        "365": ("dispute window in metrics.m_recovery_scenarios", 365 in windows),
        "0.5": ("realization factor in metrics.m_recovery_scenarios", 0.5 in factors),
        "0.75": ("realization factor in metrics.m_recovery_scenarios", 0.75 in factors),
        "1.0": ("realization factor in metrics.m_recovery_scenarios", 1.0 in factors),
        "2.0": (
            "outlier threshold in analysis 03",
            ">= 2.0" in next((ROOT / "sql/analysis").glob("03_*.sql")).read_text(),
        ),
        "1.5": (
            "spike threshold used by this verifier and build_findings",
            ">= 1.5" in (ROOT / "scripts/build_findings.py").read_text(),
        ),
        "4.5": (
            "z threshold in analysis 07",
            ">= 4.5" in next((ROOT / "sql/analysis").glob("07_*.sql")).read_text(),
        ),
        "24": ("forecast.model.FIRST_ORIGIN", forecast_model.FIRST_ORIGIN == 24),
        "3": (
            "forecast.model.HORIZON; also finding numbers and the original z >= 3 (DECISIONS D42)",
            forecast_model.HORIZON == 3,
        ),
        "95": (
            "2.5 / 97.5 percentiles in forecast.model.compare_models",
            "2.5" in (ROOT / "forecast/model.py").read_text(),
        ),
        "3.11": ("pyproject requires-python", "3.11" in py),
        "1": ("structural: finding / list numbering", True),
        "2": ("structural: finding / list numbering", True),
        "5": ("structural: list numbering", True),
        "08": ("structural: analysis file number", any(ROOT.glob("sql/analysis/08_*.sql"))),
    }


def _has(con) -> bool:
    return bool(
        con.execute(
            "select count(*) from information_schema.tables where table_schema = 'metrics' and table_name = 'm_recovery_scenarios'"
        ).fetchone()[0]
    )


def numeric_literals(template: str) -> list[str]:
    text = re.sub(r"```.*?```", "", template, flags=re.S)
    text = TOKEN.sub("", text)
    text = re.sub(r"\]\([^)]*\)", "]", text)
    text = re.sub(r"`[^`]*`", "", text)
    return re.findall(r"(?<![A-Za-z_])\d+(?:[.,]\d+)*", text)


def close(a, b) -> bool:
    if isinstance(a, int | float | np.floating | np.integer) and isinstance(
        b, int | float | np.floating | np.integer
    ):
        return abs(float(a) - float(b)) <= 1e-6 * max(1.0, abs(float(b)))
    return a == b


def verify(
    warehouse: Path, findings_path: Path = FINDINGS, readme_path: Path = README, forecast_dir: Path | None = None,
    audit_dir: Path | None = None, template_path: Path = TEMPLATE,
) -> list[str]:  # fmt: skip
    forecast_dir = forecast_dir or ROOT / "forecast" / "results"
    audit_dir = audit_dir or ROOT / "docs" / "audit"
    findings, readme, template = (
        json.loads(findings_path.read_text()),
        readme_path.read_text(),
        template_path.read_text(),
    )
    con = duckdb.connect(str(warehouse), read_only=True)
    values = compute(con, forecast_dir, audit_dir)
    constants = design_constants(con)
    con.close()
    failures: list[str] = []
    tokens = [m.group(1) for m in TOKEN.finditer(template) if not m.group(1).startswith("include:")]
    checked = 0
    for expr in dict.fromkeys(tokens):
        path, _, name = expr.partition("|")
        if path not in values:
            failures.append(f"{path}: README number has NO independent check")
            print(f"FAIL {path:<42} no independent check")
            continue
        independent, stored = values[path], lookup(findings, path)
        shown = FILTERS[name or "str"](stored if isinstance(independent, dict) else independent)
        ok = close(stored, independent) and shown in readme
        checked += 1
        print(
            f"{'ok' if ok else 'FAIL':<5}{path:<42} independent={str(independent)[:34]:<36} README shows {shown!r}: {shown in readme}"
        )
        if not ok:
            failures.append(path)
    for literal in sorted(set(numeric_literals(template))):
        if literal not in constants:
            failures.append(f"literal {literal}")
            print(
                f"FAIL literal {literal!r} typed in the template has no registered source of truth"
            )
        elif not constants[literal][1]:
            failures.append(f"literal {literal}")
            print(f"FAIL literal {literal!r}: source of truth disagrees ({constants[literal][0]})")
        else:
            print(f"ok   literal {literal!r:<8} = {constants[literal][0]}")
    print(
        f"{checked} tokens independently checked, {len(set(numeric_literals(template)))} design constants checked"
    )
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
