# Interview Q&A for this repository

> All data in this project is synthetic and the findings demonstrate a method. Answers are grounded in files, queries and
> audit results in this repo ([AUDIT_REPORT.md](AUDIT_REPORT.md), [DECISIONS.md](DECISIONS.md)). Where the honest answer is
> "this project cannot tell you", it says so.

## Fifteen hard questions

**1. Where can this pipeline double count deduction dollars, and how do you know it doesn't?**
The grain chain is invoice (1) to deductions (n) to dispute (0..1). `models/intermediate/` aggregates every child to its parent's grain *before* any join (`int_invoice_lines`, `int_invoice_payments`, `int_deduction_disputes`, `int_invoice_deductions`), so `fct_invoices.gross_amount` is never repeated. Tests compare every mart and metric total to independent sums over the raw tables (`tests/test_models.py`, `tests/test_pipeline_robustness.py::test_metrics_layer_row_counts_and_totals_match_raw_tables`). The audit also injected two real fan-outs (a join to invoice lines, a join to raw deductions) and the suite failed for both (mutations M01, M02 in [AUDIT_REPORT.md](AUDIT_REPORT.md)).

**2. How exactly do you define the deduction rate, and why is the recent period flagged?**
`metrics.deduction_rate(deductions, gross)` on an invoice-cohort basis: a deduction counts toward the month of the invoice it came from ([METRICS.md](METRICS.md)). Deductions arrive weeks after invoices, so recent months look better than they are; `is_mature_month` marks months younger than four months, the trend queries skip them, and the README reports both the all-period rate (5.1%) and the mature-month rate (5.3%). The 4-month rule is a judgement call tied to the generator's claim lags (up to about 90 days); on real data I would read it off the empirical lag distribution.

**3. Why is the "valid vs invalid" share not a statement about whether retailers deduct wrongly?**
It is an outcome-based proxy (`metrics.validity_class`): invalid means recovered through a won or partial dispute, valid means lost or accepted, and undisputed write-offs are "undetermined" and excluded from the denominator. People dispute the deductions they think are wrong, so the invalid share is a lower bound and is biased by who chooses to dispute. Real validity needs evidence (proof of delivery, promotion agreements), which this schema does not carry.

**4. The headline recoverable-dollar number: why should I believe it?**
You shouldn't believe it as a point. It multiplies never-disputed deductions younger than 180 days by their reason's *historical* win rate and recovery ratio (`metrics.m_recoverable_candidates`). The audit built a mode where AR teams dispute winnable deductions first (`Config(dispute_bias=...)`, `docs/audit/bias_results.json`) and compared the estimate with the oracle value: the true value was 98% of the estimate with no selection, 80% at moderate selection and 76% at strong selection. The README therefore shows a range ($0.6M to $1.2M, base $0.9M), and the same method on data with no planted effect still returns about $0.6M, so the figure measures volume and rates, not a discovered pattern.

**5. The patterns are planted by you. Isn't finding them circular?**
Partly, and the audit measured how much. Detectors were run on 20 datasets with no planted effect (`docs/audit/null_after.json`): zero "under-invested" flags, about 3 anomaly cells per dataset out of 1,512, no fine outlier, no spike, no lag drift. On 20 planted datasets they found each pattern 20 of 20 times (the one-off anomaly 19 of 20). The margins are not all comfortable (fine-ratio threshold 2.0x with null max 1.98x and planted min 2.04x), and the first version of two detectors produced many false alarms on null data, which is why they were changed (D42). What the repo cannot show is that real retailers behave like this.

**6. How much should I trust your test suite?**
I ran a hand-written mutation audit: 42 injected bugs (fan-outs, LEFT to INNER joins, boundary and denominator errors, a forecast leak, a dropped dashboard filter, duplicate payments, re-derived formulas) one at a time. All 42 are caught by the final suite (kill rate 100%). The baseline run (28 of 30) found two survivors, both LEFT to INNER joins that clean data never exercises; a messy-data fixture now kills them. I also tried `mutmut` on the forecast module: 55% of 564 mutants were killed by the pure-function tests, 66% after I added hand-computed tests for the comparison, scoring and coverage code (88% of the 420 mutants those tests can reach; 144 mutants sit in code only exercised by warehouse-dependent tests, which mutmut cannot run quickly). A mutation score is evidence about test strength, not about whether the metric definitions are right.

**7. What does your forecast actually show?**
That Holt-Winters and the seasonal-naive baseline are indistinguishable on this data. Pooled MAPE is 18.6% vs 18.9%; resampling the 7 origins gives a 95% interval of -2.2 to +2.7 MAPE points for the difference (bootstrap p = 0.89; Diebold-Mariano with the small-sample correction p = 0.92). The 80% band covered 77% of backtest points when built only from earlier origins. MAPE is shown next to sMAPE, MASE and WAPE because small retailers' percentage errors are about twice the large retailers' (`forecast/RESULTS.md`).

