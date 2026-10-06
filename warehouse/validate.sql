-- Data-quality rules for the SYNTHETIC warehouse. Each rule returns one number: how many rows/entities
-- violate it. {s} is replaced with the schema under test (raw or raw_dirty).
-- A healthy load returns 0 for every rule.

-- rule: pk_retailers
select count(*) - count(distinct retailer_id) from {s}.retailers;
-- rule: pk_skus
select count(*) - count(distinct sku_id) from {s}.skus;
-- rule: pk_invoices
select count(*) - count(distinct invoice_id) from {s}.invoices;
-- rule: pk_invoice_lines
select count(*) - count(distinct (invoice_id, sku_id)) from {s}.invoice_lines;
-- rule: pk_payments
select count(*) - count(distinct payment_id) from {s}.payments;
-- rule: pk_deductions
select count(*) - count(distinct deduction_id) from {s}.deductions;
-- rule: pk_disputes
select count(*) - count(distinct dispute_id) from {s}.disputes;
-- rule: pk_promotions
select count(*) - count(distinct promo_id) from {s}.promotions;

-- rule: fk_invoices_retailer
select count(*) from {s}.invoices x left join {s}.retailers p using (retailer_id) where p.retailer_id is null;
-- rule: fk_invoice_lines_invoice
select count(*) from {s}.invoice_lines x left join {s}.invoices p using (invoice_id) where p.invoice_id is null;
-- rule: fk_invoice_lines_sku
select count(*) from {s}.invoice_lines x left join {s}.skus p using (sku_id) where p.sku_id is null;
-- rule: fk_payments_invoice
select count(*) from {s}.payments x left join {s}.invoices p using (invoice_id) where p.invoice_id is null;
-- rule: fk_deductions_invoice
select count(*) from {s}.deductions x left join {s}.invoices p using (invoice_id) where p.invoice_id is null;
-- rule: fk_deductions_retailer
select count(*) from {s}.deductions x left join {s}.retailers p using (retailer_id) where p.retailer_id is null;
-- rule: fk_deductions_sku
select count(*) from {s}.deductions x left join {s}.skus p using (sku_id)
where x.sku_id is not null and p.sku_id is null;
-- rule: fk_disputes_deduction
select count(*) from {s}.disputes x left join {s}.deductions p using (deduction_id) where p.deduction_id is null;
-- rule: fk_promotions_retailer
select count(*) from {s}.promotions x left join {s}.retailers p using (retailer_id) where p.retailer_id is null;
-- rule: fk_promotions_sku
select count(*) from {s}.promotions x left join {s}.skus p using (sku_id) where p.sku_id is null;

-- rule: nonpositive_invoice_gross
select count(*) from {s}.invoices where gross_amount <= 0;
-- rule: nonpositive_line_qty_or_price
select count(*) from {s}.invoice_lines where qty <= 0 or unit_price <= 0;
-- rule: nonpositive_payment_amount
select count(*) from {s}.payments where paid_amount <= 0;
-- rule: nonpositive_deduction_amount
select count(*) from {s}.deductions where amount <= 0;
-- rule: negative_recovered_amount
select count(*) from {s}.disputes where recovered_amount < 0;

-- rule: recon_invoice_gross_vs_lines
select count(*)
from {s}.invoices i
left join (select invoice_id, sum(qty * unit_price) as lines_amount from {s}.invoice_lines group by 1) l using (invoice_id)
where i.gross_amount <> coalesce(l.lines_amount, 0);
-- rule: recon_overpaid_invoice
select count(*)
from {s}.invoices i
left join (select invoice_id, sum(paid_amount) as paid from {s}.payments group by 1) p using (invoice_id)
left join (select invoice_id, sum(amount) as ded from {s}.deductions group by 1) d using (invoice_id)
where coalesce(p.paid, 0) + coalesce(d.ded, 0) > i.gross_amount;
-- rule: recon_recovered_exceeds_deduction
select count(*) from {s}.disputes x join {s}.deductions d using (deduction_id) where x.recovered_amount > d.amount;
-- rule: recon_deduction_retailer_mismatch
select count(*) from {s}.deductions d join {s}.invoices i using (invoice_id) where d.retailer_id <> i.retailer_id;
-- rule: duplicate_payments
select coalesce(sum(n - 1), 0)::bigint
from (select count(*) as n from {s}.payments group by invoice_id, paid_date, paid_amount having count(*) > 1);

-- rule: date_due_before_invoice
select count(*) from {s}.invoices where due_date < invoice_date;
-- rule: date_deduction_before_invoice
select count(*) from {s}.deductions d join {s}.invoices i using (invoice_id) where d.deduction_date < i.invoice_date;
-- rule: date_dispute_order
select count(*)
from {s}.disputes x join {s}.deductions d using (deduction_id)
where x.filed_date < d.deduction_date or x.resolved_date < x.filed_date;
