# Audit report

> Independent audit of the SYNTHETIC-data project "CPG Deduction & Trade Spend Analytics" (branch `audit`). All data is
> synthetic; nothing here is about a real company. Evidence for every claim is in [AUDIT_LOG.md](AUDIT_LOG.md) (real command output),
> `docs/audit/*.json` (raw sweep, bias and mutation results) and the commit named in each row. Design choices and test
> changes are in [DECISIONS.md](DECISIONS.md) D42-D51.

## Summary

- **The project's own validation was partly circular.** On 20 generated datasets with *no* planted effect, the original
  "under-invested" detector flagged a reason in **19 of 20** and the anomaly detector flagged **25.6** cells per dataset
  (1.7% of cells). Both were fixed (thresholds justified from the null runs); after the fix: **0 of 20** and **3.1** cells per dataset, while every planted pattern is still found on 20 of 20
  datasets (the one-off anomaly 19 of 20).
- **The headline "recoverable now" figure was a point estimate that assumed undisputed deductions win like disputed ones.** A selection-bias simulation with a known oracle
  shows the true value of the same deductions is 76% to 98% of the historical-rate estimate; the same method returns about $0.64M on data with no planted effect. It is now a range with its sensitivity.
- **The test suite is strong on what it tests.** 42 hand-written mutations: baseline **28 of 30** killed (the two survivors were LEFT-to-INNER joins that clean data never exercises); after the audit's fixes and tests **42 of 42**. `mutmut` on the forecast module: **55% of 564 mutants killed, 66% after adding hand-computed tests** (88% of the 420 mutants reachable by the selected tests).
- **Real bugs found and fixed:** recoveries could exceed the deduction (net revenue above gross); two analyses compared a month with the previous *row* instead of the previous calendar month; dirty source data could reach dbt; the README verifier covered 17 of 109 numbers; a division by zero in my own forecast comparison.
- **What remains open** is listed at the end: censoring bias in days-to-resolve and win rate, undeduplicated duplicate deductions, no receivable-balance metric, a partial warehouse after a killed `dbt build`, a thin fine-ratio margin, a regex-based hygiene test, unverified CI and Metabase.
- **Final gate** (ruff, format, 236 pytest tests, dbt build with 116 nodes, `make all` from two fresh clones in a path containing a space): all green, outputs byte-identical (see the end of this report).

## Findings

Severity: **Critical** = would make a headline claim wrong or misleading to a skeptical reviewer; **High** = a real defect or a gap that hides defects; **Medium** = correctness or reproducibility risk with a bounded effect; **Low** = hygiene or limitation.

