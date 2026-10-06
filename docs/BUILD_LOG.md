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
wrote /Users/jainamshah/cpg-deduction-analytics/warehouse/warehouse.duckdb

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
wrote /Users/jainamshah/cpg-deduction-analytics/warehouse/warehouse.duckdb

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
wrote /Users/jainamshah/cpg-deduction-analytics/warehouse/warehouse.duckdb

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

