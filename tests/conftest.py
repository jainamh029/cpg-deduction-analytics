"""Shared fixtures. The default dataset is generated once per test session (fast: ~1s)."""

import os
import shutil
from pathlib import Path

import duckdb
import pytest

from data_gen.config import Config
from data_gen.generate import Tables, generate
from data_gen.load import DEFAULT_PATH, build_warehouse

from .helpers import run_dbt


@pytest.fixture(scope="session")
def tables() -> Tables:
    return generate(Config())


@pytest.fixture(scope="session")
def loaded_warehouse(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A warehouse file with the `raw` (clean) and `raw_dirty` schemas only."""
    path = tmp_path_factory.mktemp("wh") / "warehouse.duckdb"
    build_warehouse(path, Config())
    return path


@pytest.fixture
def con(loaded_warehouse: Path):
    connection = duckdb.connect(str(loaded_warehouse), read_only=True)
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def built_warehouse(loaded_warehouse: Path, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A warehouse with every dbt layer built from the clean `raw` schema.

    `make test` sets CPG_USE_BUILT=1 to reuse warehouse/warehouse.duckdb that `make build`
    already produced; otherwise a private copy is built so tests stay hermetic.
    """
    if os.environ.get("CPG_USE_BUILT") and DEFAULT_PATH.exists():
        return DEFAULT_PATH
    path = tmp_path_factory.mktemp("built") / "warehouse.duckdb"
    shutil.copy(loaded_warehouse, path)
    result = run_dbt("build", warehouse=path, target_path=path.parent / "target")
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-1000:]
    return path


@pytest.fixture
def bcon(built_warehouse: Path):
    connection = duckdb.connect(str(built_warehouse), read_only=True)
    yield connection
    connection.close()
