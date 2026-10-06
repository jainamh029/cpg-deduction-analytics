"""Audit 6: dashboard smoke tests (headless Streamlit AppTest) across filter scenarios, plus SQL-injection safety.

Every page runs under: default filters, a single retailer, a single reason, a selection that has no data, and all
filters combined. No unhandled exceptions; empty selections show an explicit message; displayed numbers equal the
data-function (SQL) output for the same filters.
"""

import datetime as dt

import duckdb
import pytest
from streamlit.testing.v1 import AppTest

from dashboard import data
from dashboard.ui import money, pct

from .helpers import REPO_ROOT

PAGES = ["sales", "ops", "cfo"]


@pytest.fixture(scope="module")
def env(built_warehouse, forecast_results):
    con = duckdb.connect(str(built_warehouse), read_only=True)
    names = data.retailers(con).set_index("retailer_name")["retailer_id"].to_dict()
    # A day on which the smallest retailer (L) has no invoices at all -> a genuinely empty selection.
    empty_day = con.execute(
        "select d::date from generate_series(date '2023-01-01', date '2025-12-31', interval 1 day) t(d) "
        "where not exists (select 1 from marts.fct_invoices i where i.retailer_id = 12 and i.invoice_date = t.d::date) limit 1"
    ).fetchone()[0]
    yield {
        "con": con,
        "names": names,
        "empty_day": empty_day,
        "warehouse": built_warehouse,
        "forecast": forecast_results,
    }
    con.close()


def scenarios(env):
    day = env["empty_day"]
    return {
        "default": {},
        "single_retailer": {"retailers": ["Retailer C"]},
        "single_reason": {"reasons": ["shortage"]},
        "no_data": {"retailers": ["Retailer L"], "reasons": ["damage"], "dates": (day, day)},
        "combined": {"retailers": ["Retailer B", "Retailer E"], "reasons": ["promo", "pricing"], "dates": (dt.date(2024, 3, 1), dt.date(2024, 9, 30))},
    }  # fmt: skip


def run_page(env, monkeypatch, page, scenario):
    monkeypatch.setenv("WAREHOUSE_PATH", str(env["warehouse"]))
    monkeypatch.setenv("FORECAST_DIR", str(env["forecast"]))
    app = AppTest.from_file(str(REPO_ROOT / "dashboard" / "app.py"), default_timeout=90)
    app.run()
    app.sidebar.radio[0].set_value(page)
    if "retailers" in scenario:
        app.sidebar.multiselect[0].set_value(scenario["retailers"])
    if "reasons" in scenario:
        app.sidebar.multiselect[1].set_value(scenario["reasons"])
    if "dates" in scenario:
        app.sidebar.date_input[0].set_value(scenario["dates"])
    app.run()
    return app


def filters_for(env, scenario) -> data.Filters:
    con = env["con"]
    ids = tuple(env["names"][n] for n in scenario.get("retailers", env["names"]))
    lo, hi = data.invoice_date_range(con)
    start, end = scenario.get("dates", (lo, hi))
    return data.Filters(ids, start, end, tuple(scenario.get("reasons", data.reason_codes(con))))


@pytest.mark.parametrize("page", PAGES)
@pytest.mark.parametrize(
    "name", ["default", "single_retailer", "single_reason", "no_data", "combined"]
)
def test_page_runs_without_exceptions_under_every_scenario(env, monkeypatch, page, name):
    app = run_page(env, monkeypatch, page, scenarios(env)[name])
    assert not app.exception, [e.value for e in app.exception]
    assert app.metric, "page rendered no KPIs"


@pytest.mark.parametrize("page", PAGES)
def test_empty_selection_shows_an_explicit_message(env, monkeypatch, page):
    app = run_page(env, monkeypatch, page, scenarios(env)["no_data"])
    assert not app.exception
    assert any("No " in i.value or "Nothing" in i.value for i in app.info), [
        i.value for i in app.info
    ]


@pytest.mark.parametrize("name", ["single_retailer", "single_reason", "combined"])
def test_displayed_numbers_equal_data_function_output(env, monkeypatch, name):
    scenario = scenarios(env)[name]
    f = filters_for(env, scenario)
    con = env["con"]
    shown = {m.label: m.value for m in run_page(env, monkeypatch, "sales", scenario).metric}
    kpi = data.sales_kpis(con, f)
    assert shown["Gross invoiced"] == money(kpi["gross_amount"])
    assert shown["Deduction rate"] == pct(kpi["deduction_rate"])
    shown = {m.label: m.value for m in run_page(env, monkeypatch, "ops", scenario).metric}
    ops = data.ops_kpis(con, f)
    assert shown["Open deduction balance"] == money(ops["open_balance"])
    assert shown["Open items"] == f"{int(ops['open_items']):,}"
    shown = {m.label: m.value for m in run_page(env, monkeypatch, "cfo", scenario).metric}
    assert shown["Cash tied up in open deductions"] == money(data.cash_kpis(con, f)["cash_tied_up"])


def test_incomplete_date_range_warns_instead_of_crashing(env, monkeypatch):
    monkeypatch.setenv("WAREHOUSE_PATH", str(env["warehouse"]))
    monkeypatch.setenv("FORECAST_DIR", str(env["forecast"]))
    app = AppTest.from_file(str(REPO_ROOT / "dashboard" / "app.py"), default_timeout=90)
    app.run()
    app.sidebar.date_input[0].set_value((dt.date(2024, 1, 1),))
    app.run()
    assert not app.exception
    assert any("Choose at least one" in w.value for w in app.warning)


class SqlSpy:
    """Wraps a DuckDB connection and records every SQL string sent to it."""

    def __init__(self, con):
        self._con, self.sql = con, []

    def execute(self, sql, params=None):
        self.sql.append(sql)
        return self._con.execute(sql) if params is None else self._con.execute(sql, params)

    def __getattr__(self, name):
        return getattr(self._con, name)


def test_filter_values_are_bound_parameters_never_part_of_the_sql_text(env):
    marker = "x'); drop table marts.fct_deductions; --"
    spy = SqlSpy(env["con"])
    lo, hi = data.invoice_date_range(env["con"])
    hostile = data.Filters((1, 2), lo, hi, (marker,))
    before = env["con"].execute("select count(*) from marts.fct_deductions").fetchone()[0]
    for fn in (data.sales_kpis, data.retailer_scorecard, data.monthly_rate_by_retailer, data.trend_halves, data.ops_kpis,
               data.aging_by_reason, data.reason_mix, data.filing_cohorts, data.worklist, data.cash_kpis,
               data.recoverable_grid, data.open_balance_by_retailer, data.deduction_history):  # fmt: skip
        result = fn(spy, hostile)
        assert result is not None
    assert spy.sql and all(marker not in s for s in spy.sql)
    assert env["con"].execute("select count(*) from marts.fct_deductions").fetchone()[0] == before
