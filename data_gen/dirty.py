"""Pattern 6: inject a small, known number of data-quality defects into a COPY of the clean data."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .generate import Tables

N_ORPHANED_DEDUCTIONS = 3
N_DUPLICATE_PAYMENTS = 3
N_NEGATIVE_AMOUNTS = 3

# What the validator must report on the dirty load, per rule. A duplicate payment also overpays
# its invoice, so the same three invoices appear under the reconciliation rule.
EXPECTED_DIRTY_FINDINGS = {
    "fk_deductions_invoice": N_ORPHANED_DEDUCTIONS,
    "duplicate_payments": N_DUPLICATE_PAYMENTS,
    "recon_overpaid_invoice": N_DUPLICATE_PAYMENTS,
    "nonpositive_deduction_amount": N_NEGATIVE_AMOUNTS,
}


def inject_defects(clean: Tables, seed: int) -> Tables:
    rng = np.random.default_rng([seed, 6])
    tables = {name: df.copy() for name, df in clean.items()}

    payments = tables["payments"]
    big = payments.index[payments["paid_amount"] > 1000].to_numpy()
    dup_rows = rng.choice(big, N_DUPLICATE_PAYMENTS, replace=False)
    dups = payments.loc[dup_rows].copy()
    dups["payment_id"] = payments["payment_id"].max() + 1 + np.arange(N_DUPLICATE_PAYMENTS)
    tables["payments"] = pd.concat([payments, dups], ignore_index=True)
    dup_invoices = set(dups["invoice_id"])

    deductions = tables["deductions"]
    disputed = set(tables["disputes"]["deduction_id"])
    eligible = deductions[
        ~deductions["deduction_id"].isin(disputed) & ~deductions["invoice_id"].isin(dup_invoices)
    ]
    neg_rows = rng.choice(eligible.index.to_numpy(), N_NEGATIVE_AMOUNTS, replace=False)
    deductions.loc[neg_rows, "amount"] = -deductions.loc[neg_rows, "amount"]

    positive = deductions[deductions["amount"] > 0]
    template = positive.iloc[rng.choice(len(positive), N_ORPHANED_DEDUCTIONS, replace=False)]
    orphans = template.copy()
    orphans["deduction_id"] = (
        deductions["deduction_id"].max() + 1 + np.arange(N_ORPHANED_DEDUCTIONS)
    )
    orphans["invoice_id"] = (
        tables["invoices"]["invoice_id"].max() + 1000 + np.arange(N_ORPHANED_DEDUCTIONS)
    )
    orphans["status"] = "open"
    tables["deductions"] = pd.concat([deductions, orphans], ignore_index=True)
    return tables
