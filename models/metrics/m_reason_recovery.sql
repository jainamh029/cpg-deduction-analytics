-- Grain: one row per reason code. Dispute behaviour and recovery history by reason.
-- win_recovery_ratio = recovered $ / deducted $ over WON or PARTIAL disputes only.
select
    reason_code,
    count(*) as deduction_count,
    sum(amount) as deduction_amount,
    count(*) filter (where is_disputed) as dispute_count,
    count(*) filter (where is_resolved) as resolved_count,
    count(*) filter (where is_win) as win_count,
    sum(recovered_amount) as recovered_amount,
    metrics.dispute_rate(sum(amount) filter (where is_disputed), sum(amount)) as dispute_rate,
    metrics.dispute_win_rate(count(*) filter (where is_win), count(*) filter (where is_resolved)) as win_rate,
    metrics.recovery_rate(sum(recovered_amount) filter (where is_win), sum(amount) filter (where is_win)) as win_recovery_ratio,
    metrics.recovery_rate(sum(recovered_amount), sum(amount)) as recovery_rate
from {{ ref('m_deduction_detail') }}
group by reason_code
