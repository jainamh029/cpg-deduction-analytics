-- Grain: one row per dispute window x realization scenario (9 rows). These are ASSUMPTIONS, defined once
-- here and used by analysis 10 and the dashboard: dispute window = how old a never-disputed deduction may
-- be and still be disputed; realization factor = share of the history-based recovery assumed achievable
-- (people dispute the deductions they expect to win, so history overstates what undisputed ones would win).
select
    w.window_days,
    s.scenario,
    s.realization_factor
from (values (90), (180), (365)) as w (window_days)
cross join (values ('low', 0.50), ('base', 0.75), ('high', 1.00)) as s (scenario, realization_factor)
