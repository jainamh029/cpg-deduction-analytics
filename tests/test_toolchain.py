"""Phase 0 smoke tests: the dbt + DuckDB toolchain is wired up and the project parses."""

import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_dbt(*args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DBT_PROFILES_DIR": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "dbt.cli.main", *args],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_dbt_connects_to_duckdb() -> None:
    result = run_dbt("debug")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "All checks passed" in result.stdout


def test_dbt_project_parses() -> None:
    result = run_dbt("parse")
    assert result.returncode == 0, result.stdout + result.stderr
