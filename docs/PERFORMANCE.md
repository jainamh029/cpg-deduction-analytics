# Performance notes (SYNTHETIC data)

Measured by `scripts/perf_benchmark.py` on this machine (macOS-26.2-arm64-arm-64bit, 8 CPUs,
DuckDB 1.5.6). Every number below is the median of 15 runs after one warm-up, produced by
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
| 04 | 2.86 | 1.99 | 1.4x |
| 05 | 2.83 | 1.66 | 1.7x |
| 06 | 3.01 | 1.79 | 1.7x |

### EXPLAIN ANALYZE of analysis 05 (operator, rows out, operator time)

Before (view):
```
PROJECTION       rows=4         0.000 ms
  ORDER_BY         rows=4         0.008 ms
    PROJECTION       rows=4         0.000 ms
      PROJECTION       rows=4         0.000 ms
        PROJECTION       rows=4         0.000 ms
          WINDOW           rows=4         0.061 ms
            PROJECTION       rows=4         0.004 ms
              PROJECTION       rows=4         0.001 ms
                HASH_GROUP_BY    rows=4         0.532 ms
                  PROJECTION       rows=11877     0.003 ms
                    PROJECTION       rows=11877     0.018 ms
                      PROJECTION       rows=11877     0.003 ms
                        PROJECTION       rows=11877     0.229 ms
                          PROJECTION       rows=11877     0.093 ms
                            CROSS_PRODUCT    rows=11877     0.010 ms
                              SEQ_SCAN         rows=11877     0.801 ms
                              PROJECTION       rows=1         0.000 ms
                                PROJECTION       rows=1         0.000 ms
                                  PROJECTION       rows=1         0.000 ms
                                    UNGROUPED_AGGREGATE rows=1         0.001 ms
                                      PROJECTION       rows=1         0.000 ms
                                        COLUMN_DATA_SCAN rows=1         0.001 ms
```
After (table):
```
PROJECTION       rows=4         0.000 ms
  ORDER_BY         rows=4         0.008 ms
    PROJECTION       rows=4         0.000 ms
      PROJECTION       rows=4         0.000 ms
        PROJECTION       rows=4         0.000 ms
          WINDOW           rows=4         0.052 ms
            PROJECTION       rows=4         0.004 ms
              PROJECTION       rows=4         0.001 ms
                HASH_GROUP_BY    rows=4         0.499 ms
                  PROJECTION       rows=11877     0.003 ms
                    PROJECTION       rows=11877     0.027 ms
                      SEQ_SCAN         rows=11877     0.662 ms
```

Total operator time: 1.767 ms before vs 1.256 ms after; time inside PROJECTION
operators (where the macro expressions are evaluated): 0.353 ms before vs 0.036 ms
after. The trade-off: the table is only as fresh as the last `dbt build`, which is how this project is built
anyway.

## 2. Negative result: window frame vs range self-join (analysis 07)

I expected replacing the self-join baseline ([sql/perf/07_anomaly_zscores_before.sql](../sql/perf/07_anomaly_zscores_before.sql))
with a window frame (`rows between 12 preceding and 1 preceding`) to be faster. At this size it is not
measurably different:

| Version | Median runtime (ms) |
|---|---|
| Range self-join | 3.53 |
| Window frame (kept; clearer to read) | 3.65 |

The window version stays because it is shorter and easier to audit, not because it is faster.

## 3. Indexes considered (none added)

Each index was created on a throw-away copy of the built warehouse (median of 21 runs, ms):

| Query | Without index | With index |
|---|---|---|
| point lookup: deduction_id = 25000 | 0.25 | 0.15 |
| worklist slice: retailer 1, one month | 0.72 | 0.72 |

**Decision:** no explicit indexes on the marts. DuckDB scans these columnar tables in about a millisecond; the
dashboard and analysis queries aggregate rather than look up single rows, and an ART index slows bulk loads
and full rebuilds. See DECISIONS.md D22. The `raw` schema keeps the PK/FK indexes its constraints imply.
