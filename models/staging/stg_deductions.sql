select
    cast(deduction_id as integer) as deduction_id,
    cast(invoice_id as integer) as invoice_id,
    cast(retailer_id as integer) as retailer_id,
    cast(sku_id as integer) as sku_id,  -- nullable on purpose: see docs/METRICS.md
    cast(deduction_date as date) as deduction_date,
    cast(amount as decimal(18, 2)) as amount,
    cast(reason_code as varchar) as reason_code,
    cast(status as varchar) as status
from {{ source('raw', 'deductions') }}
