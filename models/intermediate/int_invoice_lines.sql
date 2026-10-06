-- Grain: one row per invoice. Lines are aggregated to the invoice BEFORE any join.
select
    invoice_id,
    count(*) as line_count,
    sum(qty) as unit_count,
    sum(line_amount) as lines_amount
from {{ ref('stg_invoice_lines') }}
group by invoice_id
