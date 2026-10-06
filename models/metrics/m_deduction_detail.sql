{{ config(materialized='table') }}

-- Grain: one row per deduction. Row-level metric attributes; callers aggregate with metrics.* macros.
with params as (
    select
        cast('{{ var("as_of_date") }}' as date) as as_of_date,
        (select min(invoice_date) from {{ ref('fct_invoices') }}) as first_invoice_date
)

select
    d.deduction_id,
    d.invoice_id,
    d.retailer_id,
    d.sku_key,
    d.is_sku_attributed,
    d.reason_code,
    d.status,
    d.invoice_date,
    date_trunc('month', d.invoice_date)::date as invoice_month,
    d.deduction_date,
    d.deduction_month,
    d.amount,
    d.is_disputed,
    d.dispute_outcome,
    d.filed_date,
    d.resolved_date,
    d.recovered_amount,
    metrics.age_days(d.deduction_date, p.as_of_date) as age_days,
    metrics.aging_bucket(metrics.age_days(d.deduction_date, p.as_of_date)) as aging_bucket,
    metrics.open_amount(d.status, d.amount, d.recovered_amount) as open_amount,
    metrics.validity_class(d.status, d.dispute_outcome) as validity_class,
    metrics.is_win(d.dispute_outcome) as is_win,
    metrics.is_resolved(d.dispute_outcome) as is_resolved,
    metrics.filing_lag_days(d.deduction_date, d.filed_date) as filing_lag_days,
    metrics.filing_lag_bucket(metrics.filing_lag_days(d.deduction_date, d.filed_date)) as filing_lag_bucket,
    metrics.days_to_resolve(d.filed_date, d.resolved_date) as days_to_resolve,
    metrics.is_burn_in_month(d.deduction_month, p.first_invoice_date) as is_burn_in_month
from {{ ref('fct_deductions') }} as d
cross join params as p
