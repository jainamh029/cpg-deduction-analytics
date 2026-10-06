-- Grain: one row per deduction (dispute fields are null when the deduction was never disputed).
-- sku_key is -1 for unattributed deductions; sku_id keeps the original NULL.
select
    d.deduction_id,
    d.invoice_id,
    d.retailer_id,
    d.sku_id,
    coalesce(d.sku_id, -1) as sku_key,
    d.sku_id is not null as is_sku_attributed,
    i.invoice_date,
    d.deduction_date,
    date_trunc('month', d.deduction_date)::date as deduction_month,
    d.amount,
    d.reason_code,
    d.status,
    d.dispute_id,
    d.dispute_id is not null as is_disputed,
    d.filed_date,
    d.resolved_date,
    d.dispute_outcome,
    d.recovered_amount
from {{ ref('int_deduction_disputes') }} as d
left join {{ ref('stg_invoices') }} as i on i.invoice_id = d.invoice_id
