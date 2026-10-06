# Design decisions

> All data in this project is synthetic. It is not Confido's data or schema.

Short log of key choices and trade-offs. Newest entries at the bottom.

## D1. DuckDB as the warehouse
**Chosen:** DuckDB, single file. **Why:** zero setup, fast analytical SQL at ~600k rows, window functions and `QUALIFY` built in, trivially reproducible in CI. **Rejected:** Postgres: adds a service to run in CI and for reviewers, with no analytic gain at this scale. **Trade-off:** single writer; Metabase must open the file read-only.

## D2. dbt-core + dbt-duckdb for transformations
**Chosen:** dbt-core 1.12 + dbt-duckdb 1.11 (initially planned as a custom SQL runner; changed on review). **Why:** industry-standard, `ref()` lineage, generated docs, built-in tests (`not_null`, `unique`, `relationships`, `accepted_values`). **Division of labour:** dbt tests cover structure; pytest covers numbers (fan-out reconciliation, hand-computed metric fixtures, generator determinism, regression). **Time box:** half a day from 2026-10-06 15:21 local. If dbt blocks progress, fall back to a minimal SQL runner and record here the reason, what failed, and the time spent.
**Phase 0 outcome:** dbt installed, connected to DuckDB (`dbt debug` passes), project parses, `dbt build` runs (no models yet). About 2 minutes of wall-clock from install to green; no blocker so far. Real model-level risks (schema naming, custom schemas, source switching between `raw` and `raw_dirty`) are still ahead in Phase 1–2.
**Schema naming:** overridden `generate_schema_name` so models land in `staging`, `intermediate`, `marts`, `metrics` instead of dbt's default `main_<schema>` prefixing.

## D3. Metrics defined once, in the `metrics` layer
Each metric is one dbt model in `models/metrics/`. Analysis SQL, dashboard cards, and the forecast select from it. A test greps for raw/staging references and re-derived formulas.

## D4. Nullable `deductions.sku_id` with an "unattributed" bucket
**Why nullable:** real deductions often carry no line reference, and pattern 1 (fines concentrated in 2 SKUs) needs a SKU link at all. **Rules:** every SKU-level metric shows an explicit `(unattributed)` bucket, never silently dropping NULLs; the null rate (expected overall 35–60%) is documented in METRICS.md and enforced by a range test; pattern 1 is reported both over attributed fines and over all fines, with the shift recorded. **Trade-off:** SKU-level concentration is a lower bound on real concentration if unattributed fines are also concentrated.

## D5. 36 months of history
Three seasonal cycles instead of two, so seasonality can be estimated and a backtest has a meaningful training window (first origin at month 24; z-scores testable from month 13). Volumes per month stay in the same order of magnitude as the original 24-month spec.

## D6. Validator checks both directions
The validator must find **exactly** the injected defects on the dirty load and **zero** findings on the clean load; both are tested. A validator that only ever flags things can't be trusted to stay silent on good data.

## D7. Planted patterns are distributions, not exact ratios
Per-entity random effects and noise; tests assert tolerance ranges. PLANTED_PATTERNS.md records target and observed values from the real generator run. **Why:** exact 3.0× effects would be unrealistic and would make the analysis look like it was reverse-engineered.

## D8. Money as DECIMAL(18,2)
Avoids float drift in reconciliation checks (`payments + deductions ≤ gross`).

## D9. Python 3.11 via a configurable interpreter
The project requires 3.11 (pyproject pins `>=3.11,<3.12`, CI uses 3.11). The development machine only had 3.12 system-wide and no `python3.11` on PATH, so Python 3.11 came from `uv python`. The Makefile takes `PY=` (default `python3.11`).

## D10. Dashboard: Metabase spike blocked in Phase 0 (open)
**Status:** not completed. Docker is not installed on the development machine (no `docker` binary, no Docker Desktop/OrbStack/Colima/Podman), and no Java runtime is installed either, so Metabase could not be run in either form. Only a desk check was possible (driver README: MotherDuck-maintained, pre-built `ghcr.io/motherduckdb/metabase-duckdb` image, version pairing in `metabase_versions.json`, Alpine unsupported). That is not a verification. **Resolved (D11).**

## D11. Dashboard built in Streamlit; Metabase left unverified
The user decided (Docker unavailable) to build the dashboard in Streamlit. Metabase is **not claimed to work anywhere**; `docs/METABASE_NOTES.md` records the unverified path and risks.

## D12. Phase gate script, build log, and test integrity
`scripts/gate.sh` runs ruff, `ruff format --check`, pytest and (once models exist) `dbt build`, and only on success appends the trimmed real output to `docs/BUILD_LOG.md`. Rule: tests and tolerances are never loosened to pass; any change to an assertion is logged here with the old and new assertion and the reason.

## D13. Ruff: E501 (line length) ignored
Long string literals (SQL snippets, report text) tripped E501, which `ruff format` cannot fix. The formatter still wraps code at 100 columns. This is a lint-rule choice, not a test change.

## D14. Generator design
Integer cents internally (exact reconciliation); one `SeedSequence` spawning an independent stream per table family so adding a table does not reshuffle the others; `revenue_scale` shrinks volume for fast determinism tests. Invoice SKUs are drawn without replacement with a lognormal popularity skew; attributable deductions pick their SKU from the invoice's own lines. Payments equal gross less all deductions on the invoice (short-pay), so payments + deductions = gross exactly for paid invoices.

