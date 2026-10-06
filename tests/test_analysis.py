"""Phase 4: every analysis query runs, is documented, and matches independently written SQL on RAW tables.

The independent checks deliberately avoid marts/metrics (they read `raw.*` and use plain SQL), so a bug
in a mart, macro or analysis query cannot hide by being shared. As-of date: 2025-12-31.
"""

import re
from pathlib import Path

import pandas as pd
import pytest

from .helpers import REPO_ROOT

ANALYSIS_DIR = REPO_ROOT / "sql" / "analysis"
FILES = sorted(ANALYSIS_DIR.glob("*.sql"))
AS_OF = "date '2025-12-31'"


def run(con, prefix: str):
    path = next(p for p in FILES if p.name.startswith(prefix))
    return con.execute(path.read_text()).df()


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def test_between_8_and_10_analysis_files():
    assert 8 <= len(FILES) <= 10


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.name)
def test_file_header_and_execution(bcon, path: Path):
    head = "\n".join(path.read_text().splitlines()[:14])
    for label in ("-- Business question:", "-- Metrics used:", "-- Assumptions:"):
        assert label in head, f"{path.name} header lacks {label}"
    assert len(bcon.execute(path.read_text()).fetchall()) > 0


def test_01_waterfall_components_sum_to_net_and_match_raw(bcon):
    df = run(bcon, "01")
    gross = scalar(bcon, "select sum(gross_amount) from raw.invoices")
    ded = scalar(bcon, "select sum(amount) from raw.deductions")
    rec = scalar(bcon, "select sum(recovered_amount) from raw.disputes")
    steps = df.set_index("step_order")["amount"]
    assert steps[1] == pytest.approx(float(gross))
    assert steps[9] == pytest.approx(float(gross - ded + rec))
    assert steps.loc[1:8].sum() == pytest.approx(steps[9])  # components sum to net
    raw_by_reason = dict(
        bcon.execute("select reason_code, sum(amount) from raw.deductions group by 1").fetchall()
    )
    for step, amount in zip(df["step"], df["amount"], strict=True):
        if step.startswith("Less: "):
            reason = step.removeprefix("Less: ").removesuffix(" deductions")
            assert -amount == pytest.approx(float(raw_by_reason[reason]))
    assert list(steps.index) == list(range(1, 10))


def test_02_rate_trend_rows_values_and_ranks(bcon):
    df = run(bcon, "02")
    expected_rows = scalar(
        bcon,
        "select count(*) from (select retailer_id, date_trunc('month', invoice_date) as m from raw.invoices "
        f"group by 1, 2 having m + interval 4 month <= {AS_OF})",
    )
    assert len(df) == expected_rows == 12 * 32
    month = "date '2023-03-01'"
    independent = scalar(
        bcon,
        f"select sum(d.amount) / (select sum(gross_amount) from raw.invoices where retailer_id = 1 and date_trunc('month', invoice_date) = {month}) "
        f"from raw.deductions d join raw.invoices i using (invoice_id) where i.retailer_id = 1 and date_trunc('month', i.invoice_date) = {month}",
    )
    row = df[(df["retailer_id"] == 1) & (df["invoice_month"] == "2023-03-01")].iloc[0]
    assert row["deduction_rate"] == pytest.approx(float(independent))
    three = scalar(
        bcon,
        "select sum(d.amount) / sum(i.gross_amount) from raw.invoices i left join "
        "(select invoice_id, sum(amount) as amount from raw.deductions group by 1) d using (invoice_id) "
        "where i.retailer_id = 1 and i.invoice_date >= date '2023-01-01' and i.invoice_date < date '2023-04-01'",
    )
    assert row["rate_3m"] == pytest.approx(float(three))
    assert (
        df.groupby("invoice_month")["rank_in_month"]
        .apply(lambda s: sorted(s) == list(range(1, 13)))
        .all()
    )


