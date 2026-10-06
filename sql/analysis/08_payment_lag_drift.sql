-- Business question: Which retailers are paying later over time, and by how much versus six months ago?
-- Metrics used: payment lag (metrics.payment_lag: days from invoice date to final payment, weighted by
--   amount paid).
-- Assumptions: mature invoice months only (4+ months old), because slow payers' recent invoices are
--   still unpaid and would bias recent lag downward; the 3-month figure is a simple mean of the monthly
--   lags; unpaid invoices have no lag and do not contribute; months with no paid invoices stay in the
--   result with a NULL lag (calendar scaffold), so LAG(1) and LAG(6) are calendar months, not rows.
-- Technique: calendar scaffold, LAG (1 and 6 months back), rolling average, RANK.

with bounds as (
    select
        min(invoice_month) as first_month,
        max(invoice_month) as last_month
    from metrics.m_invoice_detail
    where is_mature_month
),

calendar as (
    select cast(unnest(generate_series(first_month, last_month, interval 1 month)) as date) as invoice_month
    from bounds
),

lags as (
    select
        retailer_id,
        invoice_month,
        metrics.payment_lag(days_to_pay, payments_amount) as payment_lag_days
    from metrics.m_invoice_detail
    where is_mature_month
    group by retailer_id, invoice_month
),

monthly as (
    select
        r.retailer_id,
        c.invoice_month,
        l.payment_lag_days
    from marts.dim_retailer as r
    cross join calendar as c
    left join lags as l
        on l.retailer_id = r.retailer_id
        and l.invoice_month = c.invoice_month
),

windowed as (
    select
        retailer_id,
        invoice_month,
        payment_lag_days,
        lag(payment_lag_days) over by_retailer as prev_month_lag,
        lag(payment_lag_days, 6) over by_retailer as lag_6m_ago,
        avg(payment_lag_days) over (by_retailer rows between 2 preceding and current row) as lag_3m_avg
    from monthly
    window by_retailer as (partition by retailer_id order by invoice_month)
),

changes as (
    select
        *,
        payment_lag_days - lag_6m_ago as change_vs_6m_ago
    from windowed
)

select
    c.retailer_id,
    r.retailer_name,
    c.invoice_month,
    c.payment_lag_days,
    c.payment_lag_days - c.prev_month_lag as mom_change,
    c.lag_3m_avg,
    c.change_vs_6m_ago,
    rank() over (partition by c.invoice_month order by c.change_vs_6m_ago desc nulls last) as rank_by_change
from changes as c
inner join marts.dim_retailer as r on r.retailer_id = c.retailer_id
order by c.invoice_month, rank_by_change
