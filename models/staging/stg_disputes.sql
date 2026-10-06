select
    cast(dispute_id as integer) as dispute_id,
    cast(deduction_id as integer) as deduction_id,
    cast(filed_date as date) as filed_date,
    cast(resolved_date as date) as resolved_date,
    cast(outcome as varchar) as outcome,
    cast(recovered_amount as decimal(18, 2)) as recovered_amount
from {{ source('raw', 'disputes') }}
