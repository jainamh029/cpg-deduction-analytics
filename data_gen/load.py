"""Build warehouse/warehouse.duckdb: constrained `raw` (clean) and unconstrained `raw_dirty`."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

from .config import Config
from .dirty import inject_defects
from .generate import Tables, generate

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = REPO_ROOT / "warehouse" / "warehouse.duckdb"
DDL_FILE = REPO_ROOT / "warehouse" / "ddl.sql"
LOAD_ORDER = (
    "retailers", "skus", "invoices", "invoice_lines", "payments",
    "promotions", "deductions", "disputes",
)  # fmt: skip


def _insert(con: duckdb.DuckDBPyConnection, schema: str, table: str, df) -> None:
    cols = con.execute(
        "select column_name, data_type from information_schema.columns "
        "where table_schema = ? and table_name = ? order by ordinal_position",
        [schema, table],
    ).fetchall()
    select = ", ".join(f'cast("{name}" as {dtype}) as "{name}"' for name, dtype in cols)
    con.register("df_in", df[[name for name, _ in cols]])
    con.execute(f"insert into {schema}.{table} select {select} from df_in")
    con.unregister("df_in")


def build_warehouse(path: Path, cfg: Config | None = None) -> Tables:
    """(Re)create the warehouse file. Returns the clean tables for convenience."""
    cfg = cfg or Config()
    clean = generate(cfg)
    dirty = inject_defects(clean, cfg.seed)
    path.parent.mkdir(parents=True, exist_ok=True)
    for stale in (path, Path(f"{path}.wal")):
        stale.unlink(missing_ok=True)
    con = duckdb.connect(str(path))
    con.execute(DDL_FILE.read_text())
    con.execute("create schema raw_dirty")
    for table in LOAD_ORDER:
        _insert(con, "raw", table, clean[table])
        con.execute(f"create table raw_dirty.{table} as select * from raw.{table} limit 0")
        _insert(con, "raw_dirty", table, dirty[table])
    con.close()
    return clean


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the SYNTHETIC warehouse.")
    parser.add_argument("--path", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--seed", type=int, default=Config.seed)
    args = parser.parse_args()
    build_warehouse(args.path, Config(seed=args.seed))
    print(f"wrote {args.path}")


if __name__ == "__main__":
    main()
