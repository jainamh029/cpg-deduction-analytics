"""Phase 6: dashboard tests. Data functions match SQL/metric values, filters move results the right way,
every chart title states a takeaway, and the app runs on the built warehouse (Streamlit AppTest)."""

import json
import re
from datetime import date

import pytest
from streamlit.testing.v1 import AppTest

from dashboard import data
from dashboard.ui import money, pct

from .helpers import REPO_ROOT

FULL_START, FULL_END = date(2023, 1, 1), date(2025, 12, 31)


def full_filters(con, **overrides) -> data.Filters:
    base = {
        "retailer_ids": tuple(int(i) for i in data.retailers(con)["retailer_id"]),
        "start": FULL_START,
        "end": FULL_END,
        "reasons": tuple(data.reason_codes(con)),
    }
    return data.Filters(**{**base, **overrides})


def scalar(con, sql):
    return float(con.execute(sql).fetchone()[0])


def analysis(con, prefix):
    path = next((REPO_ROOT / "sql" / "analysis").glob(f"{prefix}_*.sql"))
    return con.execute(path.read_text()).df()


# ------------------------------------------------------------------ data functions vs independent SQL


def test_sales_kpis_match_raw_tables(bcon):
    kpi = data.sales_kpis(bcon, full_filters(bcon))
    gross = scalar(bcon, "select sum(gross_amount) from raw.invoices")
    ded = scalar(bcon, "select sum(amount) from raw.deductions")
    rec = scalar(bcon, "select sum(recovered_amount) from raw.disputes")
    assert kpi["gross_amount"] == pytest.approx(gross)
    assert kpi["deduction_rate"] == pytest.approx(ded / gross)
    assert kpi["net_revenue"] == pytest.approx(gross - ded + rec)
    assert kpi["recovery_rate"] == pytest.approx(rec / ded)


def test_filters_move_results_in_the_expected_direction(bcon):
    everything = data.sales_kpis(bcon, full_filters(bcon))
    one_retailer = data.sales_kpis(bcon, full_filters(bcon, retailer_ids=(1,)))
    assert one_retailer["gross_amount"] < everything["gross_amount"]
    assert one_retailer["gross_amount"] == pytest.approx(
        scalar(bcon, "select sum(gross_amount) from raw.invoices where retailer_id = 1")
    )
    shortage_only = data.sales_kpis(bcon, full_filters(bcon, reasons=("shortage",)))
    assert shortage_only["deduction_amount"] < everything["deduction_amount"]
    assert shortage_only["deduction_amount"] == pytest.approx(
        scalar(bcon, "select sum(d.amount) from raw.deductions d where d.reason_code = 'shortage'")
    )
    year = data.sales_kpis(bcon, full_filters(bcon, start=date(2024, 1, 1), end=date(2024, 12, 31)))
    assert year["gross_amount"] < everything["gross_amount"]
    assert year["gross_amount"] == pytest.approx(
        scalar(bcon, "select sum(gross_amount) from raw.invoices where year(invoice_date) = 2024")
    )
    assert data.sales_kpis(bcon, full_filters(bcon, retailer_ids=()))["gross_amount"] == 0


def test_scorecard_rates_match_retailer_level_raw_sql(bcon):
    score = data.retailer_scorecard(bcon, full_filters(bcon)).set_index("retailer_id")
    raw = (
        bcon.execute(
            "select i.retailer_id, sum(i.gross_amount) as gross, "
            "(select sum(amount) from raw.deductions d where d.retailer_id = i.retailer_id) as ded "
            "from raw.invoices i group by 1"
        )
        .df()
        .set_index("retailer_id")
    )
    for rid in (1, 5, 12):
        assert score.loc[rid, "deduction_rate"] == pytest.approx(
            float(raw.loc[rid, "ded"] / raw.loc[rid, "gross"])
        )
    assert score["deduction_rate"].is_monotonic_decreasing  # sorted worst first


def test_ops_page_numbers_equal_analysis_sql(bcon):
    f = full_filters(bcon)
    kpi = data.ops_kpis(bcon, f)
    raw_open = scalar(
        bcon, "select sum(amount) from raw.deductions where status in ('open', 'disputed')"
    )
    assert kpi["open_balance"] == pytest.approx(raw_open)
    assert kpi["open_balance"] == pytest.approx(analysis(bcon, "04")["open_balance"].sum())
    assert data.aging_by_reason(bcon, f)["open_balance"].sum() == pytest.approx(raw_open)
    mix = data.reason_mix(bcon, f).set_index("reason_code")
    sql06 = analysis(bcon, "06").set_index("reason_code")
    for reason in sql06.index:
        assert mix.loc[reason, "dispute_rate"] == pytest.approx(sql06.loc[reason, "dispute_rate"])
        assert mix.loc[reason, "win_rate"] == pytest.approx(sql06.loc[reason, "win_rate"])
    cohorts = data.filing_cohorts(bcon, f).set_index("filing_lag_bucket")
    sql05 = analysis(bcon, "05").set_index("filing_lag_bucket")
    assert list(cohorts["win_rate"]) == pytest.approx(list(sql05["win_rate"]))
    smaller = data.ops_kpis(bcon, full_filters(bcon, retailer_ids=(1,)))
    assert smaller["open_balance"] < kpi["open_balance"]


