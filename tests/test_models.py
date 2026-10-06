"""Phase 2: warehouse models. Marts reconcile to raw, joins never inflate rows, the unattributed
SKU bucket exists, and the pipeline can be pointed at raw_dirty."""

import shutil
from pathlib import Path

import duckdb
import yaml

from data_gen.config import Config

from .helpers import REPO_ROOT, run_dbt, run_results


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def test_dbt_build_all_green(built_warehouse):
    """The built_warehouse fixture asserts `dbt build` (models + data tests) exited 0."""
    assert built_warehouse.exists()


def test_as_of_date_matches_generator_end_date():
    project = yaml.safe_load((REPO_ROOT / "dbt_project.yml").read_text())
    assert project["vars"]["as_of_date"] == Config().end_date.isoformat()


def test_gross_revenue_reconciles_to_raw(bcon):
    raw = scalar(bcon, "select sum(gross_amount) from raw.invoices")
    assert scalar(bcon, "select sum(gross_amount) from marts.fct_invoices") == raw
    assert scalar(bcon, "select sum(lines_amount) from marts.fct_invoices") == raw


def test_deduction_dollars_reconcile_to_raw(bcon):
    raw = scalar(bcon, "select sum(amount) from raw.deductions")
    assert scalar(bcon, "select sum(amount) from marts.fct_deductions") == raw
    assert scalar(bcon, "select sum(deduction_amount) from marts.fct_invoices") == raw


def test_recovered_dollars_reconcile_to_raw(bcon):
    raw = scalar(bcon, "select sum(recovered_amount) from raw.disputes")
    assert scalar(bcon, "select sum(recovered_amount) from marts.fct_deductions") == raw
    assert scalar(bcon, "select sum(recovered_amount) from marts.fct_disputes") == raw
    assert scalar(bcon, "select sum(recovered_amount) from marts.fct_invoices") == raw


def test_payments_reconcile_to_raw(bcon):
    raw = scalar(bcon, "select sum(paid_amount) from raw.payments")
    assert scalar(bcon, "select sum(payments_amount) from marts.fct_invoices") == raw


def test_no_row_inflation_after_joins(bcon):
    pairs = {
        "marts.fct_invoices": "raw.invoices",
        "marts.fct_deductions": "raw.deductions",
        "marts.fct_disputes": "raw.disputes",
        "marts.fct_promotions": "raw.promotions",
        "marts.dim_retailer": "raw.retailers",
    }
    for mart, raw in pairs.items():
        assert scalar(bcon, f"select count(*) from {mart}") == scalar(
            bcon, f"select count(*) from {raw}"
        ), mart
    assert (
        scalar(bcon, "select count(*) from marts.dim_sku")
        == scalar(bcon, "select count(*) from raw.skus") + 1
    )  # plus the '(unattributed)' row


def test_unattributed_bucket_exists_and_nothing_is_dropped(bcon):
    assert scalar(bcon, "select count(*) from marts.dim_sku where sku_key = -1") == 1
    null_rows = scalar(bcon, "select count(*) from raw.deductions where sku_id is null")
    assert null_rows > 0
    assert scalar(bcon, "select count(*) from marts.fct_deductions where sku_key = -1") == null_rows
    by_sku = scalar(
        bcon,
        "select sum(d.amount) from marts.fct_deductions d join marts.dim_sku s using (sku_key)",
    )
    assert by_sku == scalar(bcon, "select sum(amount) from raw.deductions")  # inner join loses 0


def test_sku_null_rate_in_documented_range(bcon):
    rate = scalar(
        bcon, "select avg(case when is_sku_attributed then 0 else 1 end) from marts.fct_deductions"
    )
    assert 0.35 <= rate <= 0.60


def test_pipeline_runs_on_raw_dirty_and_data_tests_catch_the_defects(built_warehouse, tmp_path):
    """Source switch raw -> raw_dirty. Models build; dbt data tests flag the injected defects."""
    copy = tmp_path / "dirty.duckdb"
    shutil.copy(built_warehouse, copy)
    target = tmp_path / "target"
    result = run_dbt(
        "build", "--select", "staging", "--vars", "{raw_schema: raw_dirty}",
        warehouse=copy, target_path=target,
    )  # fmt: skip
    assert result.returncode != 0  # data tests fail on dirty data
    statuses = run_results(target)
    models = {n: s for n, s in statuses.items() if n.startswith("stg_")}
    assert models and set(models.values()) == {"success"}  # all staging views built
    failed = {n for n, s in statuses.items() if s == "fail"}
    assert failed == {
        "relationships_stg_deductions_invoice_id__invoice_id__ref_stg_invoices_",
        "non_negative_stg_deductions_amount",
    }
    con = duckdb.connect(str(copy), read_only=True)
    assert scalar(con, "select count(*) from staging.stg_deductions") == scalar(
        con, "select count(*) from raw_dirty.deductions"
    )
    con.close()


def test_clean_raw_still_passes_after_dirty_run_is_isolated(built_warehouse):
    """The dirty run above used a copy, so the shared warehouse still points at clean raw."""
    assert isinstance(built_warehouse, Path)
    con = duckdb.connect(str(built_warehouse), read_only=True)
    assert scalar(con, "select count(*) from staging.stg_deductions") == scalar(
        con, "select count(*) from raw.deductions"
    )
    con.close()