def test_03_fine_outlier_and_sku_concentration_with_unattributed_bucket(bcon):
    df = run(bcon, "03")
    rates = (
        bcon.execute(
            "select i.retailer_id, coalesce(f.fines, 0) / sum(i.gross_amount) as rate from raw.invoices i "
            "left join (select retailer_id, sum(amount) as fines from raw.deductions where reason_code = 'compliance_fine' group by 1) f "
            "using (retailer_id) group by i.retailer_id, f.fines"
        )
        .df()
        .set_index("retailer_id")["rate"]
    )
    expected_ratio = rates[1] / rates.drop(1).median()
    assert set(df["retailer_name"]) == {"Retailer A"}
    assert df["ratio_to_peer_median"].iloc[0] == pytest.approx(float(expected_ratio))
    fines_a = bcon.execute(
        "select sku_id, sum(amount) as amt from raw.deductions where reason_code = 'compliance_fine' and retailer_id = 1 group by 1"
    ).df()
    total = fines_a["amt"].sum()
    attributed = fines_a.dropna(subset=["sku_id"])["amt"].sum()
    top2 = fines_a.dropna(subset=["sku_id"]).nlargest(2, "amt")
    assert (
        set(df.loc[df["sku_rank"] <= 2, "sku_key"]) == {int(s) for s in top2["sku_id"]} == {41, 187}
    )
    assert df.loc[df["sku_rank"] <= 2, "share_of_all_fines"].sum() == pytest.approx(
        float(top2["amt"].sum() / total)
    )
    assert df.loc[df["sku_rank"] <= 2, "share_of_attributed_fines"].sum() == pytest.approx(
        float(top2["amt"].sum() / attributed)
    )
    unattributed = df[df["sku_key"] == -1].iloc[0]
    assert unattributed["sku_label"] == "(unattributed)"
    assert unattributed["fine_amount"] == pytest.approx(
        float(fines_a[fines_a["sku_id"].isna()]["amt"].sum())
    )


def test_04_open_balance_and_buckets_match_raw(bcon):
    df = run(bcon, "04")
    raw_total = scalar(
        bcon, "select sum(amount) from raw.deductions where status in ('open', 'disputed')"
    )
    assert df["open_balance"].sum() == pytest.approx(float(raw_total))
    raw_buckets = dict(
        bcon.execute(
            f"select case when {AS_OF} - deduction_date <= 30 then '0-30' when {AS_OF} - deduction_date <= 60 then '31-60' "
            f"when {AS_OF} - deduction_date <= 90 then '61-90' else '90+' end as bucket, sum(amount) "
            "from raw.deductions where status in ('open', 'disputed') group by 1"
        ).fetchall()
    )
    got = df.groupby("aging_bucket")["open_balance"].sum()
    assert set(got.index) == set(raw_buckets)
    for bucket, amount in raw_buckets.items():
        assert got[bucket] == pytest.approx(float(amount))


def test_05_filing_lag_cohorts_match_raw_and_faster_wins_more(bcon):
    df = run(bcon, "05").set_index("filing_lag_bucket")
    raw = (
        bcon.execute(
            "select case when x.filed_date - d.deduction_date <= 14 then '0-14' when x.filed_date - d.deduction_date <= 30 then '15-30' "
            "when x.filed_date - d.deduction_date <= 60 then '31-60' else '61+' end as bucket, "
            "count(*) as n, count(*) filter (where x.outcome in ('won', 'partial')) * 1.0 / "
            "count(*) filter (where x.outcome <> 'pending') as win_rate "
            "from raw.disputes x join raw.deductions d using (deduction_id) group by 1"
        )
        .df()
        .set_index("bucket")
    )
    assert list(df.index) == ["0-14", "15-30", "31-60", "61+"]
    for bucket in df.index:
        assert df.loc[bucket, "disputes"] == raw.loc[bucket, "n"]
        assert df.loc[bucket, "win_rate"] == pytest.approx(float(raw.loc[bucket, "win_rate"]))
    # By construction the generator lowers win probability as filing lag grows (see PLANTED_PATTERNS.md).
    assert df["win_rate"].is_monotonic_decreasing


def test_06_underinvestment_matches_raw_and_flags_shortage_only(bcon):
    df = run(bcon, "06").set_index("reason_code")
    raw = (
        bcon.execute(
            "select d.reason_code, sum(d.amount) filter (where x.dispute_id is not null) / sum(d.amount) as dispute_rate, "
            "count(*) filter (where x.outcome in ('won', 'partial')) * 1.0 / count(*) filter (where x.outcome in ('won', 'partial', 'lost')) as win_rate "
            "from raw.deductions d left join raw.disputes x using (deduction_id) group by 1"
        )
        .df()
        .set_index("reason_code")
    )
    for reason in raw.index:
        assert df.loc[reason, "dispute_rate"] == pytest.approx(
            float(raw.loc[reason, "dispute_rate"])
        )
        assert df.loc[reason, "win_rate"] == pytest.approx(float(raw.loc[reason, "win_rate"]))
    assert set(df.index[df["under_invested"]]) == {"shortage"}


