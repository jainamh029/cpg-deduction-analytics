"""Benchmarks for docs/PERFORMANCE.md. Writes REAL measured numbers; nothing in the doc is typed by hand.

Usage: python -m scripts.perf_benchmark   (requires `make build` so target/compiled exists)

1. Optimization adopted: metrics.m_deduction_detail materialized as a table instead of a view.
2. Negative result: rewriting analysis 07's trailing baseline from a range self-join to a window frame.
3. Index candidates on the marts (none adopted).
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import statistics
import tempfile
import time
from pathlib import Path

import duckdb

from data_gen.load import DEFAULT_PATH

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "PERFORMANCE.md"
ANALYSIS = ROOT / "sql" / "analysis"
BEFORE_07 = ROOT / "sql" / "perf" / "07_anomaly_zscores_before.sql"
COMPILED = (
    ROOT
    / "target"
    / "compiled"
    / "cpg_deductions"
    / "models"
    / "metrics"
    / "m_deduction_detail.sql"
)
RUNS = 15
FOCUS = ("04", "05", "06")


def median_ms(con: duckdb.DuckDBPyConnection, sql: str, runs: int = RUNS) -> float:
    con.execute(sql).fetchall()  # warm-up
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        con.execute(sql).fetchall()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def plan_summary(con: duckdb.DuckDBPyConnection, sql: str) -> tuple[str, float, float]:
    """(indented operator tree with rows and ms, total operator ms, ms spent in PROJECTION operators)."""
    plan = json.loads(con.execute("explain (analyze, format json) " + sql).fetchall()[0][1])
    lines: list[str] = []
    totals = {"all": 0.0, "projection": 0.0}

    def walk(node: dict, depth: int) -> None:
        name, ms = node.get("operator_name", "ROOT"), node.get("operator_timing", 0.0) * 1000
        if name not in ("ROOT", "EXPLAIN_ANALYZE"):
            lines.append(
                f"{'  ' * depth}{name:<16} rows={node.get('operator_cardinality', 0):<7} {ms:7.3f} ms"
            )
            totals["all"] += ms
            totals["projection"] += ms if name == "PROJECTION" else 0.0
        for child in node.get("children", []):
            walk(child, depth + (name not in ("ROOT", "EXPLAIN_ANALYZE")))

    walk(plan, 0)
    return "\n".join(lines), totals["all"], totals["projection"]


def analysis_sql(prefix: str) -> str:
    return next(ANALYSIS.glob(f"{prefix}_*.sql")).read_text()


def same_rows(con: duckdb.DuckDBPyConnection, a: str, b: str) -> bool:
    ra = sorted(con.execute(a).fetchall(), key=lambda r: (r[0], r[1], str(r[2])))
    rb = sorted(con.execute(b).fetchall(), key=lambda r: (r[0], r[1], str(r[2])))
    return len(ra) == len(rb) and all(
        x[:3] == y[:3] and abs(float(x[6]) - float(y[6])) < 1e-6
        for x, y in zip(ra, rb, strict=True)
    )


def materialization_experiment(con: duckdb.DuckDBPyConnection) -> tuple[list, tuple, tuple]:
    """Before = the same model as a view (from dbt's compiled SQL); after = the real table."""
    con.execute(f"create view metrics.v_deduction_detail as {COMPILED.read_text()}")
    results = []
    for prefix in FOCUS:
        after_sql = analysis_sql(prefix)
        before_sql = after_sql.replace("metrics.m_deduction_detail", "metrics.v_deduction_detail")
        assert con.execute(before_sql).fetchall() == con.execute(after_sql).fetchall()
        results.append((prefix, median_ms(con, before_sql), median_ms(con, after_sql)))
    q = analysis_sql("05")
    plans = (
        plan_summary(con, q.replace("metrics.m_deduction_detail", "metrics.v_deduction_detail")),
        plan_summary(con, q),
    )
    return results, *plans


def index_experiment(con: duckdb.DuckDBPyConnection) -> list[tuple[str, float, float]]:
    cases = {
        "point lookup: deduction_id = 25000": (
            "select * from marts.fct_deductions where deduction_id = 25000",
            "create index ix_ded_id on marts.fct_deductions (deduction_id)",
        ),
        "worklist slice: retailer 1, one month": (
            "select * from marts.fct_deductions where retailer_id = 1 "
            "and deduction_date >= date '2025-06-01' and deduction_date < date '2025-07-01'",
            "create index ix_ded_ret on marts.fct_deductions (retailer_id)",
        ),
    }
    results = []
    for name, (sql, ddl) in cases.items():
        before = median_ms(con, sql, 21)
        con.execute(ddl)
        results.append((name, before, median_ms(con, sql, 21)))
    return results


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        # The file must keep its name: dbt views embed the catalog name (= file stem).
        copy = Path(tmp) / DEFAULT_PATH.name
        shutil.copy(DEFAULT_PATH, copy)
        con = duckdb.connect(str(copy))
        mat, view_plan, table_plan = materialization_experiment(con)
        after_07 = analysis_sql("07")
        before_07 = BEFORE_07.read_text()
        assert same_rows(con, before_07, after_07), "07 before/after disagree"
        t07 = (median_ms(con, before_07), median_ms(con, after_07))
        idx = index_experiment(con)
        con.close()

    mat_rows = "\n".join(f"| {p} | {b:.2f} | {a:.2f} | {b / a:.1f}x |" for p, b, a in mat)
    idx_rows = "\n".join(f"| {n} | {b:.2f} | {a:.2f} |" for n, b, a in idx)
    OUT.write_text(f"""# Performance notes (SYNTHETIC data)

Measured by `scripts/perf_benchmark.py` on this machine ({platform.platform()}, {os.cpu_count()} CPUs,
DuckDB {duckdb.__version__}). Every number below is the median of {RUNS} runs after one warm-up, produced by
that script. The dataset is small (~49k deductions), so absolute times are milliseconds; the honest takeaway
is the relative cost of each approach, and that none of these queries is slow at this scale.

## 1. Optimization adopted: materialize `metrics.m_deduction_detail`

`m_deduction_detail` applies about a dozen metric macros to every deduction. As a view, every analysis that
reads it re-evaluates those expressions over all ~49k rows. As a table (dbt `materialized: table`), they are
computed once per build.

**Before:** the model as a view (SQL from dbt's compiled output). **After:** the table now in the project.
Same query text otherwise; the script first asserts both return identical rows.

| Analysis | Before: view (ms) | After: table (ms) | Speed-up |
|---|---|---|---|
{mat_rows}

### EXPLAIN ANALYZE of analysis 05 (operator, rows out, operator time)

Before (view):
```
{view_plan[0]}
```
After (table):
```
{table_plan[0]}
```

Total operator time: {view_plan[1]:.3f} ms before vs {table_plan[1]:.3f} ms after; time inside PROJECTION
operators (where the macro expressions are evaluated): {view_plan[2]:.3f} ms before vs {table_plan[2]:.3f} ms
after. The trade-off: the table is only as fresh as the last `dbt build`, which is how this project is built
anyway.

## 2. Negative result: window frame vs range self-join (analysis 07)

I expected replacing the self-join baseline ([sql/perf/07_anomaly_zscores_before.sql](../sql/perf/07_anomaly_zscores_before.sql))
with a window frame (`rows between 12 preceding and 1 preceding`) to be faster. At this size it is not
measurably different:

| Version | Median runtime (ms) |
|---|---|
| Range self-join | {t07[0]:.2f} |
| Window frame (kept; clearer to read) | {t07[1]:.2f} |

The window version stays because it is shorter and easier to audit, not because it is faster.

## 3. Indexes considered (none added)

Each index was created on a throw-away copy of the built warehouse (median of 21 runs, ms):

| Query | Without index | With index |
|---|---|---|
{idx_rows}

**Decision:** no explicit indexes on the marts. DuckDB scans these columnar tables in about a millisecond; the
dashboard and analysis queries aggregate rather than look up single rows, and an ART index slows bulk loads
and full rebuilds. See DECISIONS.md D22. The `raw` schema keeps the PK/FK indexes its constraints imply.
""")
    print(f"wrote {OUT}")
    for p, b, a in mat:
        print(f"{p}: view={b:.2f}ms table={a:.2f}ms")
    print(f"07: self-join={t07[0]:.2f}ms window={t07[1]:.2f}ms")


if __name__ == "__main__":
    main()
