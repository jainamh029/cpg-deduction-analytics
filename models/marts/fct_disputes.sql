-- Grain: one row per dispute. Each dispute has exactly one parent deduction (many-to-one join).
select
    x.dispute_id,
    x.deduction_id,
    x.filed_date,
    x.resolved_date,
    x.outcome,
    x.recovered_amount,
    d.retailer_id,
    d.sku_key,
    d.reason_code,
    d.deduction_date,
    d.amount as deduction_amount
from {{ ref('stg_disputes') }} as x
left join {{ ref('fct_deductions') }} as d on d.deduction_id = x.deduction_id
