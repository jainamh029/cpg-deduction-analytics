"""Helpers for tests that run dbt against a specific warehouse file."""

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def run_dbt(
    *args: str, warehouse: Path | None = None, target_path: Path | None = None
) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DBT_PROFILES_DIR": str(REPO_ROOT)}
    if warehouse is not None:
        env["WAREHOUSE_PATH"] = str(warehouse)
    cmd = [sys.executable, "-m", "dbt.cli.main", *args]
    if target_path is not None:
        cmd += ["--target-path", str(target_path)]
    return subprocess.run(cmd, cwd=REPO_ROOT, env=env, capture_output=True, text=True, check=False)


def run_results(target_path: Path) -> dict[str, str]:
    """{node name: status} from dbt's run_results.json."""
    data = json.loads((target_path / "run_results.json").read_text())
    return {r["unique_id"].split(".")[2]: r["status"] for r in data["results"]}
