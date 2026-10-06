-- Business question: Which retailers' deduction rates are trending up, and how do they rank against peers
--   each month?
-- Metrics used: deduction rate (metrics.deduction_rate), on an invoice-cohort basis.
-- Assumptions: only mature invoice months are used (4+ months old), because deductions for recent
--   months have not all arrived yet; the 3-month rate is dollar-weighted (sum of deductions over sum of
--   gross), not an average of monthly rates.
-- Technique: LAG, rolling window via a named window, RANK.

with monthly as (
    select
        m.retailer_id,
        r.retailer_name,
        m.invoice_month,
        m.gross_amount,
        m.deduction_amount,
        m.deduction_rate
    from metrics.m_retailer_month as m
    inner join marts.dim_retailer as r on r.retailer_id = m.retailer_id
    where m.is_mature_month
),

windowed as (
    select
        retailer_id,
        retailer_name,
        invoice_month,
        deduction_rate,
        lag(deduction_rate) over by_retailer as prev_month_rate,
        metrics.deduction_rate(
            sum(deduction_amount) over last_three,
            sum(gross_amount) over last_three
        ) as rate_3m
    from monthly
    window
        by_retailer as (partition by retailer_id order by invoice_month),
        last_three as (partition by retailer_id order by invoice_month rows between 2 preceding and current row)
)

select
    retailer_id,
    retailer_name,
    invoice_month,
    deduction_rate,
    deduction_rate - prev_month_rate as mom_change,
    rate_3m,
    rank() over (partition by invoice_month order by rate_3m desc) as rank_in_month
from windowed
order by invoice_month, rank_in_month
