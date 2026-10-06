"""Audit 2: the null dataset, the 20-seed sweep, and the dispute-selection-bias mode.

Detection ranges are the generator tests' ranges, applied to many seeds. The null dataset has NO planted effect, so
a detector that fires on it is producing false positives.
"""

import json

import numpy as np
import pytest

from data_gen import measures as m
from data_gen.config import Config
from data_gen.generate import generate, generate_with_truth, table_hashes

from .helpers import REPO_ROOT

SEEDS = range(1, 21)


def detected(t) -> dict[str, bool]:
    shortage_dispute, shortage_win = m.dispute_stats(t, "shortage")
    _, other_win = m.dispute_stats(t, "shortage", invert=True)
    growth, q4 = m.revenue_growth_and_seasonality(t)
    slopes = m.lag_slopes(t)
    return {
        "p1": m.fine_ratio_a_vs_peers(t) >= 2.2
        and m.fine_top2_share(t, attributed_only=True)[0] >= 0.55,
        "p2": m.promo_spike_ratio(t) >= 1.5 and m.promo_dispute_rate(t) <= 0.15,
        "p3": 0.65 <= shortage_win <= 0.92
        and shortage_win - other_win >= 0.08
        and shortage_dispute < 0.30,
        "p4": slopes[2] >= 1.0 and slopes.drop(2).abs().max() <= 1.0 and m.lag_rise_b(t) >= 5,
        "p5": 0.04 <= growth <= 0.12 and 1.1 <= q4 <= 1.5,
        "p7": m.anomaly_cell(t) >= 2.0,
    }


@pytest.fixture(scope="module")
def sweep():
    planted = [detected(generate(Config(seed=s))) for s in SEEDS]
    null = [detected(generate(Config(seed=s, planted=False))) for s in SEEDS]
    return planted, null


@pytest.mark.parametrize("pattern", ["p1", "p2", "p3", "p4", "p5", "p7"])
def test_planted_patterns_are_found_on_at_least_19_of_20_seeds(sweep, pattern):
    planted, _ = sweep
    assert sum(run[pattern] for run in planted) >= 19


@pytest.mark.parametrize("pattern", ["p1", "p2", "p3", "p4", "p5", "p7"])
def test_the_same_detectors_stay_quiet_on_null_data_at_least_19_of_20_seeds(sweep, pattern):
    _, null = sweep
    assert sum(run[pattern] for run in null) <= 1, f"{pattern} fires on data with no planted effect"


def test_null_dataset_has_the_same_volume_and_no_seasonality_or_growth():
    planted, null = generate(Config(seed=7)), generate(Config(seed=7, planted=False))
    assert 0.9 <= len(null["invoices"]) / len(planted["invoices"]) <= 1.1
    # Deductions run ~10% lower in the null data on purpose: the planted fine excess and Q4 promo claims are gone.
    assert 0.85 <= len(null["deductions"]) / len(planted["deductions"]) <= 1.1
    growth, q4 = m.revenue_growth_and_seasonality(null)
    assert abs(growth) < 0.03 and 0.93 <= q4 <= 1.07


def test_null_mode_is_deterministic_and_differs_from_planted():
    cfg = Config(seed=3, revenue_scale=0.05, planted=False)
    assert table_hashes(generate(cfg)) == table_hashes(generate(cfg))
    assert (
        table_hashes(generate(cfg))["deductions"]
        != table_hashes(generate(Config(seed=3, revenue_scale=0.05)))["deductions"]
    )


def test_bias_mode_off_leaves_the_default_dataset_unchanged_and_bias_changes_only_disputes():
    base = Config(seed=5, revenue_scale=0.05)
    off = generate(base)
    zero = generate(Config(seed=5, revenue_scale=0.05, dispute_bias=0.0))
    assert table_hashes(off)["invoices"] == table_hashes(zero)["invoices"]
    assert (
        table_hashes(off)["disputes"] != table_hashes(zero)["disputes"]
    )  # heterogeneity changes outcomes


def test_selection_bias_raises_the_win_rate_of_disputed_deductions_but_not_of_the_population():
    t_off, truth_off = generate_with_truth(Config(seed=11, dispute_bias=0.0))
    t_bias, truth_bias = generate_with_truth(Config(seed=11, dispute_bias=1.5))

    def disputed(t):
        return t["deductions"]["deduction_id"].isin(t["disputes"]["deduction_id"])

    def mean_true(t, truth, mask):
        ids = t["deductions"].loc[mask, "deduction_id"]
        return truth.set_index("deduction_id").loc[ids, "p_win_true"].mean()

    gap_off = mean_true(t_off, truth_off, disputed(t_off)) - mean_true(
        t_off, truth_off, ~disputed(t_off)
    )
    gap_bias = mean_true(t_bias, truth_bias, disputed(t_bias)) - mean_true(
        t_bias, truth_bias, ~disputed(t_bias)
    )
    assert abs(gap_off) < 0.02  # no selection: disputed and undisputed are equally winnable
    assert gap_bias > 0.05  # selection: the disputed ones are clearly more winnable than the rest
    assert (
        abs(truth_off["p_win_true"].mean() - truth_bias["p_win_true"].mean()) < 0.01
    )  # population unchanged


def test_committed_audit_evidence_is_consistent_with_the_claims_made_about_it():
    summary = json.loads((REPO_ROOT / "docs" / "audit" / "summary.json").read_text())
    null = summary["null_after"]
    assert null["runs"] == 20 and null["p3_runs_with_a_flag"] == 0 and null["p1_flagged_runs"] == 0
    assert (
        null["anomalies_mean"] < 6
        and null["p4_detected_runs"] == 0
        and null["p2_detected_runs"] == 0
    )
    assert (
        summary["null_before"]["p3_runs_with_a_flag"] >= 15
    )  # the false-positive problem that was fixed
    assert all(r["detected"] >= 19 for r in summary["planted_after"])
    factors = {row["bias"]: row["implied_realization_factor"] for row in summary["bias"]}
    assert factors["0"] > 0.95 > factors["0.5"] > factors["1"] > factors["1.5"] > 0.7
    assert np.isclose(factors["off"], factors["0"], atol=0.05)
