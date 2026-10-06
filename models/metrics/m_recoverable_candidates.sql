-- Grain: one row per deduction that was NEVER disputed and is still open or was written off.
-- expected_recovery applies the reason's historical win rate and win recovery ratio. Reasons with no
-- resolved disputes have no basis, so expected_recovery is NULL (counted as $0 by SUM).
-- Caller picks the dispute window by filtering age_days.
select
    d.deduction_id,
    d.retailer_id,
    d.sku_key,
    d.reason_code,
    d.status,
    d.deduction_date,
    d.age_days,
    d.amount,
    r.win_rate,
    r.win_recovery_ratio,
    metrics.expected_recovery(d.amount, r.win_rate, r.win_recovery_ratio) as expected_recovery
from {{ ref('m_deduction_detail') }} as d
left join {{ ref('m_reason_recovery') }} as r on r.reason_code = d.reason_code
where not d.is_disputed
  and d.status in ('open', 'written_off')