| # | Sev | Finding | Evidence | Status |
|---|---|---|---|---|
| 1 | Critical | Analysis 06 flagged an "under-invested" reason on 19/20 datasets with no planted effect (bare "above average" rule); analysis 07 flagged 25.6 cells/dataset at \|z\|>=3 (a 12-point baseline gives t(11): 1.2% chance rate) | `docs/audit/null_before.json`; AUDIT_LOG 2a | **FIXED** `9e920bf`: win margin of 10 points plus below-median dispute rate; \|z\|>=4.5. After: 0/20 and 3.1 cells (`null_after.json`); regression tests `test_null_pipeline.py`, mutations M38/M39 |
| 2 | Critical | "Recoverable now $920K" was a point estimate assuming disputed = undisputed win rates; the 0.5/0.75/1.0 factors were unevidenced; the same figure appears on null data | `bias_results.json`: implied factor 0.98 (no selection), 0.87, 0.80, 0.76 (strong); null mean $0.64M | **FIXED** `c5daa54`, `0f6565e`: README range, bias simulation, null comparison, sensitivity grid (AUDIT_LOG 2d). The real selection strength remains unknown (OPEN as a limitation) |
| 3 | Critical | README presented synthetic results as real-world findings ("$21.6M was lost net", "$7.2M a year", unconditional actions) | `git diff 53cff79..c5daa54 -- docs/README.template.md` | **FIXED** `c5daa54`: "synthetic dataset", "to date", "if this pattern appeared in real data" |
| 4 | High | Re-filed disputes could recover more than the deduction (240 of 200), pushing net revenue above gross | `test_messy_conditions.py::test_recoveries_on_a_deduction_are_capped...` failed with 240 before the fix | **FIXED** `813cdff` (cap in `int_deduction_disputes`; validator rules `multiple_disputes_per_deduction`, `recon_recovered_total_exceeds_deduction`); mutation M31 |
| 5 | High | Analyses 02 and 08 used row-based `LAG`: a retailer with a gap month got a wrong month-over-month change | old query returned 0.0 where NULL is correct (`test_analysis_08_lag_across_a_gap...`) | **FIXED** `da43f1b` (calendar scaffold); mutation M32 |
| 6 | High | No validation gate: dirty source data reached dbt. With the gate bypassed, dbt fails at staging and skips marts, leaving the previous build's marts in place (stale) | `test_bypassing_the_gate...`; AUDIT_LOG 4b | **FIXED** `d151282`: `make build` runs the validator first and stops on any finding; mutation M33 |
| 7 | High | Two mutation survivors (LEFT to INNER joins in `fct_deductions`, `fct_disputes`): clean data has no orphans, so the suite could not see them | baseline 28/30 | **FIXED** `813cdff` (messy fixture with an orphaned deduction and dispute); final 42/42 |
| 8 | High | `verify_readme.py` checked 17 README numbers; the README showed about 100 | `scripts/verify_readme.py` before/after | **FIXED** `c5daa54`: 109 tokens independently recomputed + registry for typed numbers; negative-control tests |
| 9 | High | Forecast: reported "better for 8 of 12 retailers" and MAPE only; no uncertainty; the dashboard band was only checked in-sample | `forecast/RESULTS.md` | **FIXED** `93ab896`, `c5daa54`: sMAPE, MASE, origin bootstrap (95% CI -2.2 to +2.7 points, p=0.89), DM p=0.92: a statistical tie. Band covers 77.3% out of sample vs 80% nominal (OPEN: reported, not corrected) |
| 10 | Medium | Headline deduction rate is right-censored (5.14% all-period vs 5.34% on mature months) | AUDIT_LOG; `m_retailer_month` | **FIXED** `c5daa54` (both shown); `is_mature_month` already existed |
| 11 | Medium | `data_gen.load` rebuilt the warehouse in place; a kill left a partial file | `test_a_killed_data_load...` | **FIXED** `97a8490` (temp file + rename); mutation M42 |
| 12 | Medium | A killed `dbt build` leaves a partial warehouse (0 / 1 / 13 of the mart and metric objects after 1 / 2 / 3 s of a 3.2 s build) | AUDIT_LOG 4c; `test_a_killed_dbt_build...` | **OPEN**: rerunning restores an identical warehouse (tested); a build-to-staging-schema-then-swap would remove the window |
| 13 | Medium | Dependencies were ranges; transitive packages unpinned | `pyproject.toml` before | **FIXED** `97a8490`: exact pins plus `requirements.lock`; enforced by a test |
| 14 | Medium | Duplicate deductions are counted twice (flagged by the validator, never removed) | `test_duplicate_deductions_are_counted_twice...` | **OPEN**: needs a business definition of "duplicate" |
| 15 | Medium | Days to resolve and win rate cover resolved disputes only: biased toward fast outcomes (fixture: resolved-only mean 20 days while pending disputes are already 60 and 162 days old) | `test_win_rate_excludes_pending_and_days_to_resolve_is_biased_low...` | **OPEN** (documented in METRICS.md): needs survival analysis |
| 16 | Medium | Partial payments: lag uses the final payment date for the whole amount; there is no receivable-balance metric | `test_partial_payments_use_the_final_payment_date...` | **OPEN** (documented) |
| 17 | Medium | Fine-outlier threshold 2.0x has a thin margin (null max 1.98x, planted min 2.04x) | `docs/audit/summary.json` | **OPEN**: reported in the README and analysis header |
| 18 | Low | "Metrics defined once" is enforced by regex heuristics | `tests/test_hygiene.py`; M22 caught by it (and by a data test) | **OPEN** |
| 19 | Low | Many first-failing tests for join mutations are generic (the fixture's dbt data tests fail), not semantic assertions | mutation table | **OPEN** (observation) |
| 20 | Low | Returns, credit memos, chargebacks are not representable (negative amounts rejected) | `test_credit_memos_and_returns_are_not_representable` | **WON'T FIX**: out of scope; limits every net-revenue claim (stated in METRICS.md and README) |
| 21 | Low | GitHub Actions CI never run; Metabase never built; only macOS arm64 tested | n/a | **OPEN**: cannot be verified in this environment |
| 22 | Low | mutmut: 144 of 564 mutants sit in code only exercised by warehouse-dependent tests; 50 survivors remain (`compare_models` 19, `holt_winters` 18, `interval_coverage` 9) | AUDIT_LOG 1d | **OPEN** (reported, not chased) |

Checked and found fine: dashboard page load (data functions 12-14 ms; Chrome until all charts render 0.4 s warm, 1.2 s cold, all under 3 s, so no caching change was needed); every dashboard query uses bound parameters (a hostile filter value never appears in SQL text and no table was touched); `dbt docs generate` works and every dbt model states a grain; no absolute paths, secrets or large files tracked; reproducibility from two fresh clones in a path with a space.

## Audit 1: mutation testing

Method: `scripts/mutation_audit.py` edits one source file at a time (restoring it afterwards), runs `pytest -x` (cheap test files first) and records the first failing test.
**Kill rate: baseline 28/30 (93%); final 42/42 (100%).** "Caught by" is the *first failing test*, which for join mutations is often generic: the fixture's `dbt build` fails its data tests.

| ID | Mutation | Caught by (first failing test) | Baseline | Final |
|---|---|---|---|---|
| M01 | fan-out: fct_deductions joined to invoice lines (deduction x ~10 lines) | t_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql] | KILLED | KILLED |
| M02 | fan-out: fct_invoices joined to raw deductions (gross repeated per deduction) | t_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql] | KILLED | KILLED |
| M03 | LEFT JOIN -> INNER JOIN: fct_invoices drops unpaid invoices | t_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql] | KILLED | KILLED |
| M04 | LEFT JOIN -> INNER JOIN: fct_deductions drops orphaned deductions | t_messy_conditions.py::test_orphans_are_retained_not_silently_dropped_by_the_marts | SURVIVED | KILLED |
| M05 | LEFT JOIN -> INNER JOIN: fct_disputes drops disputes without a deduction row | t_messy_conditions.py::test_orphans_are_retained_not_silently_dropped_by_the_marts | SURVIVED | KILLED |
| M06 | aging boundary 30/31 (<= 30 -> < 30) | t_analysis.py::test_04_open_balance_and_buckets_match_raw | KILLED | KILLED |
| M07 | aging boundary 60/61 (<= 60 -> < 60) | t_analysis.py::test_04_open_balance_and_buckets_match_raw | KILLED | KILLED |
| M08 | aging boundary 90/91 (<= 90 -> < 90) | t_analysis.py::test_04_open_balance_and_buckets_match_raw | KILLED | KILLED |
| M09 | deduction rate: wrong denominator (gross + deductions) | t_analysis.py::test_02_rate_trend_rows_values_and_ranks | KILLED | KILLED |
| M10 | recovery rate: wrong denominator (recovered + deducted) | t_analysis.py::test_10_recoverable_dollars_match_independent_computation | KILLED | KILLED |
| M11 | win rate: wrong denominator (resolved + wins) | t_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more | KILLED | KILLED |
| M12 | unattributed SKU bucket dropped from dim_sku (key -1 -> -2) | t_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql] | KILLED | KILLED |
| M13 | NULL sku_id no longer mapped to the bucket in fct_deductions | t_analysis.py::test_file_header_and_execution[01_gross_to_net_waterfall.sql] | KILLED | KILLED |
| M14 | unresolved (pending) disputes counted as resolved/lost | t_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more | KILLED | KILLED |
| M15 | today's date instead of the fixed as-of date in ageing | t_analysis.py::test_04_open_balance_and_buckets_match_raw | KILLED | KILLED |
| M16 | z-score baseline includes the current month (11 preceding .. current row) | t_analysis.py::test_file_header_and_execution[07_anomaly_zscores.sql] | KILLED | KILLED |
| M17 | z-score sign flipped | t_analysis.py::test_07_anomalies_find_the_planted_event_and_not_too_many_others | KILLED | KILLED |
| M18 | forecast leakage: training fold includes the origin month | t_forecast.py::test_every_fold_trains_only_on_months_before_its_origin | KILLED | KILLED |
| M19 | dashboard: reason filter silently ignored in every page query | t_dashboard.py::test_filters_move_results_in_the_expected_direction | KILLED | KILLED |
| M20 | duplicate payments double-count (payments unioned with themselves) | t_models.py::test_payments_reconcile_to_raw | KILLED | KILLED |
| M21 | metric macro changed in one place: partial wins no longer wins | t_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more | KILLED | KILLED |
| M22 | analysis 05 re-derives a bucket label instead of using the metrics layer | t_analysis.py::test_05_filing_lag_cohorts_match_raw_and_faster_wins_more | KILLED | KILLED |
| M23 | net revenue formula subtracts recoveries | t_analysis.py::test_01_waterfall_components_sum_to_net_and_match_raw | KILLED | KILLED |
| M24 | open balance ignores pending-dispute deductions | t_analysis.py::test_04_open_balance_and_buckets_match_raw | KILLED | KILLED |
| M25 | recoverable candidates include accepted (verified-valid) deductions | t_analysis.py::test_10_recoverable_dollars_match_independent_computation | KILLED | KILLED |
| M26 | seasonal naive off by one month | t_forecast.py::test_seasonal_naive_matches_hand_computed_values | KILLED | KILLED |
| M27 | generator: Retailer A fine multiplier 3 -> 1 (pattern 1 removed) | t_analysis.py::test_03_fine_outlier_and_sku_concentration_with_unattributed_bucket | KILLED | KILLED |
| M28 | validator: duplicate-payment rule threshold off (> 1 -> > 2) | t_validator.py::test_dirty_load_has_exactly_the_injected_defects | KILLED | KILLED |
| M29 | days to resolve: arguments reversed (negative days) | t_metrics.py::test_6_days_to_resolve | KILLED | KILLED |
| M30 | payment lag no longer weighted by amount paid | t_analysis.py::test_08_payment_lag_drift_flags_retailer_b_and_matches_raw | KILLED | KILLED |
| M31 | recovery cap removed: re-filed disputes can recover more than the deduction | t_messy_conditions.py::test_recoveries_on_a_deduction_are_capped_at_its_amount | n/a (added later) | KILLED |
| M32 | analysis 02: calendar scaffold join made inner (gap months vanish, LAG skips them) | t_messy_conditions.py::test_analysis_02_lag_means_previous_calendar_month_across_a_gap | n/a (added later) | KILLED |
| M33 | make build no longer runs the validation gate | t_pipeline_robustness.py::test_make_build_runs_the_validation_gate_before_dbt | n/a (added later) | KILLED |
| M34 | validator: duplicate-deduction rule threshold off (> 1 -> > 2) | t_messy_conditions.py::test_validator_flags_exactly_the_messy_conditions | n/a (added later) | KILLED |
| M35 | dashboard: retailer filter ignored (always retailer 1) | t_dashboard.py::test_filters_move_results_in_the_expected_direction | n/a (added later) | KILLED |
| M36 | forecast: sMAPE missing its factor of 2 | t_forecast.py::test_smape_and_mase_match_hand_computed_values | n/a (added later) | KILLED |
| M37 | forecast: MASE scale ignores the seasonal lag (lag 1 instead of 12) | t_forecast.py::test_smape_and_mase_match_hand_computed_values | n/a (added later) | KILLED |
| M38 | analysis 06: under-invested margin removed (0.10 -> 0.0), the null-data false-positive fix undone | t_null_pipeline.py::test_no_reason_is_called_under_invested_on_null_data[1] | n/a (added later) | KILLED |
| M39 | analysis 07: z threshold back to 3 (null-data false positives return) | t_analysis.py::test_07_anomalies_find_the_planted_event_and_not_too_many_others | n/a (added later) | KILLED |
| M40 | recovery scenarios: base realization factor 0.75 -> 0.70 | t_analysis.py::test_10_recoverable_dollars_match_independent_computation | n/a (added later) | KILLED |
| M41 | generator: Retailer B lag drift removed (pattern 4) | t_findings.py::test_readme_numbers_match_independent_raw_table_sql | n/a (added later) | KILLED |
| M42 | atomic load replaced by an in-place rebuild of the final file | t_pipeline_robustness.py::test_a_killed_data_load_never_corrupts_the_existing_warehouse_and_a_rerun_recovers | n/a (added later) | KILLED |

