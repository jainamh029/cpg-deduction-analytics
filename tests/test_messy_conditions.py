"""Audit 3: metric logic under messy real-world conditions.

Fixture: tests/fixtures/messy_fixture.sql, loaded into the UNCONSTRAINED raw_dirty schema, models built with
`dbt run` (no data tests: the data is dirty on purpose), as-of date 2024-07-31. Every expected value is hand
arithmetic written next to the assertion.

Totals used below. Deductions D1..D11 = 100, 700, 50, 50, 200, 100, 80, 60, 40, 40, 30 -> 1450 (D11 is orphaned,
invoice 999, so invoices carry 1420). Disputes X1..X8 recover 0, 120, 120, 0, 80, 0, 0, 25 -> 345.
"""

import datetime as dt

import duckdb
import pandas as pd
import pytest

from data_gen.load import DDL_FILE, LOAD_ORDER
from warehouse.validate import findings

from .helpers import REPO_ROOT, run_dbt

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "messy_fixture.sql"
ANALYSIS = REPO_ROOT / "sql" / "analysis"
D = dt.date


@pytest.fixture(scope="module")
def mx(tmp_path_factory):
    path = tmp_path_factory.mktemp("messy") / "warehouse.duckdb"  # name must stay `warehouse`
    con = duckdb.connect(str(path))
    con.execute(DDL_FILE.read_text())
    con.execute("create schema raw_dirty")
    for table in LOAD_ORDER:
        con.execute(f"create table raw_dirty.{table} as select * from raw.{table} limit 0")
    con.execute(FIXTURE.read_text())
    con.close()
    result = run_dbt(
        "run", "--vars", "{as_of_date: '2024-07-31', raw_schema: raw_dirty}",
        warehouse=path, target_path=path.parent / "target",
    )  # fmt: skip
    assert result.returncode == 0, result.stdout[-3000:]
    connection = duckdb.connect(str(path), read_only=True)
    yield connection
    connection.close()


def one(con, sql):
    return con.execute(sql).fetchone()[0]


def rows(con, sql):
    return con.execute(sql).fetchall()


def analysis(con, prefix):
    df = con.execute(next(ANALYSIS.glob(f"{prefix}_*.sql")).read_text()).df()
    df["invoice_month"] = pd.to_datetime(df["invoice_month"])
    return df


def test_validator_flags_exactly_the_messy_conditions(mx):
    assert findings(mx, "raw_dirty") == {
        "fk_deductions_invoice": 1,  # D11 -> invoice 999
        "fk_disputes_deduction": 1,  # X8 -> deduction 999
        "recon_overpaid_invoice": 1,  # I2: 0 paid + 700 deducted > 500 gross
        "duplicate_deductions": 1,  # D4 repeats D3 (same invoice, reason, sku, date, amount)
        "multiple_disputes_per_deduction": 2,  # D5 has 3 disputes -> 2 extra
        "recon_recovered_total_exceeds_deduction": 1,  # D5: 0 + 120 + 120 = 240 > 200
        "date_deduction_before_invoice": 1,  # D9 dated 2024-03-25, invoice 2024-03-31
        "date_dispute_order": 1,  # X7 resolved 2024-05-05 before filed 2024-05-10
    }


def test_orphans_are_retained_not_silently_dropped_by_the_marts(mx):
    # Kills LEFT->INNER mutations in fct_deductions and fct_disputes (clean data never exercises them).
    assert one(mx, "select count(*) from marts.fct_deductions") == 11
    assert one(mx, "select sum(amount) from marts.fct_deductions") == 1450
    orphan = rows(mx, "select invoice_date from marts.fct_deductions where deduction_id = 11")
    assert orphan == [(None,)]
    assert one(mx, "select count(*) from marts.fct_disputes") == 8
    assert one(mx, "select sum(recovered_amount) from marts.fct_disputes") == 345
    # Invoices only see deductions that have an invoice: 1450 - 30 (orphan D11) = 1420.
    assert one(mx, "select sum(deduction_amount) from marts.fct_invoices") == 1420


