select
    cast(promo_id as integer) as promo_id,
    cast(retailer_id as integer) as retailer_id,
    cast(sku_id as integer) as sku_id,
    cast(start_date as date) as start_date,
    cast(end_date as date) as end_date,
    cast(promo_type as varchar) as promo_type,
    cast(planned_spend as decimal(18, 2)) as planned_spend
from {{ source('raw', 'promotions') }}
