"""Order-independent content fingerprint of every table/view in raw, marts and metrics (SYNTHETIC data).

Used by the audit to prove two builds are identical without comparing raw DuckDB file bytes.
Usage: python -m scripts.fingerprint [warehouse.duckdb]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

from data_gen.load import DEFAULT_PATH

SCHEMAS = ("raw", "raw_dirty", "marts", "metrics")


def fingerprint(path: Path) -> dict[str, list]:
    con = duckdb.connect(str(path), read_only=True)
    out = {}
    for schema in SCHEMAS:
        tables = con.execute(
            "select table_name from information_schema.tables where table_schema = ? order by 1",
            [schema],
        ).fetchall()
        for (table,) in tables:
            count, digest = con.execute(
                f'select count(*), coalesce(sum(hash(t)::hugeint), 0)::varchar from {schema}."{table}" as t'
            ).fetchone()
            out[f"{schema}.{table}"] = [count, digest]
    con.close()
    return out


if __name__ == "__main__":
    print(
        json.dumps(
            fingerprint(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PATH),
            indent=1,
            sort_keys=True,
        )
    )
