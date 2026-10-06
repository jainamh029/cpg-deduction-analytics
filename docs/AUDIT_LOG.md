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


## Audit 1b: final mutation run (42 mutations, after all audit fixes)

```
$ python -m scripts.mutation_audit --out docs/audit/mutation_final.json
M01 KILLED    tests/test_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql]  (6.7s)
M02 KILLED    tests/test_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql]  (6.8s)
M03 KILLED    tests/test_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql]  (7.1s)
M04 KILLED    tests/test_messy_conditions.py::test_orphans_are_retained_not_silently_dropped_by_the_marts  (16.9s)
M05 KILLED    tests/test_messy_conditions.py::test_orphans_are_retained_not_silently_dropped_by_the_marts  (16.0s)
M06 KILLED    tests/test_analysis.py::test_04_open_balance_and_buckets_match_raw  (7.2s)
M07 KILLED    tests/test_analysis.py::test_04_open_balance_and_buckets_match_raw  (6.9s)
M08 KILLED    tests/test_analysis.py::test_04_open_balance_and_buckets_match_raw  (6.9s)
M09 KILLED    tests/test_analysis.py::test_02_rate_trend_rows_values_and_ranks  (6.6s)
M10 KILLED    tests/test_analysis.py::test_10_recoverable_dollars_match_independent_computation  (6.8s)
M11 KILLED    tests/test_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more  (6.8s)
M12 KILLED    tests/test_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql]  (6.6s)
M13 KILLED    tests/test_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql]  (6.3s)
M14 KILLED    tests/test_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more  (6.6s)
M15 KILLED    tests/test_analysis.py::test_04_open_balance_and_buckets_match_raw  (6.7s)
M16 KILLED    tests/test_analysis.py::test_file_header_and_execution[07_anomaly_zscores.sql]  (6.6s)
M17 KILLED    tests/test_analysis.py::test_07_anomalies_find_the_planted_event_and_not_too_many_others  (6.6s)
M18 KILLED    tests/test_forecast.py::test_every_fold_trains_only_on_months_before_its_origin  (16.1s)
M19 KILLED    tests/test_dashboard.py::test_filters_move_results_in_the_expected_direction  (20.5s)
M20 KILLED    tests/test_models.py::test_payments_reconcile_to_raw  (10.5s)
M21 KILLED    tests/test_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more  (6.7s)
M22 KILLED    tests/test_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more  (6.7s)
M23 KILLED    tests/test_analysis.py::test_01_waterfall_components_sum_to_net_and_match_raw  (6.5s)
M24 KILLED    tests/test_analysis.py::test_04_open_balance_and_buckets_match_raw  (6.6s)
M25 KILLED    tests/test_analysis.py::test_10_recoverable_dollars_match_independent_computation  (6.7s)
M26 KILLED    tests/test_forecast.py::test_seasonal_naive_matches_hand_computed_values  (15.8s)
M27 KILLED    tests/test_analysis.py::test_03_fine_outlier_and_sku_concentration_with_unattributed_bucket  (6.9s)
M28 KILLED    tests/test_validator.py::test_dirty_load_has_exactly_the_injected_defects  (15.5s)
M29 KILLED    tests/test_metrics.py::test_6_days_to_resolve  (10.2s)
M30 KILLED    tests/test_analysis.py::test_08_payment_lag_drift_flags_retailer_b_and_matches_raw  (6.9s)
M31 KILLED    tests/test_messy_conditions.py::test_recoveries_on_a_deduction_are_capped_at_its_amount  (15.5s)
M32 KILLED    tests/test_messy_conditions.py::test_analysis_02_lag_means_previous_calendar_month_across_a_gap  (15.7s)
M33 KILLED    tests/test_pipeline_robustness.py::test_make_build_runs_the_validation_gate_before_dbt  (34.2s)
M34 KILLED    tests/test_messy_conditions.py::test_validator_flags_exactly_the_messy_conditions  (15.6s)
M35 KILLED    tests/test_dashboard.py::test_filters_move_results_in_the_expected_direction  (20.5s)
M36 KILLED    tests/test_forecast.py::test_smape_and_mase_match_hand_computed_values  (19.3s)
M37 KILLED    tests/test_forecast.py::test_smape_and_mase_match_hand_computed_values  (19.0s)
M38 KILLED    tests/test_null_pipeline.py::test_no_reason_is_called_under_invested_on_null_data[1]  (29.3s)
M39 KILLED    tests/test_analysis.py::test_07_anomalies_find_the_planted_event_and_not_too_many_others  (6.9s)
M40 KILLED    tests/test_analysis.py::test_10_recoverable_dollars_match_independent_computation  (7.0s)
M41 KILLED    tests/test_findings.py::test_readme_numbers_match_independent_raw_table_sql  (22.0s)
M42 KILLED    tests/test_pipeline_robustness.py::test_a_killed_data_load_never_corrupts_the_existing_warehouse_and_a_rerun_r  (47.2s)
killed 42/42 = 100%
```

