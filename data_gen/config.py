"""Configuration for the SYNTHETIC data generator. All values are fictional."""

from dataclasses import dataclass
from datetime import date

REASONS = ("shortage", "promo", "compliance_fine", "pricing", "damage", "other")
CHANNELS = ("grocery", "mass", "club", "drug", "convenience", "ecommerce")
PROMO_TYPES = ("tpr", "bogo", "display", "feature", "coupon")
CATEGORIES = ("Snacks", "Beverages", "Frozen", "Pantry", "Household", "Personal Care")

# Retailer share of revenue, ids 1..12 (Retailer A..L). Retailers A (1) and B (2) carry patterns.
RETAILER_SHARES = (0.16, 0.14, 0.12, 0.10, 0.09, 0.08, 0.075, 0.07, 0.06, 0.05, 0.04, 0.035)
RETAILER_A = 1
RETAILER_B = 2
RETAILER_ANOMALY = 5  # one-off shortage spike (pattern 7, used to test anomaly detection)
ANOMALY_INVOICE_MONTH = date(2025, 4, 1)
ANOMALY_MULTIPLIER = 5.0
PROBLEM_SKUS = (41, 187)  # the two SKUs behind Retailer A's compliance fines

MONTH_SEASONALITY = (0.92, 0.90, 0.97, 0.98, 1.00, 0.98, 0.94, 0.95, 1.00, 1.08, 1.14, 1.14)

# Per-reason deduction model: probability an invoice carries this reason, mean size as a share
# of invoice gross (compliance fines are a flat dollar amount instead), SKU null probability,
# probability the deduction is disputed, and probability a resolved dispute is won/partial.
REASON_PARAMS = {
    "shortage": {"p": 0.20, "frac": 0.050, "sku_null": 0.40, "dispute": 0.18, "win": 0.80},
    "promo": {"p": 0.18, "frac": 0.090, "sku_null": 0.70, "dispute": 0.06, "win": 0.45},
    "compliance_fine": {"p": 0.10, "flat": 350.0, "sku_null": 0.20, "dispute": 0.35, "win": 0.50},
    "pricing": {"p": 0.15, "frac": 0.040, "sku_null": 0.40, "dispute": 0.40, "win": 0.65},
    "damage": {"p": 0.12, "frac": 0.030, "sku_null": 0.40, "dispute": 0.30, "win": 0.45},
    "other": {"p": 0.14, "frac": 0.030, "sku_null": 0.80, "dispute": 0.35, "win": 0.50},
}


@dataclass(frozen=True)
class Config:
    seed: int = 20260101
    start_date: date = date(2023, 1, 1)
    end_date: date = date(2025, 12, 31)  # also the "as of" date for ageing
    n_skus: int = 300
    annual_revenue: float = 150_000_000.0  # mid-history annual run rate
    yoy_growth: float = 0.08
    revenue_scale: float = 1.0  # shrink volume for fast unit tests
