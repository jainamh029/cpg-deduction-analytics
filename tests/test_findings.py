"""Phase 8: the README is rendered from findings.json, its numbers are independently re-derived from RAW
tables, and the qualitative claims written in the template are true in the data."""

import json
import re

import pytest

from scripts.render_readme import FINDINGS, README, TEMPLATE, render
from scripts.verify_readme import independent_values, verify

from .helpers import REPO_ROOT


@pytest.fixture(scope="module")
def findings() -> dict:
    return json.loads(FINDINGS.read_text())


def test_findings_json_has_every_section(findings):
    for key in (
        "meta",
        "headline",
        "finding1",
        "finding2",
        "finding3",
        "also",
        "forecast",
        "data_quality",
    ):
        assert key in findings
    assert findings["meta"]["months"] == 36


def test_readme_is_exactly_the_rendering_of_template_and_findings(findings):
    assert README.read_text() == render(TEMPLATE.read_text(), findings)
    assert "{{" not in README.read_text()


def test_readme_numbers_match_independent_raw_table_sql(built_warehouse, forecast_results, capsys):
    failures = verify(built_warehouse, forecast_dir=forecast_results)
    assert failures == []
    assert "FAIL" not in capsys.readouterr().out


def test_at_least_five_numbers_are_independently_recomputed(built_warehouse, forecast_results):
    import duckdb

    con = duckdb.connect(str(built_warehouse), read_only=True)
    assert len(independent_values(con, forecast_results)) >= 5
    con.close()


def test_qualitative_claims_in_the_template_hold(findings):
    by_reason = findings["finding1"]["by_reason"]
    assert (
        max(by_reason, key=lambda r: by_reason[r]["win_rate"]) == "shortage"
    )  # "the highest of any reason"
    assert (
        min(by_reason, key=lambda r: by_reason[r]["dispute_rate"]) == "promo"
    )  # "promo is disputed even less"
    assert (
        findings["finding1"]["shortage_dispute_rate"]
        < findings["finding1"]["non_promo_peers_dispute_rate"]
    )
    assert (
        max(by_reason, key=lambda r: by_reason[r]["deduction_amount"]) == "promo"
    )  # "largest category"
    assert findings["finding3"]["promo_amount"] == pytest.approx(
        by_reason["promo"]["deduction_amount"]
    )
    assert (
        findings["finding2"]["top2_share_of_all"] < findings["finding2"]["top2_share_of_attributed"]
    )
    assert findings["also"]["lag_change_6m"] > 5 * max(
        findings["also"]["lag_runner_up_change_6m"], 0.1
    )
    assert findings["data_quality"]["clean_findings"] == {}
    assert sum(findings["data_quality"]["dirty_findings"].values()) == 12


def test_diagrams_cover_every_table_and_model():
    ddl = (REPO_ROOT / "warehouse" / "ddl.sql").read_text()
    tables = re.findall(r"create table raw\.(\w+)", ddl)
    erd = (REPO_ROOT / "docs" / "erd.mmd").read_text().lower()
    assert len(tables) == 8 and all(t in erd for t in tables)
    lineage = (REPO_ROOT / "docs" / "lineage.mmd").read_text()
    models = [p.stem for p in (REPO_ROOT / "models").rglob("*.sql")]
    assert len(models) >= 25 and all(m in lineage for m in models)


def test_metrics_doc_numbers_match_findings(findings):
    text = (REPO_ROOT / "docs" / "METRICS.md").read_text()
    dq, f2 = findings["data_quality"], findings["finding2"]
    assert f"{dq['sku_null_rate_count']:.1%}" in text
    assert f"{dq['sku_null_rate_amount']:.1%}" in text
    assert f"{f2['top2_share_of_attributed']:.1%}" in text
    assert f"{f2['top2_share_of_all']:.1%}" in text
    assert f"{f2['dilution_points']:.1f} points" in text
