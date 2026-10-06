# Build log

Real command output captured at each phase gate (`scripts/gate.sh`). Data is synthetic.

## Phase 1: Synthetic data generator

Run on 2026-10-06 15:43 EDT. Output trimmed to the last lines of each command.

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
18 files already formatted

$ .venv/bin/pytest
...........................                                              [100%]
27 passed in 6.78s

```

## Phase 2: Warehouse + dbt models

Run on 2026-10-06 15:45 EDT. Output trimmed to the last lines of each command.

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
21 files already formatted

$ .venv/bin/python -m data_gen.load
wrote warehouse/warehouse.duckdb

$ .venv/bin/dbt build
19:45:43  92 of 94 START test relationships_fct_disputes_deduction_id__deduction_id__ref_fct_deductions_  [RUN]
19:45:43  93 of 94 START test unique_fct_disputes_deduction_id ........................... [RUN]
19:45:43  91 of 94 PASS not_null_fct_disputes_dispute_id ................................. [PASS in 0.02s]
19:45:43  90 of 94 PASS accepted_values_fct_disputes_outcome__won__partial__lost__pending  [PASS in 0.02s]
19:45:43  92 of 94 PASS relationships_fct_disputes_deduction_id__deduction_id__ref_fct_deductions_  [PASS in 0.02s]
19:45:43  93 of 94 PASS unique_fct_disputes_deduction_id ................................. [PASS in 0.02s]
19:45:43  94 of 94 START test unique_fct_disputes_dispute_id ............................. [RUN]
19:45:43  94 of 94 PASS unique_fct_disputes_dispute_id ................................... [PASS in 0.01s]
19:45:43  
19:45:43  Finished running 6 table models, 76 data tests, 12 view models in 0 hours 0 minutes and 0.80 seconds (0.80s).
19:45:43  
19:45:43  Completed successfully
19:45:43  
19:45:43  Done. PASS=94 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=94

$ .venv/bin/pytest
......................................                                   [100%]
38 passed in 7.60s

```

## Phase 3: Metrics layer

Run on 2026-10-06 15:50 EDT. Output trimmed to the last lines of each command.

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
24 files already formatted

$ .venv/bin/python -m data_gen.load
wrote warehouse/warehouse.duckdb

$ .venv/bin/dbt build
19:49:52  110 of 113 PASS unique_m_reason_recovery_reason_code ........................... [PASS in 0.02s]
19:49:52  109 of 113 PASS unique_combination_m_deductions_monthly_retailer_id__reason_code__deduction_month  [PASS in 0.02s]
19:49:52  111 of 113 START sql view model metrics.m_recoverable_candidates ............... [RUN]
19:49:52  111 of 113 OK created sql view model metrics.m_recoverable_candidates .......... [OK in 0.01s]
19:49:52  112 of 113 START test not_null_m_recoverable_candidates_deduction_id ........... [RUN]
19:49:52  113 of 113 START test unique_m_recoverable_candidates_deduction_id ............. [RUN]
19:49:53  112 of 113 PASS not_null_m_recoverable_candidates_deduction_id ................. [PASS in 0.03s]
19:49:53  113 of 113 PASS unique_m_recoverable_candidates_deduction_id ................... [PASS in 0.03s]
19:49:53  
19:49:53  Finished running 1 project hook, 6 table models, 89 data tests, 18 view models in 0 hours 0 minutes and 1.29 seconds (1.29s).
19:49:53  
19:49:53  Completed successfully
19:49:53  
19:49:53  Done. PASS=114 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=114

$ .venv/bin/pytest
.......................ss............................................... [ 98%]
.                                                                        [100%]
71 passed, 2 skipped in 10.97s

