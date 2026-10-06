# Data model (SYNTHETIC data)

> All data is synthetic. Not Confido's data or schema. The raw tables are modelled on common CPG
> receivables concepts and are an illustration only.

## Raw schema (ERD)

`deductions.sku_id` is nullable; every SKU-level metric keeps those rows in an explicit `(unattributed)` bucket.
`disputes.deduction_id` is unique (one dispute per deduction, a simplification).

```mermaid
erDiagram
    RETAILERS ||--o{ INVOICES : "billed to"
    RETAILERS ||--o{ PROMOTIONS : runs
    RETAILERS ||--o{ DEDUCTIONS : "takes"
    SKUS ||--o{ INVOICE_LINES : "sold as"
    SKUS ||--o{ PROMOTIONS : "promoted"
    SKUS |o--o{ DEDUCTIONS : "optional reference"
    INVOICES ||--|{ INVOICE_LINES : contains
    INVOICES ||--o{ PAYMENTS : "paid by"
    INVOICES ||--o{ DEDUCTIONS : "short-paid with"
    DEDUCTIONS ||--o| DISPUTES : "disputed in"
    RETAILERS { int retailer_id PK }
    SKUS { int sku_id PK }
    INVOICES { int invoice_id PK }
    INVOICE_LINES { int invoice_id PK "FK" }
    PAYMENTS { int payment_id PK }
    DEDUCTIONS { int deduction_id PK "sku_id nullable" }
    DISPUTES { int dispute_id PK "deduction_id unique" }
    PROMOTIONS { int promo_id PK }
```

## Model grain

| Layer | Model | Grain |
|---|---|---|
| staging | `stg_*` (8) | one row per raw row, typed and renamed |
| intermediate | `int_invoice_lines` | one row per invoice |
| intermediate | `int_invoice_payments` | one row per invoice with a payment |
| intermediate | `int_deduction_disputes` | one row per deduction (dispute folded in) |
| intermediate | `int_invoice_deductions` | one row per invoice with a deduction |
| marts | `dim_retailer` | one row per retailer |
| marts | `dim_sku` | one row per SKU plus the `(unattributed)` row |
| marts | `fct_invoices` | one row per invoice |
| marts | `fct_deductions` | one row per deduction |
| marts | `fct_disputes` | one row per dispute |
| marts | `fct_promotions` | one row per promotion |
| metrics | `m_deduction_detail`, `m_invoice_detail` | deduction / invoice, with row-level metric attributes |
| metrics | `m_retailer_month` | retailer x invoice month |
| metrics | `m_deductions_monthly` | retailer x reason x deduction month |
| metrics | `m_reason_recovery` | reason code |
| metrics | `m_recoverable_candidates` | never-disputed open or written-off deduction |
| metrics | `m_recovery_scenarios` | dispute window x scenario |

Authoritative grain statements are in each layer's `schema.yml`.

## Lineage (generated from dbt's manifest by `scripts/lineage.py`)

```mermaid
flowchart LR
    subgraph raw[raw schema - synthetic]
        raw_deductions[deductions]
        raw_disputes[disputes]
        raw_invoice_lines[invoice_lines]
        raw_invoices[invoices]
        raw_payments[payments]
        raw_promotions[promotions]
        raw_retailers[retailers]
        raw_skus[skus]
    end
    subgraph staging[staging]
        stg_deductions[stg_deductions]
        stg_disputes[stg_disputes]
        stg_invoice_lines[stg_invoice_lines]
        stg_invoices[stg_invoices]
        stg_payments[stg_payments]
        stg_promotions[stg_promotions]
        stg_retailers[stg_retailers]
        stg_skus[stg_skus]
    end
    subgraph intermediate[intermediate]
        int_deduction_disputes[int_deduction_disputes]
        int_invoice_deductions[int_invoice_deductions]
        int_invoice_lines[int_invoice_lines]
        int_invoice_payments[int_invoice_payments]
    end
    subgraph marts[marts]
        dim_retailer[dim_retailer]
        dim_sku[dim_sku]
        fct_deductions[fct_deductions]
        fct_disputes[fct_disputes]
        fct_invoices[fct_invoices]
        fct_promotions[fct_promotions]
    end
    subgraph metrics[metrics]
        m_deduction_detail[m_deduction_detail]
        m_deductions_monthly[m_deductions_monthly]
        m_invoice_detail[m_invoice_detail]
        m_reason_recovery[m_reason_recovery]
        m_recoverable_candidates[m_recoverable_candidates]
        m_recovery_scenarios[m_recovery_scenarios]
        m_retailer_month[m_retailer_month]
    end
    stg_retailers --> dim_retailer
    stg_skus --> dim_sku
    int_deduction_disputes --> fct_deductions
    stg_invoices --> fct_deductions
    fct_deductions --> fct_disputes
    stg_disputes --> fct_disputes
    int_invoice_deductions --> fct_invoices
    int_invoice_lines --> fct_invoices
    int_invoice_payments --> fct_invoices
    stg_invoices --> fct_invoices
    stg_promotions --> fct_promotions
    stg_deductions --> int_deduction_disputes
    stg_disputes --> int_deduction_disputes
    int_deduction_disputes --> int_invoice_deductions
    stg_invoice_lines --> int_invoice_lines
    stg_payments --> int_invoice_payments
    fct_deductions --> m_deduction_detail
    fct_invoices --> m_deduction_detail
    m_deduction_detail --> m_deductions_monthly
    fct_invoices --> m_invoice_detail
    m_deduction_detail --> m_reason_recovery
    m_deduction_detail --> m_recoverable_candidates
    m_reason_recovery --> m_recoverable_candidates
    m_invoice_detail --> m_retailer_month
    raw_deductions --> stg_deductions
    raw_disputes --> stg_disputes
    raw_invoice_lines --> stg_invoice_lines
    raw_invoices --> stg_invoices
    raw_payments --> stg_payments
    raw_promotions --> stg_promotions
    raw_retailers --> stg_retailers
    raw_skus --> stg_skus
```