## D15. Censoring is explicit, not hidden
Everything dated after the as-of date (2025-12-31) is excluded (no deductions, payments, filings or resolutions after it). Consequences, handled in the metrics/analysis layers: (a) right-censoring: recent invoice months are not yet "mature" (their deductions and payments have not all arrived); (b) left-censoring: there are no 2022 invoices, so deduction-date months Jan-Mar 2023 are under-populated. Retailer B's lag drift is placed in Jan-Jun 2025 (not the last six months) so right-censoring does not mask it.

## D16. Pattern 7 added: one-off anomaly
Retailer E's shortage probability is x5 for invoices dated 2025-04. This is an extra planted event (not in the original six) so the anomaly-detection query has a known ground truth to be tested against.

## D17. Dirty-load defects and exact expectations
Exactly 3 orphaned deductions, 3 duplicate payments and 3 negative deduction amounts are injected into `raw_dirty`. A duplicate payment necessarily also overpays its invoice, so the validator reports it under two rules (`duplicate_payments` and `recon_overpaid_invoice`, 3 each). The expected findings dict lives in `data_gen/dirty.py` and the test compares it for equality.

## D18. Observed pattern 1 is 3.66x, not 3.0x
The A-vs-peer-median fine ratio is a draw from a distribution; with the fixed seed it is 3.66x (inside the 2.2-4.0 test range). I kept it rather than re-tuning the seed to hit exactly 3, per the "visible but imperfect" requirement.

## D19. dbt notes: arguments syntax, schema layout, materialization
dbt 1.12 expects generic-test arguments under `arguments:`; relationship tests use flow-style YAML for brevity. Custom schemas map exactly to staging/intermediate/marts/metrics. Staging, intermediate and metrics are views; marts are tables (dashboard and analysis read them repeatedly). `dbt build` on the full dataset takes ~3 s, so dbt did not become a time sink; the fallback runner was not needed (time spent on dbt in total: well under the half-day box).

## D20. Fan-out handling
Child tables are aggregated to the parent grain in `intermediate` before any join (lines/payments/deductions to invoice; disputes to deduction). Mart totals are asserted equal to raw totals in pytest (gross, deductions, recoveries, payments), and row counts equal raw counts (dim_sku is raw + the one unattributed row).

## D21. Unattributed SKU bucket implemented as a dimension row
`dim_sku` has a real row `sku_key = -1, sku_label = '(unattributed)'`; `fct_deductions.sku_key = coalesce(sku_id, -1)`. Any join on `sku_key` keeps NULL-SKU deductions in an explicit bucket instead of dropping them (tested: inner join to dim_sku loses $0).

## D22. Indexes
No explicit indexes beyond the PK/FK constraints in `raw`. DuckDB is columnar with zone maps; mart tables are scanned or aggregated, not point-looked-up. Any index added later must carry a measured EXPLAIN before/after in docs/PERFORMANCE.md; none has been added.

## D23. Dirty-source test scope
The `raw_dirty` run builds and tests only `staging` (dbt skips downstream nodes of failed tests, and downstream marts on dirty data are not a deliverable). The test asserts that all staging views build and that exactly two dbt data tests fail (deduction -> invoice relationship, non-negative deduction amount). The duplicate payment is caught by the SQL validator, not dbt, because its payment_id is unique by construction.

## D24. Test correction: metric views are checked for division only
`tests/test_hygiene.py::test_metric_views_contain_no_division` first called the full `violations()` checker (schema reads, formula patterns, division) on `models/metrics/*.sql`. That was wrong for its stated purpose: the metrics layer is the one place allowed to contain classification logic such as `status in ('open', 'written_off')` (the recoverable-candidate filter), so it tripped the "use metrics.open_amount" rule. **Old assertion:** `violations(text, check_division=True) == []`. **New assertion:** no line of any metric view contains a `/` outside comments and strings. **Why:** the contract is "views apply macros, they do not divide"; formula-reuse rules apply to analysis SQL and dashboard code, which are checked unchanged.

## D25. Metrics as DuckDB macros plus views
Ratio metrics must work at any grain (retailer-month, reason, SKU, cohort), so each formula is a scalar macro in the `metrics` schema, created once by a dbt on-run-start hook (`macros/metric_definitions.sql`). Views in `models/metrics/` apply them at standard grains; analysis SQL and the dashboard call the same macros. A hygiene test forbids re-deriving formulas elsewhere and requires an explicit `-- non-metric:` note on any division in analysis SQL. Trade-off: macros are expanded at query time, so the warehouse file must carry them (it does; they are persisted in the DuckDB catalog), and a macro change requires `dbt build` to take effect in dependent views' compiled plans.

## D26. Two different "months" for deductions
Invoice-cohort basis (`m_retailer_month`: deduction attributed to the month of its invoice) for rates and net revenue; deduction-date basis (`m_deductions_monthly`) for operational volume, anomaly detection and forecasting. Both are labelled. Maturity (4 months) and burn-in (3 months) flags handle right- and left-censoring respectively.

## D27. Recoverable dollars is a metric, not an ad hoc query
It is used by analysis 10, the CFO dashboard page and the README headline, so it lives in the metrics layer (`m_recoverable_candidates`) with the dispute window applied by the caller. Scenario haircuts (selection bias) are an analysis-level assumption, stated in the analysis file and README.
