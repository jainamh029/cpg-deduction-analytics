-- Business question: Which retailers' deduction rates are trending up, and how do they rank against peers
--   each month?
-- Metrics used: deduction rate (metrics.deduction_rate), on an invoice-cohort basis.
-- Assumptions: only mature invoice months are used (4+ months old), because deductions for recent
--   months have not all arrived yet; the 3-month rate is dollar-weighted (sum of deductions over sum of
--   gross), not an average of monthly rates. Months in which a retailer has no invoices stay in the
--   result with a NULL rate (calendar scaffold), so LAG always means "the previous calendar month".
-- Technique: calendar scaffold, LAG, rolling window via a named window, RANK.

with bounds as (
    select
        min(invoice_month) as first_month,
        max(invoice_month) as last_month
    from metrics.m_retailer_month
    where is_mature_month
),

calendar as (
    select cast(unnest(generate_series(first_month, last_month, interval 1 month)) as date) as invoice_month
    from bounds
),

monthly as (
    select
        r.retailer_id,
        r.retailer_name,
        c.invoice_month,
        m.gross_amount,
        m.deduction_amount,
        m.deduction_rate
    from marts.dim_retailer as r
    cross join calendar as c
    left join metrics.m_retailer_month as m
        on m.retailer_id = r.retailer_id
        and m.invoice_month = c.invoice_month
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
    rank() over (partition by invoice_month order by rate_3m desc nulls last) as rank_in_month
from windowed
order by invoice_month, rank_in_month
