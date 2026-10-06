-- Business question: Do promo deductions spike in Jan-Feb after Q4 promotions, and are they disputed?
-- Metrics used: deduction dollars and dispute rate (metrics.dispute_rate) for the promo reason; planned
--   promo spend from marts.fct_promotions.
-- Assumptions: promo deductions carry no promo id, so the link is retailer-year (Q4 promos of year Y-1
--   against Jan-Feb of year Y), not row-level; spike index = average monthly promo deduction dollars in
--   Jan-Feb divided by the Mar-Sep average of the same year; 2023 is excluded (no prior Q4 in the data).
-- Technique: retailer-month pre-aggregation (no row-level promo join, so no fan-out), conditional averages.

with promo_months as (
    select
        retailer_id,
        deduction_month,
        extract(year from deduction_month) as deduction_year,
        extract(month from deduction_month) as month_of_year,
        deduction_amount,
        disputed_amount
    from metrics.m_deductions_monthly
    where reason_code = 'promo'
      and not is_burn_in_month
),

yearly as (
    select
        retailer_id,
        deduction_year,
        avg(deduction_amount) filter (where month_of_year in (1, 2)) as jan_feb_monthly_amount,
        avg(deduction_amount) filter (where month_of_year between 3 and 9) as mar_sep_monthly_amount,
        metrics.dispute_rate(sum(disputed_amount), sum(deduction_amount)) as promo_dispute_rate
    from promo_months
    where deduction_year in (2024, 2025)
    group by retailer_id, deduction_year
),

q4_plans as (
    select
        retailer_id,
        extract(year from start_date) as plan_year,
        sum(planned_spend) as q4_planned_spend
    from marts.fct_promotions
    where extract(month from start_date) >= 10
    group by retailer_id, extract(year from start_date)
)

select
    y.retailer_id,
    r.retailer_name,
    y.deduction_year,
    q.q4_planned_spend as prior_q4_planned_spend,
    y.jan_feb_monthly_amount,
    y.mar_sep_monthly_amount,
    y.jan_feb_monthly_amount / y.mar_sep_monthly_amount as spike_index, -- non-metric: Jan-Feb average over Mar-Sep average
    y.promo_dispute_rate,
    rank() over (partition by y.deduction_year order by y.jan_feb_monthly_amount / y.mar_sep_monthly_amount desc) as spike_rank -- non-metric: same spike index
from yearly as y
inner join marts.dim_retailer as r on r.retailer_id = y.retailer_id
left join q4_plans as q on q.retailer_id = y.retailer_id and q.plan_year = y.deduction_year - 1
order by y.deduction_year, spike_rank
