# Metrics

> All data is **synthetic**. Not Confido's data or schema.

Every metric is implemented **once**, as a DuckDB SQL macro in the `metrics` schema
([macros/metric_definitions.sql](../macros/metric_definitions.sql)), created by a dbt `on-run-start`
hook. The views in `models/metrics/` apply the macros at a standard grain; analysis SQL, the dashboard,
and the tests call the same macros at whatever grain they need, e.g.
`metrics.deduction_rate(sum(deduction_amount), sum(gross_amount))`. A test
([tests/test_hygiene.py](../tests/test_hygiene.py)) fails the build if analysis SQL or dashboard code
reads `raw`/`staging`/`intermediate`, repeats a metric formula, or divides numbers without an
explicit `-- non-metric:` annotation. [tests/test_metrics.py](../tests/test_metrics.py) checks every
metric against hand-computed values on a tiny fixture.

**As-of date:** `2025-12-31` (dbt var `as_of_date`, equal to the generator's end date). Ageing is
measured against it, never against today.

## Conventions that apply to every metric

- **Money** is `DECIMAL(18,2)`; ratios are `DOUBLE`. Any ratio with a zero denominator is `NULL`
  (never 0 and never an error).
- **Deduction rate / net revenue are on an invoice-cohort basis**: a deduction counts toward the month
  of the invoice it came from. Deduction-date-basis views (`m_deductions_monthly`) say so in their name.
- **Right-censoring.** Deductions and payments arrive weeks after the invoice, so recent invoice months
  look cleaner than they will end up. `is_mature_month` is true once 4 months have passed
  (`invoice_month + 4 months <= as_of_date`); trend analyses use mature months only.
- **Left-censoring.** No invoices exist before 2023-01-01, so deduction-date months Jan-Mar 2023 are
  under-populated. `is_burn_in_month` flags them; forecasts and anomaly baselines exclude them.
- **SKU attribution.** `deductions.sku_id` is nullable. Every SKU-level metric keeps the NULL rows in an
  explicit `(unattributed)` bucket (`sku_key = -1`, label `(unattributed)` in `dim_sku`); nothing is dropped
  silently. See "SKU attribution and the null rate" below.

## Metric definitions

| # | Metric | Macro / view | Formula | Grain it is defined at |
|---|---|---|---|---|
| 1 | Deduction rate | `metrics.deduction_rate(ded, gross)` | `deductions / gross invoiced` | any; standard: retailer x invoice month (`m_retailer_month`) |
| 2 | Recovery rate | `metrics.recovery_rate(recovered, ded)` | `recovered $ / deducted $` | any; standard: retailer x month, reason |
| 3 | Net revenue after deductions | `metrics.net_revenue(gross, ded, recovered)` | `gross - deductions + recoveries` | invoice (`m_invoice_detail`) |
| 4 | Open deduction balance | `metrics.open_amount(status, amount, recovered)` | sum over `open`/`disputed` deductions of `amount - recovered` | deduction (`m_deduction_detail`) |
| 5 | Aging buckets | `metrics.age_days`, `metrics.aging_bucket` | days from `deduction_date` to the as-of date: `0-30`, `31-60`, `61-90`, `90+` | deduction |
| 6 | Days to resolve | `metrics.days_to_resolve(filed, resolved)` | `resolved_date - filed_date` | dispute / deduction |
| 7 | Dispute win rate | `metrics.dispute_win_rate(wins, resolved)`, `is_win`, `is_resolved` | `(won + partial) / (won + partial + lost)`, by count | any; standard: reason (`m_reason_recovery`) |
| 8 | Dispute rate | `metrics.dispute_rate(disputed, ded)` | `disputed deduction $ / deducted $` | any |
| 9 | Valid vs invalid share | `metrics.validity_class`, `metrics.invalid_share(invalid, valid)` | `invalid $ / (invalid $ + valid $)` | deduction |
| 10 | Payment lag | `metrics.days_to_pay`, `days_past_due`, `payment_lag(days, paid)` | `sum(days_to_pay x paid) / sum(paid)`, $-weighted | invoice; aggregate to any grain |
| 11 | Recoverable dollars (estimate) | `metrics.expected_recovery(amount, win_rate, ratio)`, `m_recoverable_candidates` | `amount x reason win rate x win recovery ratio` over never-disputed, open/written-off deductions | deduction |

Supporting definitions: `metrics.filing_lag_days` / `filing_lag_bucket` (`0-14`, `15-30`, `31-60`, `61+`
days from deduction to filing; used for cohort analysis), `is_mature_month`, `is_burn_in_month`.

### 1. Deduction rate
- **Inclusions:** all deductions of any reason or status, gross = invoice `gross_amount`.
- **Exclusions:** none. Recoveries do *not* reduce the numerator (that is metric 3).
- **Edge cases:** gross = 0 gives `NULL`. Immature months are understated (see right-censoring).

### 2. Recovery rate
- **Inclusions:** `recovered_amount` on won and partial disputes; denominator is *all* deducted dollars
  (not only disputed ones). A win-only ratio is `recovery_rate` applied to won/partial rows
  (used as `win_recovery_ratio`).
- **Edge cases:** pending disputes recover 0 so far; zero deducted dollars gives `NULL`. Recoveries on one deduction
  are **capped at the deduction amount** (re-filed disputes can sum to more; found by the audit).

### 3. Net revenue after deductions
- **Formula:** `gross - deductions + recoveries` per invoice; sums are additive to any grain, so
  waterfall components reconcile exactly to the total.
- **Edge cases:** a recovery can land in a later month than the invoice; cohort basis keeps it with the
  invoice. Unpaid recent invoices still count in gross (accrual basis, not cash).

### 4. Open deduction balance
- **Inclusions:** status `open` or `disputed` (a pending dispute is still unresolved).
- **Exclusions:** `recovered`, `accepted`, `written_off`.
- **Edge cases:** subtracts `recovered_amount` (0 for everything open here); never negative.

### 5. Aging buckets
- **Definition:** age = as-of date - `deduction_date`; buckets `0-30`, `31-60`, `61-90`, `90+`
  (boundaries inclusive on the upper side: 30 is `0-30`, 31 is `31-60`, 90 is `61-90`, 91 is `90+`).
- **Use:** aging is meaningful for open balance, so analyses filter `open_amount > 0`; the bucket is
  computed for every deduction.

### 6. Days to resolve
- **Inclusions:** resolved disputes only. **Edge cases:** pending or never-disputed gives `NULL`, which
  `avg`/`median` ignore. Report median and mean (the distribution is right-skewed).

### 7. Dispute win rate
- **Win** = outcome `won` or `partial`. **Resolved** = `won`, `partial`, `lost`.
  `pending` is excluded from both numerator and denominator.
- **Count-based**, not dollar-based; the dollar view is the win recovery ratio.
- **Edge cases:** no resolved disputes gives `NULL`. Win probability depends on filing lag in this
  synthetic data, so compare win rates across reasons only alongside filing-lag mix (analysis 05).

### 8. Dispute rate
- **Formula:** deduction dollars with a dispute (any outcome, including pending) over deducted dollars.
  A count-based variant is `count(is_disputed) / count(*)` and is only used in tests of the generator.

### 9. Valid vs invalid share
- **Classes** (`metrics.validity_class`): `invalid` = recovered through a won/partial dispute (the
  retailer deducted wrongly); `valid` = confirmed owed (lost dispute, or accepted); `unresolved` = open or
  pending; `undetermined` = written off without ever being disputed.
- **Share** excludes `unresolved` and `undetermined` from the denominator, because no determination exists.
- **Caveat:** an *outcome-based proxy*. Undisputed write-offs may include invalid deductions nobody
  challenged, so the invalid share is a **lower bound**.

### 10. Payment lag
- **Definition:** days from invoice date to the final payment, weighted by amount paid;
  `days_past_due` measures against `due_date`.
- **`payment_lag(days, paid)`** weights whichever day-count it is given: analysis 08 trends `days_to_pay` within a
  retailer over time; the dashboard compares retailers with `days_past_due`, because contractual terms (30/45/60
  days) differ and would otherwise make 60-day-terms retailers look slow.
- **Inclusions:** paid invoices only (unpaid have no lag). **Edge cases:** invoices within about 90 days
  of the as-of date are right-censored (slow payers have not paid yet), which biases recent lag *down*;
  trend analyses use mature months.

### 11. Recoverable dollars (estimate)
- **Definition:** for each deduction that was never disputed and is still `open` or `written_off`,
  `amount x win rate of its reason x win recovery ratio of its reason`; summed over a chosen dispute
  window (filter on `age_days`).
- **Edge cases:** reasons with no resolved disputes have no basis and contribute `NULL` (counted as $0).
- **Caveat:** assumes undisputed deductions would win at the historical rate of disputed ones. Real
  data would show selection bias (people dispute the ones they expect to win), so analysis 10 applies
  haircut scenarios.

## SKU attribution and the null rate

`deductions.sku_id` is nullable by design (real deductions often lack a line reference). Expected
null-rate range **35%-60%** overall (by count), enforced in `tests/test_models.py` and
`tests/test_generator.py`. Target by reason in the generator: compliance_fine ~20%, shortage/pricing/damage
~40%, promo ~70%, other ~80%.

Observed on the built warehouse (seed 20260101): **49.3%** of deductions by count and **53.3%** by dollars
have no SKU (compliance_fine 19.9%, damage 39.4%, other 80.7%, pricing 40.5%, promo 69.2%, shortage
39.4%). These figures are re-checked against the warehouse by `scripts/verify_readme.py`.

Impact on pattern 1 (Retailer A's compliance fines): of A's *attributed* fines, the top-2 SKUs hold
70.6%; counting the unattributed fines in the denominator, they hold 57.2% - a drop of 13.4 points.
The concentration is clearly still detectable. If unattributed fines were also concentrated in the same
two SKUs, true concentration would be higher, so the SKU-level view is a lower bound on concentration
among attributable fines (see `sql/analysis/03_compliance_fine_outliers.sql`).

## Messy real-world conditions (audit)

Status of each condition, with the fixture test that pins it (`tests/test_messy_conditions.py`, hand arithmetic in comments).
The validator (`warehouse/validate.sql`) runs as a gate before dbt (`make build`), so most of these are stopped before they
reach a metric; the table says what the *metrics* do if they get through.

| Condition | Status | What happens |
|---|---|---|
| Partial payments | Handled, by definition | `payments_amount` sums them; lag uses the **final** payment date for the whole amount (a 400 + 400 payment on days 20 and 65 is weighted at 65). The unpaid balance appears in no metric (no receivable-balance metric). |
| Deduction larger than the invoice | Handled (math), flagged | Net revenue goes negative, deduction rate above 100%; validator rule `recon_overpaid_invoice`. |
| Several deductions per invoice | Handled | Aggregated to the invoice before joining. |
| Duplicate deductions (same invoice, reason, SKU, date, amount) | **Unhandled in metrics, flagged** | Both rows count (double deduction). New validator rule `duplicate_deductions`; nothing is removed automatically. |
| Several or re-filed disputes per deduction | **Was wrong, fixed** | Folded to one row per deduction: first filing date, last resolution date, latest outcome, summed recoveries **capped at the deduction amount** (before the fix a deduction could recover 240 of 200). Raw enforces one dispute per deduction; the model does not rely on it. New rules `multiple_disputes_per_deduction`, `recon_recovered_total_exceeds_deduction`. |
| Dispute resolved before it was filed; deduction before its invoice | Unhandled in metrics, flagged | A negative `days_to_resolve` flows into means and medians. Validator rules `date_dispute_order`, `date_deduction_before_invoice` stop it at the gate. |
| Orphaned deductions or disputes (no parent) | Handled | Marts keep them (left joins) with NULL parent attributes so totals reconcile; validator `fk_*`. (A mutation test caught the case where an inner join silently dropped them.) |
| Right-censoring of win rate and days to resolve | **Biased, documented** | Pending disputes are excluded from both, so the metrics describe resolved disputes only. In the fixture the resolved-only mean is 20 days while two pending disputes have already been open 60 and 162 days. If slow disputes are also the ones that lose, win rate is biased upward too. |
| Cohort vs period basis | Handled, labelled | Rates and net revenue are invoice-cohort (`m_retailer_month`); volumes, anomalies and forecasts are deduction-date (`m_deductions_monthly`). They never mix inside one metric. Recent invoice months are flagged `is_mature_month = false`; the headline rate also reports a mature-month figure because the all-period rate is understated (about 0.2 points here). |
| Zero or NULL denominators; months with no activity | Handled; **two queries were wrong, fixed** | Macros return NULL. Retailers with no invoices in a month have no row in `m_retailer_month`; analyses 02 and 08 used a row-based `LAG`, which silently compared a month with the one before the gap. They now use a calendar scaffold (`LAG` means the previous calendar month). |
| Credit memos, returns, chargebacks | **Not modelled** | The schema rejects negative gross and prices, so returns cannot be represented. Net revenue is `gross - deductions + recoveries` and ignores returns and credits; deduction rate uses gross, not net-of-returns, as its denominator. Any claim here applies only to a world without them. |
| Time zones, month-end dates | Handled | Everything is a plain `DATE`; an invoice on Jan 31 belongs to January; a deduction on Apr 30 to April; maturity and ageing use whole-day differences against a fixed as-of date. |
