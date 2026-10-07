"""The static (GitHub Pages) dashboard reads cubes exported from the warehouse; their totals must equal the
SQL-backed dashboard functions for the same (default) filters, so the two dashboards cannot disagree."""

import pandas as pd
import pytest

from dashboard import data
from scripts.export_dashboard_data import export

from .test_dashboard import full_filters


@pytest.fixture(scope="module")
def cubes(built_warehouse, forecast_results):
    raw = export(built_warehouse, forecast_results)
    return {
        k: pd.DataFrame(v["rows"], columns=v["cols"])
        for k, v in raw.items()
        if isinstance(v, dict) and "rows" in v
    }, raw


def test_sales_totals_match(cubes, bcon):
    frames, _ = cubes
    kpi = data.sales_kpis(bcon, full_filters(bcon))
    assert frames["gross"]["gross"].sum() == pytest.approx(kpi["gross_amount"], abs=1)
    assert frames["cohort"]["amt"].sum() == pytest.approx(kpi["deduction_amount"], abs=1)
    assert frames["cohort"]["rec"].sum() == pytest.approx(kpi["recovered_amount"], abs=1)


def test_ops_totals_match(cubes, bcon):
    frames, _ = cubes
    ops = data.ops_kpis(bcon, full_filters(bcon))
    ded = frames["deductions"]
    assert ded["open_amt"].sum() == pytest.approx(ops["open_balance"], abs=1)
    assert ded["open_n"].sum() == ops["open_items"]
    assert frames["open"]["amt"].sum() == pytest.approx(ops["open_balance"], abs=1)
    assert ded["wins"].sum() / ded["resolved"].sum() == pytest.approx(ops["win_rate"])
    assert ded["disp"].sum() / ded["amt"].sum() == pytest.approx(ops["dispute_rate"], abs=1e-4)


def test_cfo_totals_match(cubes, bcon):
    frames, raw = cubes
    grid = data.recoverable_grid(bcon, full_filters(bcon)).set_index(["window_days", "scenario"])[
        "recoverable_amount"
    ]
    factors = dict(zip(frames["scenarios"]["scenario"], frames["scenarios"]["factor"], strict=True))
    cand = frames["candidates"]
    for window in raw["meta"]["windows"]:
        for scenario, factor in factors.items():
            assert cand[cand["w"] <= window]["exp"].sum() * factor == pytest.approx(
                grid[(window, scenario)], abs=2
            )
    cash = data.cash_kpis(bcon, full_filters(bcon))
    assert frames["deductions"]["amt"].sum() == pytest.approx(cash["deducted_amount"], abs=1)


def test_forecast_and_worklist_match(cubes, bcon, forecast_results):
    frames, raw = cubes
    fwd = data.forward_forecast(full_filters(bcon), forecast_results)
    assert frames["forecast"]["hw"].sum() == pytest.approx(fwd["holt_winters"].sum(), abs=2)
    work = data.worklist(bcon, full_filters(bcon))
    assert list(frames["worklist"]["id"][:10]) == list(work["deduction_id"][:10])
    assert len(frames["worklist"]) == raw["meta"]["worklist_rows"]


def test_export_is_small_enough_for_a_static_site(cubes):
    import json

    _, raw = cubes
    assert len(json.dumps(raw, separators=(",", ":"))) < 3_000_000