**8. Walk me through how you prevent forecast leakage.**
`forecast/model.py::backtest` slices `monthly.iloc[:origin]` for training and `monthly.iloc[origin:origin+horizon]` for scoring; models receive only the training array. Three tests check it: a spy that asserts every model call receives exactly an initial segment of the history, a test that multiplies the last three months by 10 and asserts every forecast is unchanged, and a mutation (`iloc[:origin+1]`) that the suite catches.

**9. What breaks when this meets real customer data?**
Several things the schema simplifies away: partial and consolidated payments (one remittance covering many invoices), duplicate or re-posted deductions, deductions with no invoice reference, returns, credit memos and chargebacks (the raw schema rejects negative amounts), retailer-specific reason codes, UPC versus SKU keys, and promotion agreements with accruals instead of a flat promotions table. The audit fixture (`tests/test_messy_conditions.py`) shows what the metrics do with duplicates, re-filed disputes, partial payments and orphans, and what the validation gate blocks. The honest list of what I could not test is in [METRICS.md](METRICS.md) and the README limitations.

**10. How does this scale to 100x the data?**
Not measured; here is the reasoning. 100x is about 4.8M invoices, 48M lines and 4.9M deductions, which fits a single DuckDB node, and the analysis queries aggregate columnar data (they run in a few milliseconds now, [PERFORMANCE.md](PERFORMANCE.md)). What would hurt first: dbt rebuilds every mart in full each time (about 4 seconds today, so minutes, but it should become incremental), the generator's per-month `n x 300` key matrix, and the README verifier loading raw tables into pandas. Metabase or another BI layer over Postgres/warehouse storage would replace the single-file DuckDB once multiple people write.

**11. How does this schema differ from real ERP and retailer data?**
It is deliberately small and clean: one payment per invoice, payments equal gross minus deductions, one dispute per deduction, invoice-level deductions with an optional SKU, and a flat promotions table with no link to deductions. Real data has settlement documents, open-item ledgers, retailer portals with their own case IDs and dispute stages, deduction codes that vary by retailer, and unapplied cash. I made no attempt to mirror any vendor's schema, and the docs say so.

**12. Why DuckDB?**
Zero setup, one file, fast analytical SQL at this scale, and a fresh clone builds in about 90 seconds (`make all`). Costs I paid for: single writer, no shared server (so the dashboard opens it read-only), and dbt views embed the catalog name, so the file must stay named `warehouse.duckdb` (D33). For a team product I would use a shared warehouse; the SQL is ordinary.

**13. Why Streamlit instead of a BI tool?**
Docker was not available on the build machine, so Metabase was never run (docs/METABASE_NOTES.md is explicitly "not verified"). Streamlit also let me put the data functions under test (13 functions checked against raw-table SQL, filters, SQL-injection safety and page load below 1.1 seconds). The cost is that finance users cannot self-serve new questions; with a BI tool the metrics macros would need to be exposed as semantic-layer measures.

**14. How do you know the README numbers are right?**
`scripts/verify_readme.py` re-derives every number the README shows (109 template tokens) from the raw tables, the forecast CSVs and the audit sweep files, with code that does not use the marts, the metrics macros or the analysis SQL. It also refuses any numeric literal typed in the template that is not a registered design constant. Two negative controls are tested: a wrong README number fails, and an unchecked typed number fails.

**15. If I run `make all` twice, do I get the same thing? What if it dies halfway?**
Identical outputs: from two fresh clones in a directory whose path contains a space, all 29 raw/mart/metric tables had equal content fingerprints and all 12 generated output files were byte-identical (AUDIT_LOG). A killed data load leaves the existing warehouse untouched (it builds beside it and renames), and re-running restores the same fingerprint. A killed `dbt build` leaves a partial warehouse (some marts missing) until it is re-run; re-running always repairs it. Dirty source data is stopped by the validation gate before dbt starts.

## Five questions this project cannot answer well (and how to answer honestly)

**A. "What is the real recovery opportunity for a brand like this?"**
Not answerable from synthetic data. Say: "The repo shows how I would measure it and how sensitive the estimate is to dispute selection bias; the real number needs the brand's dispute history, and the first thing I would measure is how winnable the undisputed deductions are."

**B. "What are Retailer X's actual dispute windows, codes and portal rules?"**
The repo uses a single assumed window set (90/180/365 days) and generic reason codes. Say so, and say that retailer-specific rules belong in configuration that I would build with the AR team.

**C. "How accurate would your matching be for cash application?"**
There is no cash application here: payments are one per invoice and equal gross minus deductions. Do not stretch the work to cover matching; describe it as the analytics layer that sits after application.

**D. "Does the promo spike mean promotions are leaking money?"**
No causal claim is supported. Promo deductions are linked to promotions only at retailer-year level, many are legitimate trade spend, and the spike is planted. The honest answer is what I would need: agreement terms and proof of performance per deduction.

**E. "How would this run in production: incremental loads, permissions, PII, SLAs?"**
Not built or tested. The repo is a reproducible analytical prototype (full rebuild, single file, no auth, no incremental logic). I can describe the design changes (incremental models, a shared warehouse, role-based access) but have not exercised them.
