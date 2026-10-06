-- Grain: one row per retailer x reason x deduction month (deduction-date basis, i.e. when the
-- deduction was taken). Months with no deductions have no row.
select
    retailer_id,
    reason_code,
    deduction_month,
    count(*) as deduction_count,
    sum(amount) as deduction_amount,
    sum(amount) filter (where is_disputed) as disputed_amount,
    sum(recovered_amount) as recovered_amount,
    metrics.dispute_rate(sum(amount) filter (where is_disputed), sum(amount)) as dispute_rate,
    metrics.recovery_rate(sum(recovered_amount), sum(amount)) as recovery_rate,
    bool_and(is_burn_in_month) as is_burn_in_month
from {{ ref('m_deduction_detail') }}
group by retailer_id, reason_code, deduction_month