def test_recoveries_on_a_deduction_are_capped_at_its_amount(mx):
    # D5 (200): lost 0 + partial 120 + partial 120 = 240 raw, capped to 200.
    assert (
        one(mx, "select recovered_amount from marts.fct_deductions where deduction_id = 5") == 200
    )
    # Reconciliation identity: fct_disputes 345 - 40 (D5 cap) - 25 (orphan dispute X8) = 280 on deductions.
    assert one(mx, "select sum(recovered_amount) from marts.fct_deductions") == 345 - 40 - 25
    # Net revenue for I4 = 600 - 200 + 200 = 600, never above gross.
    assert (
        one(mx, "select net_revenue from metrics.m_invoice_detail where invoice_id = 4")
        == 600 - 200 + 200
    )


def test_multiple_and_refiled_disputes_collapse_to_one_deduction_row(mx):
    # D5 has X1 (lost), X2 (partial), X3 (partial): first filing 05-01, last resolution 06-25, latest outcome.
    got = rows(
        mx,
        "select dispute_id, filed_date, resolved_date, dispute_outcome from marts.fct_deductions where deduction_id = 5",
    )
    assert got == [(1, D(2024, 5, 1), D(2024, 6, 25), "partial")]
    # Days to resolve = May 1 -> Jun 25 = 30 (May has 31 days: 31 - 1) + 25 = 55.
    row = rows(
        mx,
        "select days_to_resolve, is_win, is_resolved, validity_class from metrics.m_deduction_detail where deduction_id = 5",
    )
    assert row == [(55, True, True, "invalid")]


def test_partial_payments_use_the_final_payment_date_and_leave_a_silent_balance(mx):
    # I1: 400 on Feb 20 + 400 on Apr 5. Days to pay (final payment) = Jan 31 -> Apr 5 = 29 + 31 + 5 = 65.
    # Days past due: due Mar 1 -> Apr 5 = 31 + 4 = 35. The whole 800 is weighted at 65 days, although half
    # was paid at day 20 (a definition choice, documented in METRICS.md).
    row = rows(
        mx,
        "select payments_amount, days_to_pay, days_past_due from metrics.m_invoice_detail where invoice_id = 1",
    )
    assert row == [(800, 65, 35)]
    # Unreported balance: 1000 gross - 800 paid - 100 deducted = 100 sits in no metric (no receivable-balance metric).
    assert (
        one(
            mx,
            "select gross_amount - payments_amount - deduction_amount from marts.fct_invoices where invoice_id = 1",
        )
        == 100
    )


def test_deduction_larger_than_the_invoice_goes_negative_and_is_flagged(mx):
    # I2: 500 gross, 700 deducted: net revenue 500 - 700 + 0 = -200 and a 700/500 = 140% deduction rate.
    assert one(mx, "select net_revenue from metrics.m_invoice_detail where invoice_id = 2") == -200
    rate = one(
        mx,
        "select deduction_rate from metrics.m_retailer_month where retailer_id = 1 and invoice_month = '2024-02-01'",
    )
    assert rate == pytest.approx(700 / 500)


def test_duplicate_deductions_are_counted_twice_and_only_the_validator_notices(mx):
    # D3 and D4 are identical: I3 shows 50 + 50 = 100 deducted (not 50). The pipeline does not dedupe.
    assert one(mx, "select deduction_amount from marts.fct_invoices where invoice_id = 3") == 100
    assert one(mx, "select deduction_count from marts.fct_invoices where invoice_id = 3") == 2


