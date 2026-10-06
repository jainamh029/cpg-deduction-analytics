"""Shared fixtures. The default dataset is generated once per test session (fast: ~1s)."""

from pathlib import Path

import duckdb
import pytest

from data_gen.config import Config
from data_gen.generate import Tables, generate
from data_gen.load import build_warehouse


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