**mutmut 3.8.0** on `forecast/model.py` (pure-function forecast tests only): before the audit's new tests 310 killed / 110 survived / 144 not covered of 564 (55%); after 370 / 50 / 144 (66%; 88% of reachable). A mutation score measures test strength, not whether definitions are right.

## Audit 2: is the planted-signal validation circular?

**Null datasets** (`Config(planted=False)`: same volume and noise, flat revenue, no fine excess, no promo spike, no lag drift, no anomaly, identical dispute and win rates for every reason, no filing-lag effect), 20 seeds:

| | Before the fix | After the fix |
|---|---|---|
| Datasets where analysis 06 flags an "under-invested" reason | 19 / 20 (1.65 reasons per dataset) | 0 / 20 |
| Anomaly cells flagged per dataset (of 1,512) | 25.6 (range 18-31) | 3.1 (range 1-5) |
| Fine outlier called (>= 2.0x peers) | 0 / 20 (max ratio 1.98x) | 0 / 20 |
| Promo spike called (median >= 1.5x) | 0 / 20 (max 1.27x) | 0 / 20 |
| Lag drift called (>= 5 days) | 0 / 20 (max 1.5 days) | 0 / 20 |
| "Recoverable now" (base, 180 days), mean | $0.64M | $0.64M |