def test_win_rate_excludes_pending_and_days_to_resolve_is_biased_low_by_censoring(mx):
    # Resolved: D5 (partial win), D7 (won), D8 (lost). Pending: D1, D6. Win rate = 2 / 3, not 2 / 5.
    sql = "select metrics.dispute_win_rate(count(*) filter (where is_win), count(*) filter (where is_resolved)) from metrics.m_deduction_detail"
    assert one(mx, sql) == pytest.approx(2 / 3)
    assert one(mx, sql) != pytest.approx(2 / 5)
    # Days to resolve: D5 55, D7 11 (May 25 -> Jun 5 = 6 + 5), D8 -5 (bad data, see next test).
    assert one(mx, "select count(days_to_resolve) from metrics.m_deduction_detail") == 3
    # Censoring: the two pending disputes have already been open longer than ANY resolved one.
    # X6 filed Feb 20 -> Jul 31 = 151 + 11 = 162 days; X4 filed Jun 1 -> Jul 31 = 30 + 30 = 60 days.
    ages = rows(
        mx,
        "select date_diff('day', filed_date, date '2024-07-31') from metrics.m_deduction_detail where dispute_outcome = 'pending' order by 1",
    )
    assert ages == [(60,), (162,)]
    resolved_mean = one(mx, "select avg(days_to_resolve) from metrics.m_deduction_detail")
    assert resolved_mean == pytest.approx((55 + 11 - 5) / 3)  # 20.33 (resolved only)
    lower_bound_including_pending = (
        55 + 11 - 5 + 162 + 60
    ) / 5  # 56.6: pending counted at age so far
    assert resolved_mean < lower_bound_including_pending - 30


def test_resolved_before_filed_gives_a_negative_duration_so_the_validation_gate_is_the_only_guard(
    mx,
):
    # Characterization: X7 (filed May 10, resolved May 5) -> -5 days flows into the metric unguarded.
    assert (
        one(mx, "select days_to_resolve from metrics.m_deduction_detail where deduction_id = 8")
        == -5
    )
    assert findings(mx, "raw_dirty")["date_dispute_order"] == 1


def test_cohort_basis_and_deduction_date_basis_differ_and_recent_months_are_flagged(mx):
    # R1, invoice month March (I6, Mar 31): deductions D8 60 (dated Apr 30!) + D9 40 -> cohort basis 100.
    cohort = one(
        mx,
        "select deduction_amount from metrics.m_retailer_month where retailer_id = 1 and invoice_month = '2024-03-01'",
    )
    assert cohort == 100
    # Same retailer, deduction-date basis for March: only D9 (dated Mar 25) = 40; D8 lands in April.
    by_date = rows(
        mx,
        "select deduction_month, sum(deduction_amount) from metrics.m_deductions_monthly where retailer_id = 1 and reason_code = 'other' group by 1 order by 1",
    )
    # (The orphaned D11 is retailer 1, 'other', dated May 1: 30 in May.)
    assert by_date == [(D(2024, 3, 1), 40), (D(2024, 4, 1), 60), (D(2024, 5, 1), 30)]
    # Maturity: month + 4 months <= 2024-07-31 -> Jan, Feb, Mar mature; R1 April (I4) and R2 May (I5) are not.
    flags = rows(
        mx,
        "select retailer_id, invoice_month, is_mature_month from metrics.m_retailer_month order by 1, 2",
    )
    assert flags == [
        (1, D(2024, 1, 1), True), (1, D(2024, 2, 1), True), (1, D(2024, 3, 1), True), (1, D(2024, 4, 1), False),
        (2, D(2024, 1, 1), True), (2, D(2024, 3, 1), True), (2, D(2024, 5, 1), False),
    ]  # fmt: skip


def test_month_end_dates_land_in_the_right_month_and_burn_in_follows_the_first_invoice(mx):
    # I1 is dated Jan 31 -> invoice month January. D8 is dated Apr 30 -> deduction month April.
    assert one(mx, "select invoice_month from marts.fct_invoices where invoice_id = 1") == D(
        2024, 1, 1
    )
    assert one(mx, "select deduction_month from marts.fct_deductions where deduction_id = 8") == D(
        2024, 4, 1
    )
    # First invoice is Jan 10 (I7): deduction months before April are ramp-up. D9 (Mar) yes, D5 (Apr) no.
    got = dict(
        rows(
            mx,
            "select deduction_id, is_burn_in_month from metrics.m_deduction_detail where deduction_id in (5, 9)",
        )
    )
    assert got == {5: False, 9: True}


