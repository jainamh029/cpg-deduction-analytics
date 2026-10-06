"""Hygiene: metrics are defined once and reused; analysis SQL and dashboard code read only marts/metrics.

Rules (checked on analysis SQL and dashboard code):
  1. no reads from raw / raw_dirty / staging / intermediate
  2. no re-implementation of metric logic (bucket labels, win/validity classification, date_diff on
     deduction/dispute dates, ratio of two aggregates)
  3. analysis SQL may not divide numbers unless the line carries `-- non-metric: <reason>`
"""

import re
from pathlib import Path

import pytest

from .helpers import REPO_ROOT

SCHEMA_READ = re.compile(r"\b(from|join)\s+(raw|raw_dirty|staging|intermediate)\.", re.I)
FORMULAS = [
    (re.compile(r"'(0-30|31-60|61-90)'"), "aging bucket labels belong in metrics.aging_bucket"),
    (re.compile(r"'(0-14|15-30)'"), "filing-lag bucket labels belong in metrics.filing_lag_bucket"),
    (re.compile(r"outcome\s+in\s*\(\s*'won'", re.I), "use metrics.is_win / is_resolved"),
    (re.compile(r"status\s+in\s*\(\s*'open'", re.I), "use metrics.open_amount"),
    (
        re.compile(
            r"date_diff\(\s*'day'\s*,\s*(deduction_date|filed_date|invoice_date|due_date)", re.I
        ),
        "use the metrics.* date macros",
    ),  # fmt: skip
    (
        re.compile(r"sum\([^()]*\)\s*(filter\s*\([^)]*\)\s*)?/", re.I),
        "ratio of aggregates: use a metrics.* macro",
    ),  # fmt: skip
]
ANNOTATION = "-- non-metric:"


def strip_sql(line: str) -> str:
    code = line.split("--", 1)[0]
    return re.sub(r"'[^']*'", "''", code)


def violations(text: str, *, check_division: bool) -> list[str]:
    found = []
    for n, line in enumerate(text.splitlines(), start=1):
        code = line.split("--", 1)[0]
        if SCHEMA_READ.search(code):
            found.append(f"line {n}: reads a non-mart schema")
        for pattern, why in FORMULAS:
            if pattern.search(code):
                found.append(f"line {n}: {why}")
        if check_division and "/" in strip_sql(line) and ANNOTATION not in line:
            found.append(f"line {n}: division without '{ANNOTATION}' annotation")
    return found


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("select * from raw.invoices", 1),
        ("select * from staging.stg_deductions", 1),
        ("select case when age <= 30 then '0-30' end", 1),
        ("select count(*) filter (where outcome in ('won', 'partial'))", 1),
        ("select sum(deduction_amount) / sum(gross_amount) from x", 2),  # formula + bare division
        ("select a / b -- non-metric: z-score", 0),
        ("select metrics.deduction_rate(sum(a), sum(b)) from marts.fct_invoices", 0),
        ("select 1 -- a/b in a comment", 0),
    ],
)
def test_checker_catches_violations(sql, expected):
    assert len(violations(sql, check_division=True)) == expected


ANALYSIS_FILES = sorted((REPO_ROOT / "sql" / "analysis").glob("*.sql"))
DASHBOARD_FILES = sorted((REPO_ROOT / "dashboard").rglob("*.py"))


@pytest.mark.parametrize("path", ANALYSIS_FILES, ids=lambda p: p.name)
def test_analysis_sql_reuses_the_metrics_layer(path: Path):
    assert violations(path.read_text(), check_division=True) == []


@pytest.mark.parametrize("path", DASHBOARD_FILES, ids=lambda p: p.name)
def test_dashboard_code_reuses_the_metrics_layer(path: Path):
    assert violations(path.read_text(), check_division=False) == []


def test_metric_views_contain_no_division():
    for path in (REPO_ROOT / "models" / "metrics").glob("*.sql"):
        text = re.sub(r"\{\{.*?\}\}", "", path.read_text())
        divisions = [ln for ln in text.splitlines() if "/" in strip_sql(ln)]
        assert divisions == [], path.name


def test_each_metric_macro_is_defined_exactly_once():
    text = (REPO_ROOT / "macros" / "metric_definitions.sql").read_text()
    names = re.findall(r"create or replace macro metrics\.(\w+)", text)
    assert len(names) == len(set(names)) >= 20
    other_macros = [
        p for p in (REPO_ROOT / "macros").glob("*.sql") if p.name != "metric_definitions.sql"
    ]
    for path in other_macros:
        assert "macro metrics." not in path.read_text()