The recoverable-dollar figure does not fall on null data: it measures volume and rates, not evidence of a pattern.

**Seed sweep** (20 planted seeds, after the fixes; `docs/audit/planted_after.json`):

| Pattern | Effect | Detected | Mean | Min | Max | False positives (sum / mean) |
|---|---|---|---|---|---|---|
| p1 | Retailer A fines vs peers (x) | 20/20 | 2.910 | 2.039 | 3.563 | 0 |
| p2 | Jan-Feb promo spike (x) | 20/20 | 2.445 | 2.057 | 2.792 | None |
| p3 | Shortage win rate | 20/20 | 0.771 | 0.753 | 0.807 | 0 |
| p4 | Retailer B lag change over 6 months (days) | 20/20 | 9.114 | 8.007 | 9.641 | 0 |
| p5 | YoY revenue growth | 20/20 | 0.079 | 0.071 | 0.088 | None |
| p7 | Planted anomaly flagged (abs z >= 4.5) | 19/20 | 6.000 | 2.000 | 11.000 | 4.85 |

Aggregate behaviour is asserted in `tests/test_audit_modes.py` (generator-level, 20 seeds, planted found on >= 19, null quiet on >= 19) and `tests/test_null_pipeline.py` (full pipeline, 2 null seeds).

**Dispute selection bias** (`Config(dispute_bias=b)`; oracle value of the same 180-day candidates vs the historical-rate estimate, 3 seeds per level):