## Audit 1c: does the hygiene test alone catch M22 (re-derived bucket label in an analysis file)?

```
$ (apply M22) pytest tests/test_hygiene.py -q -x -rf
FAILED tests/test_hygiene.py::test_analysis_sql_reuses_the_metrics_layer[05_filing_lag_cohorts.sql]  -> line 36: filing-lag bucket labels belong in metrics.filing_lag_bucket
```

## Audit 1d: mutmut 3.8.0 on forecast/model.py (pure-function tests only; scratch clone)

```
$ mutmut run   # before the audit added hand-computed tests
⠸ 564/564  🎉 310 🫥 144  ⏰ 0  🤔 0  🙁 110  🔇 0  🧙 0
7.82 mutations/second
$ mutmut run   # after
⠸ 564/564  🎉 370 🫥 144  ⏰ 0  🤔 0  🙁 50  🔇 0  🧙 0
9.78 mutations/second
status by function after (survived / no tests):
  72 small_denominator_report: no
  72 forward_forecast: no
  19 compare_models: survived
  18 holt_winters: survived
   9 interval_coverage: survived
   1 seasonal_naive: survived
   1 score: survived
   1 origin_losses: survived
   1 backtest: survived
```

## Audit 2a-b: null and planted sweeps (20 seeds each), summarized from docs/audit/*.json

```
{
 "null_before": {
  "runs": 20,
  "p1_max_ratio": 1.980559011487568,
  "p1_mean_ratio": 1.5728080477497475,
  "p1_flagged_runs": 0,
  "p2_max_median_spike": 1.2727101127838198,
  "p2_detected_runs": 0,
  "p2_retailer_years_spiking_mean": 1.85,
  "p3_runs_with_a_flag": 19,
  "p3_flags_per_run": 1.65,
  "p4_max_change_days": 1.4780438760800507,
  "p4_detected_runs": 0,
  "p5_detected_runs": 0,
  "anomalies_mean": 25.65,
  "anomalies_min": 18,
  "anomalies_max": 31,
  "recoverable_180_base_mean": 644122.2200307145,
  "filing_lag_win_gap_mean": -0.0015598588324696183
 },
 "null_after": {
  "runs": 20,
  "p1_max_ratio": 1.980559011487568,
  "p1_mean_ratio": 1.5728080477497475,
  "p1_flagged_runs": 0,
  "p2_max_median_spike": 1.2727101127838198,
  "p2_detected_runs": 0,
  "p2_retailer_years_spiking_mean": 1.85,
  "p3_runs_with_a_flag": 0,
  "p3_flags_per_run": 0.0,
  "p4_max_change_days": 1.4780438760800507,
  "p4_detected_runs": 0,
  "p5_detected_runs": 0,
  "anomalies_mean": 3.1,
  "anomalies_min": 1,
  "anomalies_max": 5,
  "recoverable_180_base_mean": 644122.2200307145,
  "filing_lag_win_gap_mean": -0.0015598588324696183
 }
}
| Pattern | Effect | Detected | Mean | Min | Max | False positives (sum / mean) |
|---|---|---|---|---|---|---|
| p1 | Retailer A fines vs peers (x) | 20/20 | 2.910 | 2.039 | 3.563 | 0 |
| p2 | Jan-Feb promo spike (x) | 20/20 | 2.445 | 2.057 | 2.792 | None |
| p3 | Shortage win rate | 20/20 | 0.771 | 0.753 | 0.807 | 0 |
| p4 | Retailer B lag change over 6 months (days) | 20/20 | 9.114 | 8.007 | 9.641 | 0 |
| p5 | YoY revenue growth | 20/20 | 0.079 | 0.071 | 0.088 | None |
| p7 | Planted anomaly flagged (abs z >= 4.5) | 19/20 | 6.000 | 2.000 | 11.000 | 4.85 |
```

## Audit 2c: dispute-selection bias (3 seeds per level; means)

```
       history_estimate_180   oracle_180  implied_realization_factor  shortage_observed_win_rate  shortage_true_win_prob_undisputed
level                                                                                                                              
off             1058386.668  1036108.133                       0.980                       0.767                              0.770
0               1053964.448  1034511.318                       0.983                       0.766                              0.764
0.5             1165296.132  1013533.711                       0.870                       0.812                              0.754
1               1289963.380  1028065.710                       0.797                       0.856                              0.746
1.5             1406611.797  1069261.167                       0.760                       0.880                              0.745
```

## Audit 2d: sensitivity of the recoverable-dollar estimate (historical-rate value x realization factor), $M

```
dispute window (days) |  x0.25 |  x0.5 | x0.75 |  x1.0
                   60 |  0.13 |  0.26 |  0.39 |  0.52
                   90 |  0.17 |  0.35 |  0.52 |  0.70
                  120 |  0.22 |  0.44 |  0.66 |  0.88
                  180 |  0.31 |  0.61 |  0.92 |  1.23
                  270 |  0.44 |  0.88 |  1.33 |  1.77
                  365 |  0.65 |  1.30 |  1.95 |  2.60
```

