-- Grain: one row per SKU, plus one explicit '(unattributed)' row (sku_key = -1) that holds
-- deductions with no SKU reference. SKU-level metrics join on sku_key so NULLs are never dropped.
select
    sku_id as sku_key,
    sku_id,
    'SKU ' || lpad(cast(sku_id as varchar), 3, '0') as sku_label,
    category,
    list_price,
    cogs,
    cast((list_price - cogs) / list_price as decimal(9, 4)) as gross_margin_pct
from {{ ref('stg_skus') }}

union all

select
    -1 as sku_key,
    cast(null as integer) as sku_id,
    '(unattributed)' as sku_label,
    '(unattributed)' as category,
    cast(null as decimal(18, 2)) as list_price,
    cast(null as decimal(18, 2)) as cogs,
    cast(null as decimal(9, 4)) as gross_margin_pct