| Selection strength | Implied realization factor (truth / estimate) | Shortage win rate seen on disputed | True win prob. of undisputed shortages |
|---|---|---|---|
| off | 0.98 | 0.77 | 0.77 |
| 0 | 0.98 | 0.77 | 0.76 |
| 0.5 | 0.87 | 0.81 | 0.75 |
| 1 | 0.80 | 0.86 | 0.75 |
| 1.5 | 0.76 | 0.88 | 0.75 |

So under strong selection the estimate overstates by about a third and the observed shortage win rate rises from 0.77 to 0.89 while the true value stays near 0.75.

**Sensitivity of the estimate** (historical-rate value of never-disputed deductions x realization factor, $M):

| Dispute window (days) | x0.25 | x0.5 | x0.75 | x1.0 |
|---|---|---|---|---|
| 60 | 0.13 | 0.26 | 0.39 | 0.52 |
| 90 | 0.17 | 0.35 | 0.52 | 0.70 |
| 120 | 0.22 | 0.44 | 0.66 | 0.88 |
| 180 | 0.31 | 0.61 | 0.92 | 1.23 |
| 270 | 0.44 | 0.88 | 1.33 | 1.77 |
| 365 | 0.65 | 1.30 | 1.95 | 2.60 |

The dispute window matters more than the haircut: going from 90 to 365 days multiplies the estimate by 3.7; going from 0.25 to 1.0 multiplies it by 4.