## Audit 4b: validation gate on clean and dirty source; make -n build

```
$ python -m warehouse.validate --schema raw
validation passed for schema raw: 34 rules, 0 findings
$ python -m warehouse.validate --schema raw_dirty; echo exit=$?
validation FAILED for schema raw_dirty: {'fk_deductions_invoice': 3, 'nonpositive_deduction_amount': 3, 'recon_overpaid_invoice': 3, 'duplicate_payments': 3}
exit=1
$ make -n build
python3.11 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -c requirements.lock -e ".[dev]"
touch .venv/.installed
.venv/bin/python -m data_gen.load
.venv/bin/python -m warehouse.validate --schema raw
.venv/bin/dbt build
```

## Audit 4c: kill-and-rerun experiment (tiny warehouse, dbt build killed at 1.0 / 2.0 / 3.0 s; a full build takes 3.2 s)

```
tiny dbt build secs 3.2
kill at 1.0s alive_at_kill=True tables_after_kill(marts+metrics)=0 rerun_matches_reference=True
kill at 2.0s alive_at_kill=True tables_after_kill(marts+metrics)=1 rerun_matches_reference=True
kill at 3.0s alive_at_kill=True tables_after_kill(marts+metrics)=13 rerun_matches_reference=True
```

## Audit 4d: dbt docs generate, grain descriptions, pins (pytest -v on those tests)

```
============================= 10 passed in 32.70s ==============================
```

## Audit 6: dashboard page load, full dataset (scripts/audit_dashboard_timing.py)

```
page   data functions   AppTest page run   Chrome until charts rendered (cold / warm)
sales        13 ms           38 ms
ops          12 ms           35 ms
cfo          14 ms           44 ms
sales  chrome load: cold 1.17s, warm median 0.43s, max 1.17s
ops    chrome load: cold 0.40s, warm median 0.43s, max 0.46s
cfo    chrome load: cold 0.42s, warm median 0.40s, max 0.42s
```

## Audit 6b: dashboard robustness tests (5 filter scenarios x 3 pages, empty selections, number equality, SQL-injection safety)

```
.......................                                                  [100%]
```

## Audit 4e / final: make all from two fresh clones in a path containing a space (final tree)

```
$ scripts/audit_fresh_clone.sh <python3.11>
clone root: <tmp>/path with space
run 1: make all exit code 0
All checks passed!
validation passed for schema raw: 34 rules, 0 findings
21:25:59  Done. PASS=116 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=116
0 failure(s)
236 passed in 88.29s (0:01:28)
run 2: make all exit code 0
All checks passed!
validation passed for schema raw: 34 rules, 0 findings
21:28:31  Done. PASS=116 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=116
0 failure(s)
236 passed in 87.71s (0:01:27)
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

## Final gate (scripts/gate.sh, last section of docs/BUILD_LOG.md)

```
## Audit: final gate

Run on 2026-10-06 17:25 EDT. Output trimmed to the last lines of each command.

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
66 files already formatted

$ .venv/bin/python -m data_gen.load
wrote warehouse/warehouse.duckdb

$ .venv/bin/python -m warehouse.validate --schema raw
validation passed for schema raw: 34 rules, 0 findings

$ .venv/bin/dbt build
21:23:41  112 of 115 OK created sql view model metrics.m_recoverable_candidates .......... [OK in 0.01s]
21:23:41  107 of 115 OK created sql view model metrics.m_deductions_monthly .............. [OK in 0.11s]
21:23:41  113 of 115 START test not_null_m_recoverable_candidates_deduction_id ........... [RUN]
21:23:41  114 of 115 START test unique_m_recoverable_candidates_deduction_id ............. [RUN]
21:23:41  115 of 115 START test unique_combination_m_deductions_monthly_retailer_id__reason_code__deduction_month  [RUN]
21:23:41  113 of 115 PASS not_null_m_recoverable_candidates_deduction_id ................. [PASS in 0.03s]
21:23:41  115 of 115 PASS unique_combination_m_deductions_monthly_retailer_id__reason_code__deduction_month  [PASS in 0.02s]
21:23:41  114 of 115 PASS unique_m_recoverable_candidates_deduction_id ................... [PASS in 0.03s]
21:23:41  
21:23:41  Finished running 1 project hook, 8 table models, 90 data tests, 17 view models in 0 hours 0 minutes and 1.42 seconds (1.42s).
21:23:41  
21:23:41  Completed successfully
21:23:41  
21:23:41  Done. PASS=116 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=116

$ .venv/bin/python -m forecast.run
months=33 folds=252 pooled MAPE: seasonal_naive=0.189, holt_winters=0.186
wrote forecast/results and forecast/RESULTS.md

$ .venv/bin/pytest
........................................................................ [ 30%]
........................................................................ [ 61%]
........................................................................ [ 91%]
....................                                                     [100%]
236 passed in 87.98s (0:01:27)

```

```
