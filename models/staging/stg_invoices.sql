select
    cast(invoice_id as integer) as invoice_id,
    cast(retailer_id as integer) as retailer_id,
    cast(invoice_date as date) as invoice_date,
    cast(due_date as date) as due_date,
    cast(gross_amount as decimal(18, 2)) as gross_amount
from {{ source('raw', 'invoices') }}
