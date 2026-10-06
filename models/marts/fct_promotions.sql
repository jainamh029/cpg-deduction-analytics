-- Grain: one row per promotion (retailer x SKU x promo window).
select
    promo_id,
    retailer_id,
    sku_id,
    start_date,
    end_date,
    date_trunc('month', start_date)::date as start_month,
    date_diff('day', start_date, end_date) + 1 as duration_days,
    promo_type,
    planned_spend
from {{ ref('stg_promotions') }}
