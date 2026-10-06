-- Business question: How much of gross invoiced revenue is lost to deductions, which reasons cost the
--   most, and how much is won back? (Gross-to-net revenue waterfall, all 36 months.)
-- Metrics used: net revenue after deductions (metrics.net_revenue), deduction dollars by reason.
-- Assumptions: invoice-cohort basis (deductions count with the invoice they came from); recoveries are
--   the dollars won back on disputes to date; amounts are SYNTHETIC. Deductions are negative steps.
-- Technique: chained CTEs; invoice-level and deduction-level totals are aggregated separately and
--   never joined, so there is no fan-out.

with invoice_totals as (
    select
        sum(gross_amount) as gross_amount,
        sum(deduction_amount) as deduction_amount,
        sum(recovered_amount) as recovered_amount
    from metrics.m_invoice_detail
),

reason_totals as (
    select
        reason_code,
        sum(amount) as deduction_amount
    from metrics.m_deduction_detail
    group by reason_code
),

reason_steps as (
    select
        1 + row_number() over (order by deduction_amount desc) as step_order,
        'Less: ' || reason_code || ' deductions' as step,
        -deduction_amount as amount
    from reason_totals
),

steps as (
    select 1 as step_order, 'Gross invoiced' as step, gross_amount as amount
    from invoice_totals

    union all

    select step_order, step, amount
    from reason_steps

    union all

    select 8 as step_order, 'Plus: recovered via disputes' as step, recovered_amount as amount
    from invoice_totals

    union all

    select
        9 as step_order,
        'Net revenue after deductions' as step,
        metrics.net_revenue(gross_amount, deduction_amount, recovered_amount) as amount
    from invoice_totals
)

select
    step_order,
    step,
    amount
from steps
order by step_order
