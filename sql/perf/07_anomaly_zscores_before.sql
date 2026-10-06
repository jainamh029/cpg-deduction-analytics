-- BEFORE version of analysis 07, kept only for the benchmark in docs/PERFORMANCE.md (not an analysis).
-- Same result as sql/analysis/07_anomaly_zscores.sql, but the trailing 12-month baseline is computed with a
-- range self-join of the series onto itself instead of a window frame.

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
        s.retailer_id,
        s.reason_code,
        s.deduction_month,
        s.deduction_amount,
        avg(h.deduction_amount) as baseline_mean,
        stddev_samp(h.deduction_amount) as baseline_stddev,
        count(*) as baseline_months
    from series as s
    inner join series as h
        on h.retailer_id = s.retailer_id
        and h.reason_code = s.reason_code
        and h.deduction_month >= s.deduction_month - interval 12 month
        and h.deduction_month < s.deduction_month
    group by s.retailer_id, s.reason_code, s.deduction_month, s.deduction_amount
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
where abs(z_score) >= 3
order by anomaly_rank
