{#-
  THE ONLY PLACE METRIC FORMULAS ARE DEFINED (SYNTHETIC data project).

  Each metric is a DuckDB SQL macro in the `metrics` schema. dbt creates them in an on-run-start hook,
  the metric views in models/metrics/ call them, and analysis SQL, the dashboard and tests call them
  too (e.g. metrics.deduction_rate(sum(a), sum(b)) at any grain). Definitions: docs/METRICS.md.
  Statements are separated by semicolons; do not put a semicolon inside a comment.
-#}
{% macro metric_definitions() -%}
-- 1. Deduction rate = deductions / gross invoiced (NULL when gross is 0)
create or replace macro metrics.deduction_rate(deduction_amount, gross_amount) as
    deduction_amount / nullif(gross_amount, 0);

-- 2. Recovery rate = recovered dollars / deducted dollars (NULL when nothing was deducted)
create or replace macro metrics.recovery_rate(recovered_amount, deduction_amount) as
    recovered_amount / nullif(deduction_amount, 0);

-- 3. Net revenue after deductions = gross - deductions + recoveries
create or replace macro metrics.net_revenue(gross_amount, deduction_amount, recovered_amount) as
    gross_amount - deduction_amount + recovered_amount;

-- 4. Open deduction balance: row-level open amount, summed by the caller
create or replace macro metrics.open_amount(deduction_status, deduction_amount, recovered_amount) as
    case when deduction_status in ('open', 'disputed') then deduction_amount - recovered_amount else 0 end;

-- 5. Aging: days since the deduction date, and its bucket
create or replace macro metrics.age_days(deduction_date, as_of_date) as
    date_diff('day', deduction_date, as_of_date);
create or replace macro metrics.aging_bucket(age_days) as
    case when age_days <= 30 then '0-30'
         when age_days <= 60 then '31-60'
         when age_days <= 90 then '61-90'
         else '90+' end;

-- 6. Days to resolve = resolved date - filed date (NULL while pending or never filed)
create or replace macro metrics.days_to_resolve(filed_date, resolved_date) as
    date_diff('day', filed_date, resolved_date);

-- 7. Dispute win rate = (won + partial) / resolved disputes, by count (pending excluded)
create or replace macro metrics.is_win(dispute_outcome) as
    dispute_outcome in ('won', 'partial');
create or replace macro metrics.is_resolved(dispute_outcome) as
    dispute_outcome in ('won', 'partial', 'lost');
create or replace macro metrics.dispute_win_rate(win_count, resolved_count) as
    win_count / nullif(resolved_count, 0);

-- 8. Dispute rate = disputed deduction dollars / deducted dollars
create or replace macro metrics.dispute_rate(disputed_amount, deduction_amount) as
    disputed_amount / nullif(deduction_amount, 0);

-- 9. Valid vs invalid. invalid = recovered via dispute, valid = confirmed owed,
--    unresolved = open or pending, undetermined = written off with no determination
create or replace macro metrics.validity_class(deduction_status, dispute_outcome) as
    case when dispute_outcome in ('won', 'partial') then 'invalid'
         when dispute_outcome = 'lost' or deduction_status = 'accepted' then 'valid'
         when deduction_status in ('open', 'disputed') then 'unresolved'
         else 'undetermined' end;
create or replace macro metrics.invalid_share(invalid_amount, valid_amount) as
    invalid_amount / nullif(invalid_amount + valid_amount, 0);

-- 10. Payment lag: days from invoice date to final payment, dollar-weighted by amount paid
create or replace macro metrics.days_to_pay(invoice_date, paid_date) as
    date_diff('day', invoice_date, paid_date);
create or replace macro metrics.days_past_due(due_date, paid_date) as
    date_diff('day', due_date, paid_date);
create or replace macro metrics.payment_lag(days_to_pay, paid_amount) as
    sum(days_to_pay * paid_amount) / nullif(sum(paid_amount), 0);

-- 11. Recoverable dollars (estimate): amount x reason win rate x recovery ratio on won disputes
create or replace macro metrics.expected_recovery(deduction_amount, win_rate, win_recovery_ratio) as
    deduction_amount * win_rate * win_recovery_ratio;

-- Cohort dimension for the filing-speed analysis
create or replace macro metrics.filing_lag_days(deduction_date, filed_date) as
    date_diff('day', deduction_date, filed_date);
create or replace macro metrics.filing_lag_bucket(lag_days) as
    case when lag_days is null then null
         when lag_days <= 14 then '0-14'
         when lag_days <= 30 then '15-30'
         when lag_days <= 60 then '31-60'
         else '61+' end;

-- Data-completeness flags. An invoice month is mature once 4 months have passed (deductions and
-- payments have arrived). The first 3 deduction months are ramp-up: no invoices exist before the start.
create or replace macro metrics.is_mature_month(invoice_month, as_of_date) as
    invoice_month + interval 4 month <= as_of_date;
create or replace macro metrics.is_burn_in_month(deduction_month, first_invoice_date) as
    deduction_month < date_trunc('month', first_invoice_date) + interval 3 month;
{%- endmacro %}

{% macro create_metric_macros() %}
    {% if execute %}
        {% do run_query("create schema if not exists metrics") %}
        {% for statement in metric_definitions().split(';') %}
            {% if statement.strip() %}
                {% do run_query(statement) %}
            {% endif %}
        {% endfor %}
    {% endif %}
{% endmacro %}
