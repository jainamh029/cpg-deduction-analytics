-- Grain: one row per invoice. Row-level metric attributes; callers aggregate with metrics.* macros.
with params as (
    select cast('{{ var("as_of_date") }}' as date) as as_of_date
)

select
    i.invoice_id,
    i.retailer_id,
    i.invoice_date,
    i.invoice_month,
    i.due_date,
    i.gross_amount,
    i.deduction_amount,
    i.recovered_amount,
    i.payments_amount,
    i.last_paid_date,
    metrics.net_revenue(i.gross_amount, i.deduction_amount, i.recovered_amount) as net_revenue,
    metrics.days_to_pay(i.invoice_date, i.last_paid_date) as days_to_pay,
    metrics.days_past_due(i.due_date, i.last_paid_date) as days_past_due,
    metrics.is_mature_month(i.invoice_month, p.as_of_date) as is_mature_month
from {{ ref('fct_invoices') }} as i
cross join params as p
