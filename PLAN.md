# PLAN: CPG Deduction & Trade Spend Analytics

> **All data in this project is synthetic.** It is not Confido's data, schema, or any real company's. The fictional company is "Northfield Foods" (~$150M/yr, 12 retailers, ~300 SKUs, **36 months**).

Status: **v2, approved with changes (see revision log). All phases built; deviations from this plan are listed in docs/FINAL_REPORT.md section 5 and logged in docs/DECISIONS.md.**

## Revision log (v1 → v2)

1. Transformations: **dbt-core + dbt-duckdb** replaces the custom Python runner. Time-boxed to half a day; fallback to the runner is recorded in DECISIONS.md if dbt blocks.
2. `deductions.sku_id` stays nullable, with an explicit "unattributed" bucket in every SKU-level metric, a documented null rate enforced by test, and a measured check that pattern 1 survives it.
3. History is **36 months** (2023-01-01 → 2025-12-31), three seasonal cycles; scale targets adjusted.
4. Validator runs both directions: dirty load → exactly the injected defects; clean load → zero findings (tested).
5. Planted patterns use distributions, not exact ratios. Generator tests assert ranges; PLANTED_PATTERNS.md records target and observed values.
6. Phase 0 reordered: (a) Metabase/Docker spike, (b) repo + Makefile + ruff + pytest + dbt skeleton, (c) CI workflow (marked unverified until pushed).

---

## 1. Goal and deliverable

Answer, with dollars: *where does money leak through retailer deductions, and how much is recoverable?* Deliverables: seeded generator, DuckDB warehouse, dbt models, a single-definition metrics layer, 10 analysis queries, a tested pipeline, a Metabase dashboard (3 pages), a backtested forecast, and a README written as a findings memo.

## 2. Architecture

```
 data_gen (seeded)                      warehouse/warehouse.duckdb (gitignored)
 ┌────────────────┐   load    ┌───────────────────────────────────────────────┐
 │ generator      │ ───────►  │ raw        constrained tables (PK/FK/CHECK)   │
 │  clean dataset │           │ raw_dirty  UNconstrained copy + injected bugs │
 │  dirty dataset │ ───────►  ├───────────── dbt-core (dbt-duckdb) ───────────┤
 └────────────────┘           │ staging       typed/renamed views             │
                              │ intermediate  joins, dedupe, fan-out guards   │
 sql/analysis/*.sql ◄──reads─ │ marts         fct_*, dim_* (tables)           │
 dashboard (Metabase) ◄─reads─│ metrics       one view per metric             │
 forecast/ ◄──────reads───────└───────────────────────────────────────────────┘
```

**Rules:** only `staging` reads `raw`, via dbt `source()`. Analysis SQL, dashboard, forecast, and tests read only `marts` / `metrics`.

### Technology choices (rationale in docs/DECISIONS.md)

| Choice | Decision | Why |
|---|---|---|
| Warehouse | **DuckDB** | Zero setup, one file, fast analytical SQL at this scale; Postgres would add a service to CI for no analytic gain. |
| Transformations | **dbt-core + dbt-duckdb** | Standard tooling for the role: `ref()` lineage, generated docs, built-in tests. Time-boxed (see below). |
| Division of testing | **dbt tests** for structure; **pytest** for numbers | dbt: `not_null`, `unique`, `relationships`, `accepted_values` on every model. pytest: fan-out reconciliation (mart totals = raw totals), metric fixtures with hand-computed values, generator determinism and pattern tolerances, regression on analysis queries. |
| Dashboard | **Metabase (docker-compose) + MotherDuck-maintained DuckDB driver** | Spiked in Phase 0; fallback Streamlit, announced if used. |
| Forecast | **statsmodels** (Holt-Winters/ETS) vs seasonal-naive | Lighter than statsforecast, sufficient for one real model. |
| Money type | `DECIMAL(18,2)` | No float drift in reconciliation tests. |

**dbt time box:** half a day from 2026-10-06 15:21 local. If dbt genuinely blocks progress, revert to a minimal SQL runner and record the reason, what failed, and time spent in DECISIONS.md.

Metrics are still defined **exactly once**, as dbt models in the `metrics` layer, and reused everywhere.

Dependencies are added per phase, only when first used. Phase 0: `dbt-core`, `dbt-duckdb`, `pytest`, `ruff`. Later: `pandas`, `numpy`, `statsmodels`, `matplotlib`.

## 3. Schema

Eight tables as specified, plus a nullable `deductions.sku_id`:

