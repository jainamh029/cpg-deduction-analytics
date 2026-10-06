"""Audit 4: end-to-end pipeline behaviour: dirty data, idempotency, interruption, inflation, docs, pins."""

import shutil
import subprocess
import sys
import time
from pathlib import Path

import duckdb
import yaml

from data_gen.config import Config
from data_gen.load import build_warehouse
from scripts.fingerprint import fingerprint

from .helpers import REPO_ROOT, run_dbt


def scalar(con, sql):
    return con.execute(sql).fetchone()[0]


def validate_cli(warehouse: Path, schema: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "warehouse.validate", "--schema", schema, "--warehouse", str(warehouse)],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )  # fmt: skip


def test_validation_gate_passes_clean_data_and_blocks_dirty_data(loaded_warehouse):
    clean, dirty = (
        validate_cli(loaded_warehouse, "raw"),
        validate_cli(loaded_warehouse, "raw_dirty"),
    )
    assert clean.returncode == 0 and "0 findings" in clean.stdout
    assert dirty.returncode == 1 and "validation FAILED" in dirty.stdout
    for rule in ("fk_deductions_invoice", "duplicate_payments", "nonpositive_deduction_amount"):
        assert rule in dirty.stdout


def test_make_build_runs_the_validation_gate_before_dbt():
    dry = subprocess.run(
        ["make", "-n", "build"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    ).stdout
    assert dry.index("warehouse.validate") < dry.index("dbt build")
    assert "data_gen.load" in dry and dry.index("data_gen.load") < dry.index("warehouse.validate")


def test_bypassing_the_gate_dirty_data_fails_dbt_and_leaves_previous_marts_untouched(
    built_warehouse, tmp_path
):
    """What happens if dirty data reaches dbt anyway: dbt stops at staging and SKIPS the marts, which stay as the
    previous (clean) build left them. Not silently wrong, but stale: the validation gate exists to stop this earlier."""
    copy = tmp_path / "warehouse.duckdb"
    shutil.copy(built_warehouse, copy)
    con = duckdb.connect(str(copy), read_only=True)
    before = scalar(con, "select count(*) from marts.fct_deductions")
    con.close()
    result = run_dbt(
        "build",
        "--vars",
        "{raw_schema: raw_dirty}",
        warehouse=copy,
        target_path=tmp_path / "target",
    )
    assert result.returncode != 0
    con = duckdb.connect(str(copy), read_only=True)
    assert (
        scalar(con, "select count(*) from marts.fct_deductions") == before
    )  # skipped, not rebuilt from dirty rows
    assert (
        scalar(con, "select count(*) from raw_dirty.deductions") == before + 3
    )  # the dirty rows were never used
    con.close()


def test_every_stage_is_idempotent_and_the_rebuilt_warehouse_is_identical(tmp_path):
    path = tmp_path / "warehouse.duckdb"
    cfg = Config(seed=9, revenue_scale=0.05)
    build_warehouse(path, cfg)
    first_raw = fingerprint(path)
    build_warehouse(path, cfg)  # data stage twice
    assert fingerprint(path) == first_raw
    assert run_dbt("build", warehouse=path, target_path=tmp_path / "t1").returncode == 0
    once = fingerprint(path)
    assert (
        run_dbt("build", warehouse=path, target_path=tmp_path / "t2").returncode == 0
    )  # dbt stage twice
    assert fingerprint(path) == once


def test_a_killed_data_load_never_corrupts_the_existing_warehouse_and_a_rerun_recovers(tmp_path):
    path = tmp_path / "warehouse.duckdb"
    build_warehouse(path, Config())
    reference = fingerprint(path)
    building = path.with_name("warehouse.building.duckdb")
    process = subprocess.Popen([sys.executable, "-m", "data_gen.load", "--path", str(path)], cwd=REPO_ROOT,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    deadline = time.time() + 30
    while not building.exists() and process.poll() is None and time.time() < deadline:
        time.sleep(0.02)
    assert process.poll() is None, "the load finished before the kill: the test would prove nothing"
    process.kill()  # killed while the temporary file is being written
    process.wait()
    assert (
        fingerprint(path) == reference
    )  # the original file is untouched (build happens beside it)
    done = subprocess.run(
        [sys.executable, "-m", "data_gen.load", "--path", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        check=False,
    )
    assert done.returncode == 0 and fingerprint(path) == reference
    assert not building.exists()


def test_a_killed_dbt_build_leaves_a_partial_warehouse_and_rerunning_repairs_it(tmp_path):
    cfg = Config(seed=9, revenue_scale=0.05)
    ref_path, path = tmp_path / "ref" / "warehouse.duckdb", tmp_path / "run" / "warehouse.duckdb"
    build_warehouse(ref_path, cfg)
    build_warehouse(path, cfg)
    start = time.time()
    assert run_dbt("build", warehouse=ref_path, target_path=tmp_path / "t_ref").returncode == 0
    duration = time.time() - start
    reference = fingerprint(ref_path)
    env = {"WAREHOUSE_PATH": str(path), "DBT_PROFILES_DIR": str(REPO_ROOT), "PATH": "/usr/bin:/bin"}
    process = subprocess.Popen([sys.executable, "-m", "dbt.cli.main", "build", "--target-path", str(tmp_path / "killed")],
                               cwd=REPO_ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    time.sleep(0.6 * duration)
    assert process.poll() is None, "dbt finished before the kill: the test would prove nothing"
    process.kill()
    process.wait()
    assert len(fingerprint(path)) < len(
        reference
    )  # a killed dbt build leaves a PARTIAL warehouse (marts missing)
    assert run_dbt("build", warehouse=path, target_path=tmp_path / "rerun").returncode == 0
    assert fingerprint(path) == reference


def test_metrics_layer_row_counts_and_totals_match_raw_tables(built_warehouse):
    """Independent inflation check written directly against raw tables (not marts)."""
    con = duckdb.connect(str(built_warehouse), read_only=True)
    count = lambda sql: scalar(con, sql)  # noqa: E731
    assert count("select count(*) from metrics.m_deduction_detail") == count(
        "select count(*) from raw.deductions"
    )
    assert count("select count(distinct deduction_id) from metrics.m_deduction_detail") == count(
        "select count(*) from raw.deductions"
    )
    assert count("select count(*) from metrics.m_invoice_detail") == count(
        "select count(*) from raw.invoices"
    )
    assert count("select sum(gross_amount) from metrics.m_retailer_month") == count(
        "select sum(gross_amount) from raw.invoices"
    )
    assert count("select sum(deduction_amount) from metrics.m_retailer_month") == count(
        "select sum(amount) from raw.deductions"
    )
    assert count("select sum(deduction_amount) from metrics.m_deductions_monthly") == count(
        "select sum(amount) from raw.deductions"
    )
    assert count("select sum(deduction_amount) from metrics.m_reason_recovery") == count(
        "select sum(amount) from raw.deductions"
    )
    assert count("select sum(recovered_amount) from metrics.m_deduction_detail") == count(
        "select sum(recovered_amount) from raw.disputes"
    )
    assert count("select count(*) from metrics.m_recoverable_candidates") == count(
        "select count(*) from raw.deductions where status in ('open', 'written_off') "
        "and deduction_id not in (select deduction_id from raw.disputes)"
    )
    con.close()


def test_every_dbt_model_has_a_described_grain():
    described = {}
    for schema_file in (REPO_ROOT / "models").rglob("schema.yml"):
        for model in yaml.safe_load(schema_file.read_text())["models"]:
            described[model["name"]] = model.get("description", "")
    models = {p.stem for p in (REPO_ROOT / "models").rglob("*.sql")}
    assert models == set(described), models ^ set(described)
    missing = [m for m in models if "grain" not in described[m].lower()]
    assert missing == []


def test_dbt_docs_generate_works(built_warehouse, tmp_path):
    result = run_dbt("docs", "generate", warehouse=built_warehouse, target_path=tmp_path / "docs")
    assert result.returncode == 0, result.stdout[-1500:]
    assert (tmp_path / "docs" / "catalog.json").exists() and (
        tmp_path / "docs" / "manifest.json"
    ).exists()


def test_dependencies_are_exactly_pinned_and_locked():
    import tomllib

    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())["project"]
    deps = project["dependencies"] + [
        d for extra in project["optional-dependencies"].values() for d in extra
    ]
    assert deps and all("==" in d for d in deps), [d for d in deps if "==" not in d]
    lock = {
        line.split("==")[0].lower(): line.strip()
        for line in (REPO_ROOT / "requirements.lock").read_text().splitlines()
        if "==" in line
    }
    for dep in deps:
        name, _, version = dep.partition("==")
        assert lock.get(name.lower()) == f"{name}=={version}", dep
