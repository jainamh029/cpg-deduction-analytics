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

