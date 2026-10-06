-- Grain: one row per deduction. Disputes are aggregated to the deduction BEFORE the join, so a
-- deduction can never be multiplied by its disputes (raw enforces one dispute per deduction,
-- but the model does not rely on it).
with disputes_by_deduction as (
    select
        deduction_id,
        count(*) as dispute_count,
        min(dispute_id) as dispute_id,
        min(filed_date) as filed_date,
        max(resolved_date) as resolved_date,
        arg_max(outcome, dispute_id) as dispute_outcome,
        sum(recovered_amount) as recovered_amount
    from {{ ref('stg_disputes') }}
    group by deduction_id
)

select
    d.deduction_id,
    d.invoice_id,
    d.retailer_id,
    d.sku_id,
    d.deduction_date,
    d.amount,
    d.reason_code,
    d.status,
    x.dispute_id,
    x.filed_date,
    x.resolved_date,
    x.dispute_outcome,
    coalesce(x.dispute_count, 0) as dispute_count,
    coalesce(x.recovered_amount, 0) as recovered_amount
from {{ ref('stg_deductions') }} as d
left join disputes_by_deduction as x on x.deduction_id = d.deduction_id