```

## Phase 4: Analysis SQL

Run on 2026-10-06 15:55 EDT. Output trimmed to the last lines of each command.

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
27 files already formatted

$ .venv/bin/python -m data_gen.load
wrote warehouse/warehouse.duckdb

$ .venv/bin/dbt build
19:55:20  109 of 113 PASS unique_m_reason_recovery_reason_code ........................... [PASS in 0.02s]
19:55:20  110 of 113 PASS unique_combination_m_deductions_monthly_retailer_id__reason_code__deduction_month  [PASS in 0.02s]
19:55:20  111 of 113 START sql view model metrics.m_recoverable_candidates ............... [RUN]
19:55:20  111 of 113 OK created sql view model metrics.m_recoverable_candidates .......... [OK in 0.01s]
19:55:20  112 of 113 START test not_null_m_recoverable_candidates_deduction_id ........... [RUN]
19:55:20  113 of 113 START test unique_m_recoverable_candidates_deduction_id ............. [RUN]
19:55:20  112 of 113 PASS not_null_m_recoverable_candidates_deduction_id ................. [PASS in 0.03s]
19:55:20  113 of 113 PASS unique_m_recoverable_candidates_deduction_id ................... [PASS in 0.03s]
19:55:20  
19:55:20  Finished running 1 project hook, 8 table models, 89 data tests, 16 view models in 0 hours 0 minutes and 1.35 seconds (1.35s).
19:55:20  
19:55:20  Completed successfully
19:55:20  
19:55:20  Done. PASS=114 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=114

$ .venv/bin/pytest
.......................................................s................ [ 69%]
................................                                         [100%]
103 passed, 1 skipped in 11.43s

```

## Phase 5: Forecast

Run on 2026-10-06 15:58 EDT. Output trimmed to the last lines of each command.

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
32 files already formatted

$ .venv/bin/python -m data_gen.load
wrote warehouse/warehouse.duckdb

$ .venv/bin/dbt build
19:58:40  110 of 113 PASS unique_m_reason_recovery_reason_code ........................... [PASS in 0.02s]
19:58:40  108 of 113 PASS unique_combination_m_deductions_monthly_retailer_id__reason_code__deduction_month  [PASS in 0.02s]
19:58:40  111 of 113 START sql view model metrics.m_recoverable_candidates ............... [RUN]
19:58:40  111 of 113 OK created sql view model metrics.m_recoverable_candidates .......... [OK in 0.01s]
19:58:40  112 of 113 START test not_null_m_recoverable_candidates_deduction_id ........... [RUN]
19:58:40  113 of 113 START test unique_m_recoverable_candidates_deduction_id ............. [RUN]
19:58:40  112 of 113 PASS not_null_m_recoverable_candidates_deduction_id ................. [PASS in 0.03s]
19:58:40  113 of 113 PASS unique_m_recoverable_candidates_deduction_id ................... [PASS in 0.03s]
19:58:40  
19:58:40  Finished running 1 project hook, 8 table models, 89 data tests, 16 view models in 0 hours 0 minutes and 1.33 seconds (1.33s).
19:58:40  
19:58:40  Completed successfully
19:58:40  
19:58:40  Done. PASS=114 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=114

$ .venv/bin/python -m forecast.run
months=33 folds=252 pooled MAPE: seasonal_naive=0.189, holt_winters=0.186
wrote forecast/results and forecast/RESULTS.md

$ .venv/bin/pytest
................................................................s....... [ 63%]
.........................................                                [100%]
112 passed, 1 skipped in 13.81s

