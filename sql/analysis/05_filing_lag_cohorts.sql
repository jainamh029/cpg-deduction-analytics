-- Business question: Does filing a dispute sooner win more often? (Cohorts by days from deduction to filing.)
-- Metrics used: dispute win rate (metrics.dispute_win_rate), filing-lag buckets (metrics.filing_lag_bucket),
--   days to resolve (metrics.days_to_resolve), recovery rate (metrics.recovery_rate).
-- Assumptions: only disputes already filed are in a cohort; pending disputes are in the cohort size but
--   not in the win rate; all reasons are pooled (reason mix is similar across buckets by construction).
-- Technique: cohort analysis, first_value window to compare each cohort to the fastest one.

with disputed as (
    select
        filing_lag_bucket,
        is_win,
        is_resolved,
        days_to_resolve,
        amount,
        recovered_amount
    from metrics.m_deduction_detail
    where is_disputed
),

cohorts as (
    select
        filing_lag_bucket,
        count(*) as disputes,
        count(*) filter (where is_resolved) as resolved_disputes,
        metrics.dispute_win_rate(
            count(*) filter (where is_win),
            count(*) filter (where is_resolved)
        ) as win_rate,
        median(days_to_resolve) as median_days_to_resolve,
        metrics.recovery_rate(sum(recovered_amount), sum(amount)) as recovery_rate
    from disputed
    group by filing_lag_bucket
)

select
    filing_lag_bucket,
    disputes,
    resolved_disputes,
    win_rate,
    win_rate - first_value(win_rate) over (order by filing_lag_bucket) as win_rate_vs_fastest,
    median_days_to_resolve,
    recovery_rate
from cohorts
order by filing_lag_bucket
