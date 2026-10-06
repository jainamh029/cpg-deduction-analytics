-- DDL for the SYNTHETIC raw schema (fictional data; not any real company's schema).
-- The raw schema enforces PK / FK / NOT NULL / CHECK. The raw_dirty schema is created by
-- data_gen/load.py as unconstrained copies of these tables.

create schema if not exists raw;

create table raw.retailers (
    retailer_id        integer primary key,
    name               varchar not null,
    channel            varchar not null
        check (channel in ('grocery', 'mass', 'club', 'drug', 'convenience', 'ecommerce')),
    region             varchar not null,
    payment_terms_days integer not null check (payment_terms_days > 0)
);

create table raw.skus (
    sku_id     integer primary key,
    category   varchar not null,
    list_price decimal(18, 2) not null check (list_price > 0),
    cogs       decimal(18, 2) not null check (cogs >= 0 and cogs < list_price)
);

create table raw.invoices (
    invoice_id   integer primary key,
    retailer_id  integer not null references raw.retailers (retailer_id),
    invoice_date date not null,
    due_date     date not null,
    gross_amount decimal(18, 2) not null check (gross_amount > 0),
    check (due_date >= invoice_date)
);

create table raw.invoice_lines (
    invoice_id integer not null references raw.invoices (invoice_id),
    sku_id     integer not null references raw.skus (sku_id),
    qty        integer not null check (qty > 0),
    unit_price decimal(18, 2) not null check (unit_price > 0),
    primary key (invoice_id, sku_id)
);

create table raw.payments (
    payment_id  integer primary key,
    invoice_id  integer not null references raw.invoices (invoice_id),
    paid_date   date not null,
    paid_amount decimal(18, 2) not null check (paid_amount > 0)
);

create table raw.deductions (
    deduction_id   integer primary key,
    invoice_id     integer not null references raw.invoices (invoice_id),
    retailer_id    integer not null references raw.retailers (retailer_id),
    sku_id         integer references raw.skus (sku_id),  -- nullable: many deductions lack a line reference
    deduction_date date not null,
    amount         decimal(18, 2) not null check (amount > 0),
    reason_code    varchar not null
        check (reason_code in ('shortage', 'promo', 'compliance_fine', 'pricing', 'damage', 'other')),
    status         varchar not null
        check (status in ('open', 'disputed', 'written_off', 'recovered', 'accepted'))
);

create table raw.disputes (
    dispute_id       integer primary key,
    deduction_id     integer not null unique references raw.deductions (deduction_id),
    filed_date       date not null,
    resolved_date    date,
    outcome          varchar not null check (outcome in ('won', 'partial', 'lost', 'pending')),
    recovered_amount decimal(18, 2) not null check (recovered_amount >= 0),
    check ((outcome = 'pending') = (resolved_date is null)),
    check (resolved_date is null or resolved_date >= filed_date)
);

create table raw.promotions (
    promo_id      integer primary key,
    retailer_id   integer not null references raw.retailers (retailer_id),
    sku_id        integer not null references raw.skus (sku_id),
    start_date    date not null,
    end_date      date not null,
    promo_type    varchar not null check (promo_type in ('tpr', 'bogo', 'display', 'feature', 'coupon')),
    planned_spend decimal(18, 2) not null check (planned_spend >= 0),
    check (end_date >= start_date)
);
