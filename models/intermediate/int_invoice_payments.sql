-- Grain: one row per invoice that has at least one payment.
select
    invoice_id,
    count(*) as payment_count,
    sum(paid_amount) as payments_amount,
    min(paid_date) as first_paid_date,
    max(paid_date) as last_paid_date
from {{ ref('stg_payments') }}
group by invoice_id
