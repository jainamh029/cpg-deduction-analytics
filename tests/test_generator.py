"""Generator tests: determinism, scale, reconciliation, and planted-pattern TOLERANCE RANGES.

Ranges are deliberately ranges, not exact values: the generator adds noise on purpose.
"""

import numpy as np
import pytest

from data_gen import measures as m
from data_gen.config import PROBLEM_SKUS, Config
from data_gen.generate import generate, table_hashes


def test_same_seed_gives_identical_tables():
    cfg = Config(revenue_scale=0.03)
    assert table_hashes(generate(cfg)) == table_hashes(generate(cfg))


def test_different_seed_changes_tables():
    a = table_hashes(generate(Config(revenue_scale=0.03, seed=1)))
    b = table_hashes(generate(Config(revenue_scale=0.03, seed=2)))
    assert all(a[t] != b[t] for t in ("skus", "invoices", "deductions"))


def test_scale_and_shape(tables):
    assert len(tables["retailers"]) == 12
    assert len(tables["skus"]) == 300
    assert 300_000 <= len(tables["invoice_lines"]) <= 520_000
    assert len(tables["deductions"]) >= 30_000
    inv = tables["invoices"]
    assert inv["invoice_date"].min().date() == Config().start_date
    assert inv["invoice_date"].max().date() <= Config().end_date
    assert inv["invoice_date"].dt.to_period("M").nunique() == 36
    yearly = inv.groupby(inv["invoice_date"].dt.year)["gross_amount"].sum()
    assert 135e6 <= yearly[2024] <= 165e6  # ~$150M/yr scale
    assert 400e6 <= inv["gross_amount"].sum() <= 520e6


def test_invoice_gross_equals_sum_of_lines(tables):
    lines = tables["invoice_lines"]
    cents = (lines["qty"] * np.round(lines["unit_price"] * 100)).groupby(lines["invoice_id"]).sum()
    gross_cents = np.round(tables["invoices"].set_index("invoice_id")["gross_amount"] * 100)
    assert (cents == gross_cents).all()


def test_payments_plus_deductions_do_not_exceed_gross(tables):
    paid = tables["payments"].groupby("invoice_id")["paid_amount"].sum()
    ded = tables["deductions"].groupby("invoice_id")["amount"].sum()
    total = paid.add(ded, fill_value=0)
    gross = tables["invoices"].set_index("invoice_id")["gross_amount"]
    assert (total <= gross.reindex(total.index) + 0.005).all()


def test_sku_null_rate_in_documented_range(tables):
    assert 0.35 <= tables["deductions"]["sku_id"].isna().mean() <= 0.60


def test_pattern1_retailer_a_compliance_fines(tables):
    assert 2.2 <= m.fine_ratio_a_vs_peers(tables) <= 4.0
    attributed, top2 = m.fine_top2_share(tables, attributed_only=True)
    overall, _ = m.fine_top2_share(tables, attributed_only=False)
    assert top2 == set(PROBLEM_SKUS)
    assert attributed >= 0.55
    assert overall >= 0.40  # still detectable after counting unattributed fines
    assert overall < attributed  # unattributed fines dilute the concentration


def test_pattern2_promo_spike_after_q4_rarely_disputed(tables):
    assert m.promo_spike_ratio(tables) >= 1.5
    assert m.promo_dispute_rate(tables) <= 0.15


def test_pattern3_shortage_high_win_low_dispute(tables):
    dispute_rate, win_rate = m.dispute_stats(tables, "shortage")
    other_dispute_rate, other_win_rate = m.dispute_stats(tables, "shortage", invert=True)
    assert 0.65 <= win_rate <= 0.92
    assert 0.08 <= dispute_rate <= 0.30
    assert win_rate - other_win_rate >= 0.08
    assert dispute_rate < other_dispute_rate


def test_pattern4_retailer_b_payment_lag_drifts_up(tables):
    slopes = m.lag_slopes(tables)
    assert slopes[2] >= 1.0  # days per month
    assert slopes.drop(2).abs().max() <= 1.0
    assert m.lag_rise_b(tables) >= 5


def test_pattern5_growth_and_seasonality(tables):
    growth, q4_ratio = m.revenue_growth_and_seasonality(tables)
    assert 0.04 <= growth <= 0.12
    assert 1.1 <= q4_ratio <= 1.5


def test_pattern7_one_off_shortage_anomaly(tables):
    assert m.anomaly_cell(tables) >= 2.0


@pytest.mark.parametrize("table", ["deductions", "disputes", "payments"])
def test_no_activity_after_as_of_date(tables, table):
    col = {"deductions": "deduction_date", "disputes": "filed_date", "payments": "paid_date"}[table]
    assert tables[table][col].max().date() <= Config().end_date
