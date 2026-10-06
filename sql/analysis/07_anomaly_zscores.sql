-- Business question: Which retailer x reason x month combinations have deduction dollars far outside their
--   own recent norm?
-- Metrics used: deduction dollars by retailer, reason and deduction month (metrics.m_deductions_monthly).
-- Assumptions: baseline = the trailing 12 months, excluding the current month; months with fewer than 12
--   baseline months are not scored; ramp-up months (the first 3, before invoices existed) are excluded;
--   months with no deductions count as $0; |z| >= 4.5 is flagged. A z-score against a 12-point baseline follows
--   roughly a t distribution with 11 degrees of freedom, where |t| >= 3 occurs 1.2% of the time (about 18 of the
--   1,512 scored cells by chance; the audit measured 25.6 on average in data with no planted anomaly) and
--   |t| >= 4.5 about 0.1% (about 1.5 cells). Seasonal effects are NOT removed, so recurring seasonal spikes
--   (e.g. post-Q4 promo claims) can flag too.
-- Technique: calendar scaffold, window frame (12 preceding to 1 preceding), z-score, RANK.

with bounds as (
    select
        min(deduction_month) as first_month,
        max(deduction_month) as last_month
    from metrics.m_deductions_monthly
    where not is_burn_in_month
),

calendar as (
    select cast(unnest(generate_series(first_month, last_month, interval 1 month)) as date) as deduction_month
    from bounds
),

grid as (
    select
        r.retailer_id,
        x.reason_code,
        c.deduction_month
    from marts.dim_retailer as r
    cross join (select distinct reason_code from metrics.m_deductions_monthly) as x
    cross join calendar as c
),

series as (
    select
        g.retailer_id,
        g.reason_code,
        g.deduction_month,
        coalesce(m.deduction_amount, 0) as deduction_amount
    from grid as g
    left join metrics.m_deductions_monthly as m
        on m.retailer_id = g.retailer_id
        and m.reason_code = g.reason_code
        and m.deduction_month = g.deduction_month
),

scored as (
    select
        retailer_id,
        reason_code,
        deduction_month,
        deduction_amount,
        avg(deduction_amount) over baseline_window as baseline_mean,
        stddev_samp(deduction_amount) over baseline_window as baseline_stddev,
        count(*) over baseline_window as baseline_months
    from series
    window baseline_window as (
        partition by retailer_id, reason_code
        order by deduction_month
        rows between 12 preceding and 1 preceding
    )
),

flagged as (
    select
        *,
        (deduction_amount - baseline_mean) / baseline_stddev as z_score -- non-metric: z-score against trailing baseline
    from scored
    where baseline_months = 12 and baseline_stddev > 0
)

select
    retailer_id,
    reason_code,
    deduction_month,
    deduction_amount,
    baseline_mean,
    baseline_stddev,
    z_score,
    rank() over (order by abs(z_score) desc) as anomaly_rank
from flagged
where abs(z_score) >= 4.5
order by anomaly_rank
