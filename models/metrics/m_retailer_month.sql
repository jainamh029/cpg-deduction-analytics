-- Grain: one row per retailer x invoice month (invoice-cohort basis: deductions are attributed to the
-- month of the invoice they came from). Recent months are right-censored: see is_mature_month.
select
    retailer_id,
    invoice_month,
    count(*) as invoice_count,
    sum(gross_amount) as gross_amount,
    sum(deduction_amount) as deduction_amount,
    sum(recovered_amount) as recovered_amount,
    metrics.net_revenue(sum(gross_amount), sum(deduction_amount), sum(recovered_amount)) as net_revenue,
    metrics.deduction_rate(sum(deduction_amount), sum(gross_amount)) as deduction_rate,
    metrics.recovery_rate(sum(recovered_amount), sum(deduction_amount)) as recovery_rate,
    bool_and(is_mature_month) as is_mature_month
from {{ ref('m_invoice_detail') }}
group by retailer_id, invoice_month