def test_07_anomalies_find_the_planted_event_and_not_too_many_others(bcon):
    df = run(bcon, "07")
    planted = df[(df["retailer_id"] == 5) & (df["reason_code"] == "shortage")]
    months = {m.strftime("%Y-%m") for m in planted["deduction_month"]}
    assert months & {"2025-04", "2025-05"}, (
        f"planted Retailer E shortage spike not flagged: {months}"
    )
    cells = 12 * 6 * 21  # retailers x reasons x scored months (Apr 2024 .. Dec 2025)
    assert len(df) <= 0.04 * cells  # not an implausible number of other flags
    assert (df["z_score"].abs() >= 4.5).all()
    # Independent z-score for the planted cell, from raw deductions.
    monthly = (
        bcon.execute(
            "select date_trunc('month', deduction_date)::date as m, sum(amount) as amt from raw.deductions "
            "where retailer_id = 5 and reason_code = 'shortage' group by 1 order by 1"
        )
        .df()
        .set_index("m")["amt"]
        .astype(float)
    )
    target = monthly.index[monthly.index.astype(str) == "2025-05-01"][0]
    baseline = monthly[
        (monthly.index >= target - pd.DateOffset(months=12)) & (monthly.index < target)
    ]
    z = (monthly[target] - baseline.mean()) / baseline.std(ddof=1)
    row = planted[planted["deduction_month"].astype(str).str.startswith("2025-05")].iloc[0]
    assert row["z_score"] == pytest.approx(float(z))


def test_08_payment_lag_drift_flags_retailer_b_and_matches_raw(bcon):
    df = run(bcon, "08")
    assert len(df) == 12 * 32
    latest = df[df["invoice_month"] == df["invoice_month"].max()]
    assert latest.sort_values("rank_by_change").iloc[0]["retailer_name"] == "Retailer B"
    independent = scalar(
        bcon,
        "select sum((p.paid_date - i.invoice_date) * p.paid_amount) / sum(p.paid_amount) from raw.invoices i "
        "join raw.payments p using (invoice_id) where i.retailer_id = 2 and date_trunc('month', i.invoice_date) = date '2025-08-01'",
    )
    got = latest[latest["retailer_id"] == 2]["payment_lag_days"].iloc[0]
    assert got == pytest.approx(float(independent))


def test_09_promo_spike_rows_values_and_dispute_rate(bcon):
    df = run(bcon, "09")
    assert len(df) == 12 * 2
    monthly = bcon.execute(
        "select extract(month from deduction_date) as mo, extract(year from deduction_date) as yr, "
        "date_trunc('month', deduction_date) as m, sum(amount) as amt from raw.deductions "
        "where reason_code = 'promo' and retailer_id = 1 group by 1, 2, 3"
    ).df()
    y24 = monthly[monthly["yr"] == 2024]
    expected = (
        y24[y24["mo"] <= 2]["amt"].astype(float).mean()
        / y24[(y24["mo"] >= 3) & (y24["mo"] <= 9)]["amt"].astype(float).mean()
    )
    got = df[(df["retailer_id"] == 1) & (df["deduction_year"] == 2024)]["spike_index"].iloc[0]
    assert got == pytest.approx(expected)
    assert df["spike_index"].median() >= 1.5
    assert df["promo_dispute_rate"].max() <= 0.15


def test_10_recoverable_dollars_match_independent_computation(bcon):
    df = run(bcon, "10")
    assert len(df) == 9
    stats = (
        bcon.execute(
            "select d.reason_code, count(*) filter (where x.outcome in ('won', 'partial')) * 1.0 / "
            "count(*) filter (where x.outcome in ('won', 'partial', 'lost')) as win_rate, "
            "sum(x.recovered_amount) filter (where x.outcome in ('won', 'partial')) / "
            "sum(d.amount) filter (where x.outcome in ('won', 'partial')) as ratio "
            "from raw.deductions d join raw.disputes x using (deduction_id) group by 1"
        )
        .df()
        .set_index("reason_code")
    )
    cands = bcon.execute(
        f"select reason_code, amount from raw.deductions where deduction_id not in (select deduction_id from raw.disputes) "
        f"and status in ('open', 'written_off') and {AS_OF} - deduction_date <= 180"
    ).df()
    cands["amount"] = cands["amount"].astype(float)
    expected_history = sum(
        r.amount * stats.loc[r.reason_code, "win_rate"] * stats.loc[r.reason_code, "ratio"]
        for r in cands.itertuples()
    )
    row = df[(df["window_days"] == 180) & (df["scenario"] == "base")].iloc[0]
    assert row["recoverable_amount"] == pytest.approx(float(expected_history) * 0.75)
    assert row["candidate_deductions"] == len(cands)
    assert (
        df.groupby("window_days")["recoverable_amount"]
        .apply(lambda s: s.is_monotonic_increasing)
        .all()
    )


def test_no_unannotated_file_reads_raw():
    for path in FILES:
        assert not re.search(r"\b(from|join)\s+raw", path.read_text(), re.I), path.name