```
retailers(retailer_id PK, name, channel CHECK IN (grocery,mass,club,drug,convenience,ecommerce),
          region, payment_terms_days CHECK >0)
skus(sku_id PK, category, list_price CHECK >0, cogs CHECK >=0 AND < list_price)
invoices(invoice_id PK, retailer_id FK, invoice_date, due_date CHECK >= invoice_date, gross_amount CHECK >0)
invoice_lines(invoice_id FK, sku_id FK, qty CHECK >0, unit_price CHECK >0, PK(invoice_id, sku_id))
payments(payment_id PK, invoice_id FK, paid_date, paid_amount CHECK >0)
deductions(deduction_id PK, invoice_id FK, retailer_id FK, sku_id FK NULL, deduction_date,
           amount CHECK >0, reason_code CHECK IN (shortage,promo,compliance_fine,pricing,damage,other),
           status CHECK IN (open,disputed,written_off,recovered,accepted))
disputes(dispute_id PK, deduction_id FK UNIQUE, filed_date, resolved_date NULL,
         outcome CHECK IN (won,partial,lost,pending), recovered_amount CHECK >=0)
promotions(promo_id PK, retailer_id FK, sku_id FK, start_date, end_date CHECK >= start_date,
           promo_type CHECK IN (tpr,bogo,display,feature,coupon), planned_spend CHECK >=0)
```

- **Nullable `sku_id` policy.** A real deduction often lacks a line reference. Target null rate by reason: compliance_fine ≈15–25%, pricing/damage/shortage ≈30–50%, promo/other ≈70–90%; overall expected range **35–60%**, enforced by a pytest range test and documented in METRICS.md. Every SKU-level metric (and every dbt model that groups by SKU) emits an explicit `'(unattributed)'` bucket; NULL rows are never dropped. Pattern 1 is reported two ways (share of *attributed* fines in the top-2 SKUs, and share of *all* fines incl. unattributed) and the shift between them is recorded in PLANTED_PATTERNS.md.
- One dispute per deduction (UNIQUE): grain simplification, documented.
- Cross-row invariants (not expressible as CHECK) enforced by validation SQL + tests: `invoices.gross_amount = Σ(qty × unit_price)`; `Σ payments + Σ deductions ≤ gross` per invoice; `recovered_amount ≤ deduction amount`; deduction retailer matches its invoice's retailer; `resolved_date ≥ filed_date ≥ deduction_date`.
- **Validator (both directions).** `warehouse/validate.sql` returns one row per violated rule per schema. Tests: dirty load → exactly the injected defect set (1 orphaned deduction, 1 duplicate payment, 1 negative amount, 1 reconciliation breach), nothing more or less; clean load → **zero findings**.

### Scale (36 months, same per-month order of magnitude as v1)

~$450M total gross (~$12.5M/month), ~60k invoices, ~500–600k lines (~10/invoice), ~45–55k deductions (≈4.5–5% of gross).

### Indexes

DuckDB is columnar with zone maps, so indexes are used sparingly. Candidates: `deductions(retailer_id, deduction_date)`, `payments(invoice_id)`. Each is measured with EXPLAIN before and after; any index without a measured benefit is dropped. Created after bulk load.

## 4. Planted patterns

Each is a **distribution**, not an exact ratio: per-entity random effects, noise in rates, and overlapping ranges so the effect is visible but imperfect. Targets below are central tendencies; tests assert **ranges**; PLANTED_PATTERNS.md records *target* and *observed* per pattern (observed pasted from the actual generator run).

| # | Pattern | Mechanism (stochastic) | Target | Test range (wide enough to avoid flakiness, narrow enough to be meaningful) |
|---|---|---|---|---|
| 1 | Retailer A compliance fines ≈3× peers, concentrated in 2 SKUs | A's per-invoice fine probability = peer base × lognormal multiplier (median ≈3); SKU choice from a skewed categorical favouring 2 SKUs (~70% mass) | A's fine $/revenue ≈ 3× peer median | 2.2–4.0×; top-2 share of attributed ≥ 55% and of all incl. unattributed ≥ 40% |
| 2 | Promo deductions spike after Q4 promos, rarely disputed | Promo-deduction intensity multiplied (≈2–3×, random per retailer-year) in the 8 weeks after Q4 promo windows; dispute prob ~5–10% | Jan–Feb promo $ / other-month avg ≥ 1.8 | ≥1.5×; dispute rate ≤ 15% |
| 3 | Shortage: high win rate, low dispute rate | Dispute prob ~15%, win prob ~80% (other reasons ~35–45% disputed, win ~55–65%) | win ≥ 70%, dispute rate ≤ 25% | win 65–92%, dispute rate 8–30%; and win(shortage) − win(others) ≥ 0.08 |
| 4 | Retailer B payment lag drifts up over 6 months | Lag mean rises ≈ +10 days over the last 6 months on top of noise (σ ≈ 4 d) | positive slope; ≥ +6 days | OLS slope > 0 and last-3-month mean − first-month mean of window ≥ 5 d; other retailers' slope CI includes 0 |
| 5 | Seasonality + growth | Month multipliers (Q4 peak, summer dip) × ≈8% YoY trend × noise | YoY 6–10%; Q4 / Q1–Q3 avg ≈ 1.2–1.3 | YoY 4–12%; Q4 ratio 1.1–1.5 |
| 6 | Data-quality defects | Dirty load only | exact counts | exact (this one is deterministic by design) |

