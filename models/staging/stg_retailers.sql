select
    cast(retailer_id as integer) as retailer_id,
    cast(name as varchar) as retailer_name,
    cast(channel as varchar) as channel,
    cast(region as varchar) as region,
    cast(payment_terms_days as integer) as payment_terms_days
from {{ source('raw', 'retailers') }}