```

## Phase 6: Dashboard (Streamlit)

Run on 2026-10-06 16:04 EDT. Output trimmed to the last lines of each command.

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
43 files already formatted

$ .venv/bin/python -m data_gen.load
wrote warehouse/warehouse.duckdb

$ .venv/bin/dbt build
20:04:38  112 of 115 OK created sql view model metrics.m_recoverable_candidates .......... [OK in 0.01s]
20:04:38  107 of 115 OK created sql view model metrics.m_deductions_monthly .............. [OK in 0.11s]
20:04:38  113 of 115 START test not_null_m_recoverable_candidates_deduction_id ........... [RUN]
20:04:38  114 of 115 START test unique_m_recoverable_candidates_deduction_id ............. [RUN]
20:04:38  115 of 115 START test unique_combination_m_deductions_monthly_retailer_id__reason_code__deduction_month  [RUN]
20:04:38  113 of 115 PASS not_null_m_recoverable_candidates_deduction_id ................. [PASS in 0.03s]
20:04:38  115 of 115 PASS unique_combination_m_deductions_monthly_retailer_id__reason_code__deduction_month  [PASS in 0.03s]
20:04:38  114 of 115 PASS unique_m_recoverable_candidates_deduction_id ................... [PASS in 0.03s]
20:04:38  
20:04:38  Finished running 1 project hook, 8 table models, 90 data tests, 17 view models in 0 hours 0 minutes and 1.31 seconds (1.31s).
20:04:38  
20:04:38  Completed successfully
20:04:38  
20:04:38  Done. PASS=116 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=116

$ .venv/bin/python -m forecast.run
months=33 folds=252 pooled MAPE: seasonal_naive=0.189, holt_winters=0.186
wrote forecast/results and forecast/RESULTS.md

$ .venv/bin/pytest
........................................................................ [ 53%]
..............................................................           [100%]
134 passed in 15.20s

```

## Phase 7: CI workflow, hygiene tests

Run on 2026-10-06 16:05 EDT. Output trimmed to the last lines of each command.

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
44 files already formatted

$ .venv/bin/python -m data_gen.load
wrote warehouse/warehouse.duckdb

$ .venv/bin/dbt build
20:05:35  112 of 115 OK created sql view model metrics.m_recoverable_candidates .......... [OK in 0.01s]
20:05:35  107 of 115 OK created sql view model metrics.m_deductions_monthly .............. [OK in 0.12s]
20:05:35  113 of 115 START test not_null_m_recoverable_candidates_deduction_id ........... [RUN]
20:05:35  114 of 115 START test unique_m_recoverable_candidates_deduction_id ............. [RUN]
20:05:35  115 of 115 START test unique_combination_m_deductions_monthly_retailer_id__reason_code__deduction_month  [RUN]
20:05:35  113 of 115 PASS not_null_m_recoverable_candidates_deduction_id ................. [PASS in 0.05s]
20:05:35  115 of 115 PASS unique_combination_m_deductions_monthly_retailer_id__reason_code__deduction_month  [PASS in 0.05s]
20:05:35  114 of 115 PASS unique_m_recoverable_candidates_deduction_id ................... [PASS in 0.05s]
20:05:35  
20:05:35  Finished running 1 project hook, 8 table models, 90 data tests, 17 view models in 0 hours 0 minutes and 1.49 seconds (1.49s).
20:05:35  
20:05:35  Completed successfully
20:05:35  
20:05:35  Done. PASS=116 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=116

$ .venv/bin/python -m forecast.run
months=33 folds=252 pooled MAPE: seasonal_naive=0.189, holt_winters=0.186
wrote forecast/results and forecast/RESULTS.md

$ .venv/bin/pytest
........................................................................ [ 50%]
.......................................................................  [100%]
143 passed in 15.55s

```

## Phase 7b: fresh clone, `make all`

Run in a new temp directory after `git clone`; trimmed to key lines.

```
.venv/bin/ruff check .
All checks passed!
.venv/bin/ruff format --check .
44 files already formatted
wrote warehouse/warehouse.duckdb
20:06:33  Done. PASS=116 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=116
months=33 folds=252 pooled MAPE: seasonal_naive=0.189, holt_winters=0.186
wrote forecast/results and forecast/RESULTS.md
143 passed in 15.60s
make all   35.65s user 5.49s system 55% cpu 1:13.92 total
exit code: 0
```

## Phase 8: Findings memo README

Run on 2026-10-06 16:13 EDT. Output trimmed to the last lines of each command.

```
$ .venv/bin/ruff check .
All checks passed!