def test_zero_and_null_denominators_return_null_and_inactive_months_have_no_row(mx):
    for expr in ("metrics.deduction_rate(5, 0)", "metrics.deduction_rate(NULL, 5)", "metrics.dispute_win_rate(0, 0)",
                 "metrics.recovery_rate(0, 0)", "metrics.invalid_share(0, 0)", "metrics.dispute_rate(1, 0)"):  # fmt: skip
        assert one(mx, f"select {expr}") is None, expr
    # R2 has no invoices in February: no row at all (the analyses scaffold the calendar to cope).
    assert (
        one(
            mx,
            "select count(*) from metrics.m_retailer_month where retailer_id = 2 and invoice_month = '2024-02-01'",
        )
        == 0
    )


def test_analysis_02_lag_means_previous_calendar_month_across_a_gap(mx):
    df = analysis(mx, "02").set_index(["retailer_id", "invoice_month"])
    ts = pd.Timestamp
    mar = lambda r: df.loc[(r, ts(2024, 3, 1))]  # noqa: E731
    # R2: Jan 40/400 = 0.10, Feb no invoices (NULL), Mar 100/2000 = 0.05. The previous calendar month of March is
    # February, which has no rate, so mom_change is NULL (a row-based LAG would wrongly return January: 0.05 - 0.10).
    assert (
        df.loc[(2, ts(2024, 2, 1)), "deduction_rate"]
        != df.loc[(2, ts(2024, 2, 1)), "deduction_rate"]
    )  # NaN
    assert mar(2)["mom_change"] != mar(2)["mom_change"]
    assert mar(2)["deduction_rate"] == pytest.approx(100 / 2000)
    # Rolling 3-month rate for R2 in March: (40 + 0 + 100) / (400 + 0 + 2000) = 140 / 2400.
    assert mar(2)["rate_3m"] == pytest.approx(140 / 2400)
    # R1: Jan 100/1000 = 0.1, Feb 700/500 = 1.4, Mar 100/800 = 0.125; mom change in Mar = 0.125 - 1.4.
    assert mar(1)["deduction_rate"] == pytest.approx(0.125)
    assert mar(1)["mom_change"] == pytest.approx(0.125 - 1.4)
    assert mar(1)["rate_3m"] == pytest.approx((100 + 700 + 100) / (1000 + 500 + 800))  # 900 / 2300


def test_analysis_08_lag_across_a_gap_and_weighting(mx):
    df = analysis(mx, "08").set_index(["retailer_id", "invoice_month"])
    ts = pd.Timestamp
    # R2 Jan: I7 paid on Feb 15, 36 days (Jan 10 -> Feb 10 = 31, + 5). R2 Mar: I3 paid Apr 10: 31 + 5 = 36 days.
    assert df.loc[(2, ts(2024, 1, 1)), "payment_lag_days"] == pytest.approx(36)
    assert df.loc[(2, ts(2024, 3, 1)), "payment_lag_days"] == pytest.approx(36)
    # February has no paid invoices for R2, so March's month-over-month change is NULL, not 36 - 36 = 0.
    assert df.loc[(2, ts(2024, 3, 1)), "mom_change"] != df.loc[(2, ts(2024, 3, 1)), "mom_change"]
    # R1 Jan: only I1 (800 paid at 65 days) -> 65. R1 Feb and Mar invoices are unpaid -> NULL.
    assert df.loc[(1, ts(2024, 1, 1)), "payment_lag_days"] == pytest.approx(65)
    assert (
        df.loc[(1, ts(2024, 2, 1)), "payment_lag_days"]
        != df.loc[(1, ts(2024, 2, 1)), "payment_lag_days"]
    )


def test_credit_memos_and_returns_are_not_representable(tmp_path):
    """Unsupported by design: negative gross or price is rejected, so returns/credit memos cannot be modelled."""
    con = duckdb.connect(str(tmp_path / "w.duckdb"))
    con.execute(DDL_FILE.read_text())
    con.execute("insert into raw.retailers values (1, 'R', 'grocery', 'National', 30)")
    with pytest.raises(duckdb.Error):
        con.execute("insert into raw.invoices values (1, 1, '2024-01-01', '2024-01-31', -100.00)")
    con.close()
