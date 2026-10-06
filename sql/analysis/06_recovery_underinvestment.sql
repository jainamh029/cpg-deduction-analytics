-- Business question: For which reasons do we win most disputes but dispute least, i.e. where is recovery
--   under-invested?
-- Metrics used: dispute rate (metrics.dispute_rate), dispute win rate (metrics.dispute_win_rate),
--   recovery rate (metrics.recovery_rate).
-- Assumptions: "under-invested" = win rate at least 10 points above the all-reason win rate AND dispute rate
--   below the median reason's dispute rate. The 10-point margin is about 5 standard errors of a win rate
--   built from ~650+ resolved disputes; the audit showed that a bare "above average" rule flags a reason in
--   19 of 20 datasets with NO planted effect. Undisputed dollars are what was never challenged (open, written
--   off or accepted).
-- Technique: window-function benchmarks over the whole result set, RANK, flag.

with by_reason as (
    select
        reason_code,
        sum(amount) as deducted_amount,
        sum(amount) filter (where is_disputed) as disputed_amount,
        sum(amount) filter (where not is_disputed) as undisputed_amount,
        count(*) filter (where is_win) as wins,
        count(*) filter (where is_resolved) as resolved,
        sum(recovered_amount) as recovered_amount
    from metrics.m_deduction_detail
    group by reason_code
),

rated as (
    select
        reason_code,
        deducted_amount,
        undisputed_amount,
        recovered_amount,
        metrics.dispute_rate(disputed_amount, deducted_amount) as dispute_rate,
        metrics.dispute_win_rate(wins, resolved) as win_rate,
        metrics.dispute_rate(sum(disputed_amount) over (), sum(deducted_amount) over ()) as all_reason_dispute_rate,
        metrics.dispute_win_rate(sum(wins) over (), sum(resolved) over ()) as all_reason_win_rate
    from by_reason
),

benchmarked as (
    select
        *,
        median(dispute_rate) over () as median_dispute_rate
    from rated
)

select
    reason_code,
    deducted_amount,
    undisputed_amount,
    dispute_rate,
    win_rate,
    recovered_amount,
    (win_rate >= all_reason_win_rate + 0.10 and dispute_rate < median_dispute_rate) as under_invested,
    rank() over (order by win_rate - dispute_rate desc) as rank_by_win_minus_dispute
from benchmarked
order by rank_by_win_minus_dispute