$ .venv/bin/ruff format --check .
51 files already formatted

$ .venv/bin/python -m data_gen.load
wrote warehouse/warehouse.duckdb

$ .venv/bin/dbt build
20:13:06  111 of 115 PASS not_null_m_reason_recovery_reason_code ......................... [PASS in 0.02s]
20:13:06  112 of 115 PASS unique_m_reason_recovery_reason_code ........................... [PASS in 0.02s]
20:13:06  113 of 115 START sql view model metrics.m_recoverable_candidates ............... [RUN]
20:13:06  113 of 115 OK created sql view model metrics.m_recoverable_candidates .......... [OK in 0.01s]
20:13:06  114 of 115 START test not_null_m_recoverable_candidates_deduction_id ........... [RUN]
20:13:06  115 of 115 START test unique_m_recoverable_candidates_deduction_id ............. [RUN]
20:13:06  114 of 115 PASS not_null_m_recoverable_candidates_deduction_id ................. [PASS in 0.01s]
20:13:06  115 of 115 PASS unique_m_recoverable_candidates_deduction_id ................... [PASS in 0.02s]
20:13:06  
20:13:06  Finished running 1 project hook, 8 table models, 90 data tests, 17 view models in 0 hours 0 minutes and 1.43 seconds (1.43s).
20:13:06  
20:13:06  Completed successfully
20:13:06  
20:13:06  Done. PASS=116 WARN=0 ERROR=0 SKIP=0 NO-OP=0 REUSED=0 TOTAL=116

$ .venv/bin/python -m forecast.run
months=33 folds=252 pooled MAPE: seasonal_naive=0.189, holt_winters=0.186
wrote forecast/results and forecast/RESULTS.md

$ .venv/bin/pytest
........................................................................ [ 48%]
........................................................................ [ 96%]
......                                                                   [100%]
150 passed in 16.94s

```

## Phase 8b: scripts/verify_readme.py (independent recomputation from RAW tables)

```
ok   headline.gross                           independent=4.63964e+08      findings=4.63964e+08      README shows '$464.0M': True
ok   headline.deductions                      independent=2.38249e+07      findings=2.38249e+07      README shows '$23.8M': True
ok   headline.deduction_rate                  independent=0.0513507        findings=0.0513507        README shows '5.1%': True
ok   headline.recovered                       independent=2.21239e+06      findings=2.21239e+06      README shows '$2.2M': True
ok   headline.net_leakage                     independent=2.16125e+07      findings=2.16125e+07      README shows '$21.6M': True
ok   headline.recoverable_180_base            independent=920158           findings=920158           README shows '$920K': True
ok   finding1.shortage_dispute_rate           independent=0.167801         findings=0.167801         README shows '17%': True
ok   finding1.shortage_win_rate               independent=0.803215         findings=0.803215         README shows '80%': True
ok   finding2.ratio_to_peers                  independent=3.66433          findings=3.66433          README shows '3.7x': True
ok   finding2.top2_share_of_attributed        independent=0.705907         findings=0.705907         README shows '71%': True
ok   finding2.top2_share_of_all               independent=0.572172         findings=0.572172         README shows '57%': True
ok   finding3.median_spike_index              independent=2.18782          findings=2.18782          README shows '2.2x': True
ok   also.lag_change_6m                       independent=9.10643          findings=9.10643          README shows '9.1': True
ok   data_quality.sku_null_rate_count         independent=0.493287         findings=0.493287         README shows '49.3%': True
ok   data_quality.sku_null_rate_amount        independent=0.532685         findings=0.532685         README shows '53.3%': True
ok   forecast.pooled_mape_hw                  independent=0.186364         findings=0.186364         README shows '18.6%': True
ok   forecast.pooled_mape_naive               independent=0.188509         findings=0.188509         README shows '18.9%': True
0 failure(s)
```

