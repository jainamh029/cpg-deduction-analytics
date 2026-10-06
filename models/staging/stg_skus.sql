select
    cast(sku_id as integer) as sku_id,
    cast(category as varchar) as category,
    cast(list_price as decimal(18, 2)) as list_price,
    cast(cogs as decimal(18, 2)) as cogs
from {{ source('raw', 'skus') }}