def test_worklist_is_open_undisputed_and_ranked(bcon):
    f = full_filters(bcon)
    work = data.worklist(bcon, f)
    assert 0 < len(work) <= data.WORKLIST_SIZE
    assert work["expected_recovery"].dropna().is_monotonic_decreasing
    ids = tuple(int(i) for i in work["deduction_id"])
    bad = bcon.execute(
        "select count(*) from raw.deductions d where d.deduction_id = any(?) "
        "and (d.status <> 'open' or d.deduction_id in (select deduction_id from raw.disputes))",
        [list(ids)],
    ).fetchone()[0]
    assert bad == 0
    only_a = data.worklist(bcon, full_filters(bcon, retailer_ids=(1,)))
    assert set(only_a["retailer_name"]) == {"Retailer A"}


def test_cfo_page_numbers_equal_analysis_10(bcon):
    grid = data.recoverable_grid(bcon, full_filters(bcon))
    sql10 = analysis(bcon, "10")
    assert list(grid["recoverable_amount"]) == pytest.approx(list(sql10["recoverable_amount"]))
    assert list(grid["window_days"]) == list(sql10["window_days"])
    narrower = data.recoverable_grid(bcon, full_filters(bcon, reasons=("shortage",)))
    assert (narrower["recoverable_amount"].to_numpy() < grid["recoverable_amount"].to_numpy()).all()
    cash = data.cash_kpis(bcon, full_filters(bcon))
    assert cash["cash_tied_up"] == pytest.approx(
        scalar(bcon, "select sum(amount) from raw.deductions where status in ('open', 'disputed')")
    )


def test_forecast_history_and_forward_data(bcon, forecast_results):
    f = full_filters(bcon)
    history = data.deduction_history(bcon, f)
    raw = scalar(
        bcon, "select sum(amount) from raw.deductions where deduction_date >= date '2023-04-01'"
    )
    assert history["amount"].sum() == pytest.approx(raw)
    forward = data.forward_forecast(f, forecast_results)
    one = data.forward_forecast(full_filters(bcon, retailer_ids=(1,)), forecast_results)
    assert len(forward) == len(one) == 3
    assert (one["holt_winters"].to_numpy() < forward["holt_winters"].to_numpy()).all()


# ------------------------------------------------------------------ the Streamlit app itself


@pytest.fixture
def app(monkeypatch, built_warehouse, forecast_results):
    monkeypatch.setenv("WAREHOUSE_PATH", str(built_warehouse))
    monkeypatch.setenv("FORECAST_DIR", str(forecast_results))
    test = AppTest.from_file(str(REPO_ROOT / "dashboard" / "app.py"), default_timeout=90)
    test.run()
    assert not test.exception
    return test


def chart_titles(app) -> list[str]:
    titles = []
    for element in app.main:
        if getattr(element, "type", "") in ("vega_lite_chart", "arrow_vega_lite_chart"):
            titles.append(" ".join(json.loads(element.proto.spec)["title"]["text"]))
    return titles


def metrics(app) -> dict[str, str]:
    return {m.label: m.value for m in app.metric}


@pytest.mark.parametrize(("page", "expected_charts"), [("sales", 3), ("ops", 3), ("cfo", 3)])
def test_every_page_runs_and_every_chart_title_states_a_takeaway(app, page, expected_charts):
    app.sidebar.radio[0].set_value(page).run()
    assert not app.exception
    titles = chart_titles(app)
    assert len(titles) == expected_charts
    for title in titles:
        assert re.search(r"\d", title), f"no number in takeaway title: {title}"
        assert len(title.split()) >= 8, f"title too short to be a takeaway: {title}"


def test_page_metrics_equal_data_functions(app, bcon):
    f = full_filters(bcon)
    kpi = data.sales_kpis(bcon, f)
    shown = metrics(app)
    assert shown["Gross invoiced"] == money(kpi["gross_amount"])
    assert shown["Deduction rate"] == pct(kpi["deduction_rate"])
    app.sidebar.radio[0].set_value("ops").run()
    assert metrics(app)["Open deduction balance"] == money(data.ops_kpis(bcon, f)["open_balance"])
    app.sidebar.radio[0].set_value("cfo").run()
    grid = data.recoverable_grid(bcon, f)
    base = grid[(grid["window_days"] == 180) & (grid["scenario"] == "base")][
        "recoverable_amount"
    ].iloc[0]
    assert metrics(app)["Recoverable (180-day window, base case)"] == money(base)


def test_retailer_filter_changes_the_page(app, bcon):
    before = metrics(app)["Gross invoiced"]
    app.sidebar.multiselect[0].set_value(["Retailer A"]).run()
    assert not app.exception
    after = metrics(app)["Gross invoiced"]
    assert after != before
    assert after == money(
        data.sales_kpis(bcon, full_filters(bcon, retailer_ids=(1,)))["gross_amount"]
    )


def test_empty_selection_shows_a_warning_not_a_crash(app):
    app.sidebar.multiselect[0].set_value([]).run()
    assert not app.exception
    assert any("Choose at least one" in w.value for w in app.warning)
