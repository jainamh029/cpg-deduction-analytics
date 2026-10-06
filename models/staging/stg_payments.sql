select
    cast(payment_id as integer) as payment_id,
    cast(invoice_id as integer) as invoice_id,
    cast(paid_date as date) as paid_date,
    cast(paid_amount as decimal(18, 2)) as paid_amount
from {{ source('raw', 'payments') }}
