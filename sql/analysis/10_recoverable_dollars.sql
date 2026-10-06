-- Business question: How many dollars are realistically recoverable from deductions that were never
--   disputed, under different dispute windows and realization assumptions?
-- Metrics used: recoverable dollars (metrics.expected_recovery via metrics.m_recoverable_candidates).
-- Assumptions: candidates = never-disputed deductions that are still open or were written off; the
--   dispute window is how old a deduction may be and still be disputed (90/180/365 days); history says
--   such deductions would win at their reason's historical win rate and recover the historical share of
--   the amount on a win. Because people tend to dispute the ones they expect to win, scenarios apply a
--   realization factor to the history-based figure: low 0.50, base 0.75, high 1.00 (ASSUMED, not measured).
-- Technique: scenario grid (cross join of windows and factors), window-limited aggregation.

with windows as (
    select window_days
    from (values (90), (180), (365)) as w (window_days)
),

scenarios as (
    select scenario, realization_factor
    from (values ('low', 0.50), ('base', 0.75), ('high', 1.00)) as s (scenario, realization_factor)
),

window_totals as (
    select
        w.window_days,
        count(*) as candidate_deductions,
        sum(c.amount) as candidate_amount,
        sum(c.expected_recovery) as expected_recovery_at_history
    from windows as w
    inner join metrics.m_recoverable_candidates as c on c.age_days <= w.window_days
    group by w.window_days
)

select
    t.window_days,
    s.scenario,
    t.candidate_deductions,
    t.candidate_amount,
    t.expected_recovery_at_history * s.realization_factor as recoverable_amount
from window_totals as t
cross join scenarios as s
order by t.window_days, s.realization_factor