Generator design: one `numpy.random.default_rng(seed)`; per-table child streams from `SeedSequence.spawn` so adding a table does not reshuffle others. Config in a typed `config.py` dataclass (no YAML dependency). Valid vs invalid is **not** stored as an oracle column; it is derived from dispute outcomes (see METRICS).

## 5. Repository layout

```
.github/workflows/ci.yml
data_gen/      config.py generate.py patterns.py dirty.py load.py
warehouse/     ddl.sql validate.sql      (DuckDB file is gitignored)
models/
  sources.yml
  staging/       stg_*.sql  + schema.yml  (dbt tests)
  intermediate/  int_*.sql  + schema.yml
  marts/         dim_retailer dim_sku fct_invoices fct_deductions fct_disputes + schema.yml
  metrics/       m_*.sql    + schema.yml
macros/        generate_schema_name.sql (+ shared helpers)
dbt_project.yml profiles.yml (relative DuckDB path, no secrets)
sql/analysis/  01_… 10_*.sql  + OPTIMIZATION_NOTES.md
tests/         test_toolchain.py test_generator.py test_validator.py test_fanout.py
               test_metrics.py test_analysis_regression.py  fixtures/  expected/
forecast/      forecast.py backtest.py forecast.ipynb results/backtest_mape.csv
dashboard/     docker-compose.yml setup_metabase.py cards/*.json screenshots/
docs/          DECISIONS.md METRICS.md data_model.md (Mermaid ERD) + dbt docs (generated, not committed)
Makefile README.md PLAN.md PLANTED_PATTERNS.md pyproject.toml .gitignore
```

## 6. Metrics layer (docs/METRICS.md; each implemented once in `models/metrics/`)

1. **Deduction rate** = Σ deduction amount / Σ gross invoiced
2. **Net revenue after deductions** = gross − deductions + recovered
3. **Open deduction balance** = Σ amount of `open`/`disputed` deductions − recoveries to date
4. **Aging buckets** (0–30, 31–60, 61–90, 90+ days since deduction_date; fixed as-of date for reproducibility)
5. **Days to resolve** (filed → resolved, resolved disputes only; median and mean)
6. **Dispute rate** ($ and count)
7. **Dispute win rate** ($-weighted won+partial; pending excluded)
8. **Recovery rate** = recovered $ / deducted $
9. **Valid-vs-invalid share**: *invalid* = recovered via dispute; *valid* = confirmed owed (lost, accepted, written off); *unresolved* separate. Outcome-based proxy, not ground truth.
10. **Payment lag (days)** = paid_date − invoice_date, $-weighted; and days past due.

Each entry: formula, grain, inclusions/exclusions, edge cases, **and SKU-null handling** where SKU-sliced (`'(unattributed)'` bucket; null rate documented). A test fails the build if analysis SQL or dashboard cards reference `raw.*`/`staging.*` or re-derive a metric formula.

### Fan-out strategy
Grain chain: invoice (1) → deductions (n) → dispute (0..1). Intermediate models pre-aggregate children to parent grain **before** joining. pytest asserts `SUM(fct_invoices.gross_amount) = SUM(raw.invoices.gross_amount)` and the same for deductions and recoveries across all marts. Promo attribution (no FK) is done at **retailer-month** grain with promos pre-aggregated; approximate, documented.

## 7. Analysis queries (`sql/analysis/`)

| # | Business question | Techniques |
|---|---|---|
| 01 | Gross-to-net waterfall | chained CTEs, fan-out-safe join |
| 02 | Which retailers' deduction rates are trending up? | `LAG`, rolling 3-mo avg, `RANK` |
| 03 | Reason mix by retailer; compliance-fine outlier and SKU concentration (with unattributed bucket) | `RANK`, share-of-total windows |
| 04 | How old is the open balance? | aging buckets |
| 05 | Does filing faster win more? | cohort by filing-lag bucket |
| 06 | Where is recovery under-invested? | dispute rate vs win rate by reason |
| 07 | Which retailer-reason-months are anomalous? | z-score vs trailing 12-mo baseline (`ROWS BETWEEN 12 PRECEDING AND 1 PRECEDING`); testable months 13–36 |
| 08 | Do Q4 promos cause the Jan–Feb spike? | retailer-month promo aggregation |
| 09 | Which retailers pay later? | `LAG`, rolling avg, slope |
| 10 | Realistically recoverable dollars | open undisputed × reason win rate × recovery ratio; low/base/high |