## Audit 3: metrics under messy conditions

Full table with test names: [METRICS.md](METRICS.md#messy-real-world-conditions-audit). In short: **handled** partial payments (by definition), several deductions per invoice, orphans (after the mutation test), cohort vs period basis, NULL/zero denominators, month-end dates; **was wrong, fixed**: re-filed disputes (recoveries above the deduction), row-based LAG across gaps; **unhandled in metrics but flagged and gated**: duplicate deductions, resolved-before-filed, deduction-before-invoice; **biased, documented**: days to resolve and win rate under right-censoring; **not modelled**: credit memos, returns, chargebacks. 15 fixture tests with hand arithmetic in `tests/test_messy_conditions.py`.

## Audit 4: end-to-end pipeline

- Fresh clone in a directory whose path contains a space, `make all` twice: both exit 0, 236 tests pass, **29 table fingerprints identical, 12 generated output files byte-identical, 0 tracked files modified** (log below).
- Dirty source: the validator finds exactly the injected defects; `make build` now stops there. Bypassing the gate: dbt fails at staging, marts stay stale (finding 6).
- Idempotency: data stage, dbt stage run twice give identical fingerprints (test). Kill/restart: a killed load leaves the old warehouse untouched; a killed `dbt build` leaves a partial warehouse that a rerun repairs (finding 12).
- Inflation: metrics layer row counts and totals match raw tables with independent queries (`test_metrics_layer_row_counts_and_totals_match_raw_tables`).
- Hygiene: no absolute paths, secrets or large binaries tracked; dependencies exactly pinned and locked; `dbt docs generate` works and every model states a grain (tests).

## Audit 5: forecast

Fold construction (`forecast/model.py::backtest`): 7 origins (24..30 of 33 months), horizon 3, expanding window; training is `monthly.iloc[:origin]` and nothing at or after the origin reaches a model. Leakage is covered by a spy test, a "change the last three months" invariance test and mutation M18. MAPE for small series: percentage errors for the 3 smallest retailers are about twice those of the 3 largest (26% vs 13%), so sMAPE, MASE and WAPE are shown beside MAPE. Holt-Winters vs seasonal naive: pooled MAPE 18.6% vs 18.9%, origin-bootstrap 95% CI -2.2 to +2.7 points (p = 0.89), Diebold-Mariano (HLN) p = 0.92, better at 3 of 7 origins and 8 of 12 retailers (sign test p = 0.39): **a statistical tie**. The 80% band covered 77.3% of backtest points out of sample. The README now says all of this.

## Audit 6: dashboard

23 headless AppTest cases (3 pages x default / single retailer / single reason / no data / combined, plus empty-selection messages, number equality with the data functions, an incomplete date range) and a hostile-filter test: no unhandled exceptions, explicit empty states, bound parameters only. Page load on the full dataset is below 3 s everywhere, so nothing needed optimizing (timings in AUDIT_LOG).

## Audit 7: README and claims

Every number is now traced to an independent computation (109 placeholders) or a registered design constant (17); a wrong number or an unchecked typed number fails `verify_readme.py` (two negative-control tests). Rewording and sensitivity are described in finding 2, 3 and 10.

## Audit 8: interview readiness

[INTERVIEW_QA.md](INTERVIEW_QA.md): 15 questions with answers tied to files, queries and audit results, plus 5 questions the project cannot answer well and how to respond honestly.

## Update after the audit

The project was pushed to GitHub on 2026-10-07 and the CI workflow ran for the first time (`make all` on ubuntu-latest, Python 3.11): it **passed**, which closes the Linux half of finding 21. Metabase remains unbuilt and macOS arm64 plus that one Ubuntu run are the only platforms tested.

## Open items

Findings 12, 14, 15, 16, 17, 18, 19, 21, 22 and the real-world selection strength behind finding 2. Nothing was abandoned after five attempts; items are open because they need a business definition (14), different methods (15), real data (2, 17) or environments I do not have (21).

## Recommended next (maximum 8, by value for a data-analyst application)

1. **Kaplan-Meier days-to-resolve and a censoring-aware win rate** (resolve finding 15): the most analyst-relevant statistical gap; about half a day.
2. **A short written case study of the null/bias experiments** as a notebook-free page with the two figures (false-positive rate and implied realization factor): about 2 hours; it is the strongest evidence in the repo that you test your own conclusions.
3. **Stage-then-swap dbt build** so a killed build never leaves partial marts (finding 12): about 2 hours.
4. **Duplicate-deduction policy** (retailer-specific keys, a `quarantine` model instead of double counting): about 4 hours once the definition is agreed.
5. **Recalibrate the interval** (conformal or per-horizon scaling) so out-of-sample coverage reaches 80%: about 3 hours.
6. **Run CI on GitHub** and fix whatever Linux shows: about 1 hour plus fixes.
7. **A receivable-balance metric** (open invoice balance after payments and deductions) and a partial-payment aware lag: about 3 hours.
8. **Metabase spike** once Docker is available, or drop it from the plan: about 2 hours.

## What I would not claim in an interview

- That the findings are real (they are planted in synthetic data), or that any dollar figure applies to a real company.
- That "$0.9M is recoverable": the supported statement is a range ($0.6M to $1.2M here) that depends on an unknown dispute-selection bias and a chosen dispute window; the same method returns about $0.6M with no planted effect.
- That Holt-Winters beats the seasonal-naive baseline: it is a statistical tie on 7 overlapping origins.
- That the forecast band is an 80% interval: it covered 77% out of sample.
- That valid-vs-invalid share measures wrongful deductions: it is an outcome-based lower bound.
- That the detectors are validated against real behavior: they are checked against planted effects and null data, with a thin margin on the fine-ratio threshold.
- That win rate and days to resolve are unbiased: pending disputes are excluded.
- That duplicates, returns, credit memos, chargebacks or partial-payment balances are handled: they are not (see METRICS.md).
- That Metabase or GitHub Actions work: neither has ever run.
- That the tests prove correctness: they killed 42 of 42 injected bugs and 66% of mutmut's mutants on the forecast module, which says the tests are sensitive, not that the metric definitions are the right ones.
- That this is production-ready: it is a full-rebuild prototype with no incremental loads, access control or monitoring.

## Final gate output

Run on the final tree (`scripts/gate.sh`, appended to BUILD_LOG.md) and from fresh clones in a path containing a space (`scripts/audit_fresh_clone.sh`):

```
clone root: <tmp>/tmp.7tyMCFroGR/path with space
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
<tmp>/tmp.7tyMCFroGR/path with space/make1.log:0
<tmp>/tmp.7tyMCFroGR/path with space/make2.log:0
```

Gate (`docs/BUILD_LOG.md`, section "Audit: final gate"): ruff check: All checks passed; ruff format --check: all files formatted; pytest: 236 passed; dbt build: PASS=116 WARN=0 ERROR=0.
