# Audit log

Real command output from the independent audit (branch `audit`). Data is synthetic.

## Audit 1a: mutation baseline (before any audit fix)

```
$ python -m scripts.mutation_audit --out docs/audit/mutation_baseline.json
M01 KILLED    tests/test_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql]  (7.4s)
M02 KILLED    tests/test_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql]  (6.6s)
M03 KILLED    tests/test_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql]  (6.5s)
M04 SURVIVED    (21.6s)
M05 SURVIVED    (21.5s)
M06 KILLED    tests/test_analysis.py::test_04_open_balance_and_buckets_match_raw  (7.2s)
M07 KILLED    tests/test_analysis.py::test_04_open_balance_and_buckets_match_raw  (6.8s)
M08 KILLED    tests/test_analysis.py::test_04_open_balance_and_buckets_match_raw  (6.9s)
M09 KILLED    tests/test_analysis.py::test_02_rate_trend_rows_values_and_ranks  (6.9s)
M10 KILLED    tests/test_analysis.py::test_10_recoverable_dollars_match_independent_computation  (6.9s)
M11 KILLED    tests/test_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more  (6.6s)
M12 KILLED    tests/test_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql]  (6.5s)
M13 KILLED    tests/test_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql]  (6.3s)
M14 KILLED    tests/test_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more  (7.3s)
M15 KILLED    tests/test_analysis.py::test_04_open_balance_and_buckets_match_raw  (7.1s)
M16 KILLED    tests/test_analysis.py::test_file_header_and_execution[07_anomaly_zscores.sql]  (7.0s)
M17 KILLED    tests/test_analysis.py::test_07_anomalies_find_the_planted_event_and_not_too_many_others  (7.2s)
M18 KILLED    tests/test_findings.py::test_readme_numbers_match_independent_raw_table_sql  (10.2s)
M19 KILLED    tests/test_dashboard.py::test_filters_move_results_in_the_expected_direction  (7.2s)
M20 KILLED    tests/test_models.py::test_payments_reconcile_to_raw  (16.2s)
M21 KILLED    tests/test_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more  (7.2s)
M22 KILLED    tests/test_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more  (7.2s)
M23 KILLED    tests/test_analysis.py::test_01_waterfall_components_sum_to_net_and_match_raw  (7.0s)
M24 KILLED    tests/test_analysis.py::test_04_open_balance_and_buckets_match_raw  (7.0s)
M25 KILLED    tests/test_analysis.py::test_10_recoverable_dollars_match_independent_computation  (7.2s)
M26 KILLED    tests/test_findings.py::test_readme_numbers_match_independent_raw_table_sql  (10.3s)
M27 KILLED    tests/test_analysis.py::test_03_fine_outlier_and_sku_concentration_with_unattributed_bucket  (7.0s)
M28 KILLED    tests/test_validator.py::test_dirty_load_has_exactly_the_injected_defects  (21.7s)
M29 KILLED    tests/test_metrics.py::test_6_days_to_resolve  (15.7s)
M30 KILLED    tests/test_analysis.py::test_08_payment_lag_drift_flags_retailer_b_and_matches_raw  (6.9s)
killed 28/30 = 93%
```

## Audit 4a: fresh clone in a path containing a space, make all twice

```
$ scripts/audit_fresh_clone.sh <python3.11>
clone root: <tmp>/path with space
run 1: make all exit code 0
All checks passed!
validation passed for schema raw: 34 rules, 0 findings
20:42:24  Done. PASS=116 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=116
0 failure(s)
165 passed in 19.41s
run 2: make all exit code 0
All checks passed!
validation passed for schema raw: 34 rules, 0 findings
20:43:50  Done. PASS=116 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=116
0 failure(s)
165 passed in 20.65s
--- diff of table fingerprints (empty = identical):
identical (29 tables)
--- diff of output file hashes (empty = identical):
identical (      12 files)
--- tracked files modified by make all (run 1 / run 2):
       0
       0
--- any 'bad interpreter' / 'No such file' errors:
<tmp>/path with space/make1.log:0
<tmp>/path with space/make2.log:0
```

