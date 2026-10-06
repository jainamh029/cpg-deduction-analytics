-- Grain: one row per invoice. Children (lines, payments, deductions) are pre-aggregated to the
-- invoice in the intermediate layer, so gross_amount is never multiplied.
select
    i.invoice_id,
    i.retailer_id,
    i.invoice_date,
    date_trunc('month', i.invoice_date)::date as invoice_month,
    i.due_date,
    i.gross_amount,
    coalesce(l.lines_amount, 0) as lines_amount,
    coalesce(l.line_count, 0) as line_count,
    coalesce(p.payments_amount, 0) as payments_amount,
    coalesce(p.payment_count, 0) as payment_count,
    p.last_paid_date,
    coalesce(d.deduction_amount, 0) as deduction_amount,
    coalesce(d.deduction_count, 0) as deduction_count,
    coalesce(d.recovered_amount, 0) as recovered_amount
from {{ ref('stg_invoices') }} as i
left join {{ ref('int_invoice_lines') }} as l on l.invoice_id = i.invoice_id
left join {{ ref('int_invoice_payments') }} as p on p.invoice_id = i.invoice_id
left join {{ ref('int_invoice_deductions') }} as d on d.invoice_id = i.invoice_id
