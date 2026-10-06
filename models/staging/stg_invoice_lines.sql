select
    cast(invoice_id as integer) as invoice_id,
    cast(sku_id as integer) as sku_id,
    cast(qty as integer) as qty,
    cast(unit_price as decimal(18, 2)) as unit_price,
    cast(qty * unit_price as decimal(18, 2)) as line_amount
from {{ source('raw', 'invoice_lines') }}
