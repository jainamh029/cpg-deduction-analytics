-- Business question: How old is the open deduction balance, and which retailers hold the oldest dollars?
-- Metrics used: open deduction balance (metrics.open_amount), aging buckets (metrics.aging_bucket).
-- Assumptions: as-of date is 2025-12-31 (dbt var as_of_date); "open" means status open or disputed
--   (a pending dispute is still unresolved); the bucket is the age since the deduction date.
-- Technique: aging buckets, window totals, RANK within bucket.

with open_items as (
    select
        retailer_id,
        aging_bucket,
        open_amount
    from metrics.m_deduction_detail
    where open_amount > 0
),

by_bucket as (
    select
        retailer_id,
        aging_bucket,
        count(*) as open_items,
        sum(open_amount) as open_balance
    from open_items
    group by retailer_id, aging_bucket
)

select
    b.retailer_id,
    r.retailer_name,
    b.aging_bucket,
    b.open_items,
    b.open_balance,
    sum(b.open_balance) over (partition by b.retailer_id) as retailer_open_balance,
    b.open_balance / sum(b.open_balance) over (partition by b.retailer_id) as share_of_retailer_balance, -- non-metric: share of total
    rank() over (partition by b.aging_bucket order by b.open_balance desc) as rank_in_bucket
from by_bucket as b
inner join marts.dim_retailer as r on r.retailer_id = b.retailer_id
order by b.aging_bucket, rank_in_bucket
