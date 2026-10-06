"""Audit 2: the full pipeline (generator -> dbt -> analysis SQL) on NULL datasets must not "find" anything.

Two seeds are run here as a regression guard; the 20-seed evidence is in docs/audit/null_after.json.
"""

import duckdb
import pytest

from data_gen.config import Config
from data_gen.load import build_warehouse

from .helpers import REPO_ROOT, run_dbt

ANALYSIS = REPO_ROOT / "sql" / "analysis"


@pytest.fixture(scope="module", params=[1, 2])
def null_con(request, tmp_path_factory):
    path = tmp_path_factory.mktemp(f"null{request.param}") / "warehouse.duckdb"
    build_warehouse(path, Config(seed=request.param, planted=False))
    assert run_dbt("run", warehouse=path, target_path=path.parent / "target").returncode == 0
    con = duckdb.connect(str(path), read_only=True)
    yield con
    con.close()


def analysis(con, prefix):
    return con.execute(next(ANALYSIS.glob(f"{prefix}_*.sql")).read_text()).df()


def test_no_reason_is_called_under_invested_on_null_data(null_con):
    assert not analysis(null_con, "06")["under_invested"].any()


def test_no_fine_outlier_is_called_on_null_data(null_con):
    a03 = analysis(null_con, "03")
    assert not a03["is_fine_outlier"].any()
    assert a03["ratio_to_peer_median"].iloc[0] < 2.0


def test_anomaly_alarms_are_rare_on_null_data(null_con):
    # ~1512 scored cells; |z| >= 4.5 should fire on well under 0.5% of them by chance (<= 7 cells).
    assert len(analysis(null_con, "07")) <= 7


def test_no_promo_spike_and_no_lag_drift_on_null_data(null_con):
    a09 = analysis(null_con, "09")
    assert a09["spike_index"].median() < 1.5
    a08 = analysis(null_con, "08")
    latest = a08[a08["invoice_month"] == a08["invoice_month"].max()]
    assert latest["change_vs_6m_ago"].max() < 5


def test_no_filing_lag_effect_on_null_data(null_con):
    cohorts = analysis(null_con, "05").dropna(subset=["win_rate"])
    assert (cohorts["win_rate"].max() - cohorts["win_rate"].min()) < 0.15