`OPTIMIZATION_NOTES.md`: `EXPLAIN ANALYZE` before/after on query 07 or 05; median of 5 runs; hardware noted.

## 8. Forecast

Target: monthly **deduction dollars by retailer** (12 series × 36 months). Models: **seasonal-naive** vs **Holt-Winters** (damped additive trend, additive seasonality). Rolling-origin expanding-window backtest: first origin at month 24 (two full cycles of training), horizon 3, origins 24–33. Fit uses only data ≤ origin; a test alters future values and asserts forecasts do not change. Report MAPE per retailer, pooled MAPE, and WAPE (MAPE explodes on small values). State where the model loses. Final 3-month forward forecast feeds the CFO page.

## 9. Dashboard

Metabase (pinned tag) + MotherDuck DuckDB driver JAR (pinned, checksum-verified, downloaded at setup, not committed). Warehouse mounted **read-only**. `setup_metabase.py` creates connection, questions and 3 dashboards idempotently via REST API (stdlib only); question definitions exported to `dashboard/cards/`. Pages: Retailer performance (VP Sales); Deduction operations (AR manager); Cash impact (CFO). Filters: retailer, date, reason code. Titles state takeaways. Cards read only `marts.*`/`metrics.*`; every card query is executed in tests against the CI-built warehouse. Docker is not run in CI.

**Risks:** (a) driver ↔ Metabase version pairing; (b) DuckDB **storage-format compatibility**: the driver bundles its own DuckDB JDBC version, which must be able to open a file written by the Python `duckdb` version (mitigation: pin Python `duckdb` to the driver's bundled version, or export marts to a separate file/Parquet); (c) Docker availability; (d) screenshots only if actually captured.

## 10. Test strategy

| Layer | What | How |
|---|---|---|
| Structural | not_null, unique, relationships, accepted_values on every model | dbt tests (`dbt build`) |
| Data quality | PK, FK, no negatives, reconciliation | `validate.sql` + pytest |
| Validator both ways | dirty = exact injected set; **clean = zero findings** | pytest |
| SKU null policy | null rate within expected range, unattributed bucket present in SKU-level outputs, pattern 1 still detectable | pytest |
| Fan-out | mart totals = raw totals; adding child rows never changes parent sums | pytest |
| Metrics | every metric vs hand-computed values on a ~10-invoice fixture + edge cases | pytest |
| Generator | same seed → identical table hashes; pattern **ranges** (§4); scale bounds | pytest |
| Regression | analysis queries: row counts + a few pinned values | pytest |
| Hygiene | no analysis/dashboard SQL on raw/staging; no duplicated metric formulas | pytest |
| Forecast | no-leakage; output schema | pytest |
| Static | `ruff check`, `ruff format --check` | CI |

## 11. Build phases and exit criteria

| Phase | Output | Exit criteria |
|---|---|---|
| 0 | (a) Metabase/Docker spike report; (b) repo, Makefile, ruff, pytest, dbt skeleton; (c) CI workflow | `make lint`, `make test`, `make build` green locally; CI marked **unverified**; spike result reported plainly |
| 1 | generator, DDL, clean+dirty load, PLANTED_PATTERNS.md | generator + validator tests green (both directions); observed pattern values recorded |
| 2 | dbt staging→marts, grain docs, indexes (measured) | dbt tests + fan-out reconciliation green |
| 3 | `metrics` models, METRICS.md | metric fixture tests green; null-rate test green |
| 4 | 10 analysis files + optimization notes | regression tests green; timings measured |
| 5 | complete suite + CI | `make all` green from a fresh clone; CI verified only after the user pushes |
| 6 | dashboard + exported setup + screenshots | card queries execute; Metabase verified running or fallback declared |
| 7 | forecast + backtest | leakage test green; MAPE table produced |
| 8 | README memo, ERD, DECISIONS.md | every README number traces to a query or artifact |

**Makefile (Phase 0):** `setup`, `lint`, `test`, `build`, `docs`, `clean`, `all`. Later: `data`, `analysis`, `forecast`, `dashboard-up`. Builds recreate `warehouse.duckdb`, so they are idempotent.

## 12. Conventions

Fixed seed in `config.py`. No absolute paths. Generated data, `.duckdb`, and driver JARs are gitignored; only screenshots and small fixtures are committed. Type hints on public functions, small functions, no dead code or TODOs. SQL: lowercase keywords, one CTE per logical step. No SQL linter (keeps dependencies minimal). Python 3.11 is required; the environment here only had 3.12 system-wide, so 3.11 comes from `uv python` (README documents `PY=`).
