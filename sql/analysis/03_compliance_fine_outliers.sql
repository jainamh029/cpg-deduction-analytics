-- Business question: Is one retailer's compliance-fine rate far above its peers, and is it concentrated in
--   a few SKUs? How much of the picture sits in the "(unattributed)" bucket?
-- Metrics used: deduction rate (metrics.deduction_rate) restricted to the compliance_fine reason.
-- Assumptions: peers = every other retailer; a retailer's score is its fine rate divided by the median
--   fine rate of its peers. Fines with no SKU reference stay visible as the "(unattributed)" bucket, so
--   SKU shares are shown both over all fines and over attributed fines only.
-- Technique: chained CTEs, correlated peer median, RANK, running share, explicit unattributed bucket.

with fines as (
    select
        retailer_id,
        sku_key,
        sum(amount) as fine_amount
    from metrics.m_deduction_detail
    where reason_code = 'compliance_fine'
    group by retailer_id, sku_key
),

retailer_fines as (
    select
        retailer_id,
        sum(fine_amount) as fine_amount
    from fines
    group by retailer_id
),

retailer_gross as (
    select
        retailer_id,
        sum(gross_amount) as gross_amount
    from metrics.m_retailer_month
    group by retailer_id
),

fine_rates as (
    select
        f.retailer_id,
        f.fine_amount,
        metrics.deduction_rate(f.fine_amount, g.gross_amount) as fine_rate
    from retailer_fines as f
    inner join retailer_gross as g on g.retailer_id = f.retailer_id
),

scored as (
    select
        retailer_id,
        fine_rate,
        fine_rate / ( -- non-metric: outlier score = own rate over peer median rate
            select median(p.fine_rate)
            from fine_rates as p
            where p.retailer_id <> fine_rates.retailer_id
        ) as ratio_to_peer_median,
        rank() over (order by fine_rate desc) as retailer_rank
    from fine_rates
),

top_retailer as (
    select retailer_id, fine_rate, ratio_to_peer_median
    from scored
    where retailer_rank = 1
),

sku_fines as (
    select
        f.retailer_id,
        f.sku_key,
        s.sku_label,
        f.fine_amount,
        sum(f.fine_amount) over () as total_fines,
        sum(f.fine_amount) filter (where f.sku_key <> -1) over () as attributed_fines,
        rank() over (order by f.fine_amount desc) as sku_rank
    from fines as f
    inner join top_retailer as t on t.retailer_id = f.retailer_id
    inner join marts.dim_sku as s on s.sku_key = f.sku_key
    where f.sku_key <> -1
),

with_unattributed as (
    select
        f.retailer_id,
        f.sku_key,
        s.sku_label,
        f.fine_amount,
        cast(null as bigint) as sku_rank
    from fines as f
    inner join top_retailer as t on t.retailer_id = f.retailer_id
    inner join marts.dim_sku as s on s.sku_key = f.sku_key
    where f.sku_key = -1
),

all_rows as (
    select retailer_id, sku_key, sku_label, fine_amount, sku_rank from sku_fines
    union all
    select retailer_id, sku_key, sku_label, fine_amount, sku_rank from with_unattributed
),

shares as (
    select
        *,
        sum(fine_amount) over () as total_fines,
        sum(fine_amount) filter (where sku_key <> -1) over () as attributed_fines
    from all_rows
)

select
    r.retailer_name,
    t.fine_rate,
    t.ratio_to_peer_median,
    s.sku_key,
    s.sku_label,
    s.sku_rank,
    s.fine_amount,
    s.fine_amount / s.total_fines as share_of_all_fines, -- non-metric: share of total
    case when s.sku_key <> -1 then s.fine_amount / s.attributed_fines end as share_of_attributed_fines, -- non-metric: share of total
    sum(s.fine_amount) over (order by s.sku_rank nulls last) / s.total_fines as cumulative_share_of_all_fines -- non-metric: running share
from shares as s
inner join top_retailer as t on t.retailer_id = s.retailer_id
inner join marts.dim_retailer as r on r.retailer_id = s.retailer_id
where s.sku_rank <= 5 or s.sku_key = -1
order by s.sku_rank nulls last
