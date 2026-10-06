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
**Status:** not completed. Docker is not installed on the development machine (no `docker` binary, no Docker Desktop/OrbStack/Colima/Podman), and no Java runtime is installed either, so Metabase could not be run in either form. Only a desk check was possible (driver README: MotherDuck-maintained, pre-built `ghcr.io/motherduckdb/metabase-duckdb` image, version pairing in `metabase_versions.json`, Alpine unsupported). That is not a verification. **Decision pending the user:** install a container runtime and rerun the spike, or switch to Streamlit. No switch has been made.
