"""Validator tests: clean load has ZERO findings; dirty load has exactly the injected ones."""

import duckdb
import pytest

from data_gen.dirty import EXPECTED_DIRTY_FINDINGS
from warehouse.validate import findings, load_rules, run_rules


def test_clean_load_has_zero_findings(con):
    assert findings(con, "raw") == {}


def test_every_rule_runs_and_is_reported(con):
    results = run_rules(con, "raw")
    assert set(results) == set(load_rules())
    assert len(results) >= 25


def test_dirty_load_has_exactly_the_injected_defects(con):
    assert findings(con, "raw_dirty") == EXPECTED_DIRTY_FINDINGS


def test_dirty_row_counts_are_clean_plus_injected(con):
    count = lambda s, t: con.execute(f"select count(*) from {s}.{t}").fetchone()[0]  # noqa: E731
    assert count("raw_dirty", "deductions") == count("raw", "deductions") + 3
    assert count("raw_dirty", "payments") == count("raw", "payments") + 3
    assert count("raw_dirty", "invoices") == count("raw", "invoices")


def test_raw_dirty_has_no_constraints_but_raw_has(con):
    q = "select count(*) from duckdb_constraints() where schema_name = ?"
    assert con.execute(q, ["raw_dirty"]).fetchone()[0] == 0
    assert con.execute(q, ["raw"]).fetchone()[0] > 30


BAD_ROWS = {
    "negative_amount": "-5, 'other', 'open'",
    "bad_reason_code": "5, 'bogus', 'open'",
    "duplicate_pk": "5, 'other', 'open'",
    "not_null": "5, 'other', 'open'",
    "orphan_fk": "5, 'other', 'open'",
}
INSERT = "insert into raw.deductions values ({id}, {inv}, 1, null, {day}, {tail})"


@pytest.mark.parametrize("case", list(BAD_ROWS))
def test_raw_schema_rejects_bad_rows(loaded_warehouse, tmp_path, case):
    import shutil

    copy = tmp_path / "copy.duckdb"
    shutil.copy(loaded_warehouse, copy)
    sql = INSERT.format(
        id=1 if case == "duplicate_pk" else 999999,
        inv=999_999_999 if case == "orphan_fk" else 1,
        day="null" if case == "not_null" else "date '2024-01-01'",
        tail=BAD_ROWS[case],
    )
    connection = duckdb.connect(str(copy))
    try:
        with pytest.raises(duckdb.Error):
            connection.execute(sql)
    finally:
        connection.close()
