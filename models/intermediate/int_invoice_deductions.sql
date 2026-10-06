-- Grain: one row per invoice that has at least one deduction.
select
    invoice_id,
    count(*) as deduction_count,
    sum(amount) as deduction_amount,
    sum(recovered_amount) as recovered_amount
from {{ ref('int_deduction_disputes') }}
group by invoice_id
