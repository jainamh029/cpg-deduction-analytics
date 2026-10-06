-- Business question: How many dollars are realistically recoverable from deductions that were never
--   disputed, under different dispute windows and realization assumptions?
-- Metrics used: recoverable dollars (metrics.expected_recovery via metrics.m_recoverable_candidates).
-- Assumptions: candidates = never-disputed deductions that are still open or were written off; the
--   dispute window is how old a deduction may be and still be disputed (90/180/365 days); history says
--   such deductions would win at their reason's historical win rate and recover the historical share of
--   the amount on a win. Because people tend to dispute the ones they expect to win, scenarios apply a
--   realization factor to the history-based figure: low 0.50, base 0.75, high 1.00 (ASSUMED, not measured).
-- Technique: scenario grid (metrics.m_recovery_scenarios holds the windows and factors), window-limited aggregation.

with window_totals as (
    select
        s.window_days,
        s.scenario,
        s.realization_factor,
        count(*) as candidate_deductions,
        sum(c.amount) as candidate_amount,
        sum(c.expected_recovery) as expected_recovery_at_history
    from metrics.m_recovery_scenarios as s
    inner join metrics.m_recoverable_candidates as c on c.age_days <= s.window_days
    group by s.window_days, s.scenario, s.realization_factor
)

select
    window_days,
    scenario,
    candidate_deductions,
    candidate_amount,
    expected_recovery_at_history * realization_factor as recoverable_amount
from window_totals
order by window_days, realization_factor
