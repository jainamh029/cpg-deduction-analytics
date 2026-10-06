-- Grain: one row per retailer.
select
    retailer_id,
    retailer_name,
    channel,
    region,
    payment_terms_days
from {{ ref('stg_retailers') }}
