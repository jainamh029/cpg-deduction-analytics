"""Metric tests on a tiny hand-built fixture (tests/fixtures/metrics_fixture.sql).

Every expected value below is hand arithmetic written out in the test, never copied from output.
Fixture facts (as-of 2024-06-30), see the fixture file header for the invoices:
  deductions D1..D7 = 60, 40, 120, 80, 200, 100, 50  (total 650; R1 300, R2 350)
  gross = 1000 + 2000 + 3000 + 700 = 6700 (R1 3000, R2 3700); recovered = 60 + 120 = 180
"""

import datetime

import duckdb
import pytest

from .helpers import REPO_ROOT, run_dbt

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "metrics_fixture.sql"
DDL = REPO_ROOT / "warehouse" / "ddl.sql"


@pytest.fixture(scope="module")
def fx(tmp_path_factory):
    path = tmp_path_factory.mktemp("fixture") / "fixture.duckdb"
    con = duckdb.connect(str(path))
    con.execute(DDL.read_text())
    con.execute(FIXTURE.read_text())
    con.close()
    result = run_dbt(
        "build", "--vars", "{as_of_date: '2024-06-30'}",
        warehouse=path, target_path=path.parent / "target",
    )  # fmt: skip
    assert result.returncode == 0, result.stdout[-3000:]  # includes the dbt data tests
    connection = duckdb.connect(str(path), read_only=True)
    yield connection
    connection.close()


def one(con, sql):
    return con.execute(sql).fetchone()[0]


def rows(con, sql):
    return con.execute(sql).fetchall()


def test_fixture_reconciles_by_construction(fx):
    assert one(fx, "select sum(gross_amount) from marts.fct_invoices") == 6700
    assert one(fx, "select sum(amount) from marts.fct_deductions") == 650


def test_1_deduction_rate(fx):
    total = "select metrics.deduction_rate(sum(deduction_amount), sum(gross_amount)) from metrics.m_retailer_month"
    assert one(fx, total) == pytest.approx(650 / 6700)
    by_retailer = rows(
        fx,
        "select retailer_id, metrics.deduction_rate(sum(deduction_amount), sum(gross_amount)) "
        "from metrics.m_retailer_month group by 1 order by 1",
    )
    assert by_retailer == [(1, pytest.approx(300 / 3000)), (2, pytest.approx(350 / 3700))]
    may = one(
        fx,
        "select deduction_rate from metrics.m_retailer_month where retailer_id = 2 and invoice_month = '2024-05-01'",
    )
    assert may == pytest.approx(50 / 700)
    assert one(fx, "select metrics.deduction_rate(5, 0)") is None  # zero denominator


def test_2_recovery_rate(fx):
    sql = "select metrics.recovery_rate(sum(recovered_amount), sum(deduction_amount)) from metrics.m_retailer_month"
    assert one(fx, sql) == pytest.approx(180 / 650)
    by_retailer = rows(
        fx,
        "select retailer_id, metrics.recovery_rate(sum(recovered_amount), sum(deduction_amount)) "
        "from metrics.m_retailer_month group by 1 order by 1",
    )
    assert by_retailer == [(1, pytest.approx(60 / 300)), (2, pytest.approx(120 / 350))]
    assert one(fx, "select metrics.recovery_rate(0, 0)") is None


def test_3_net_revenue(fx):
    assert one(fx, "select sum(net_revenue) from metrics.m_invoice_detail") == pytest.approx(
        6700 - 650 + 180
    )
    by_retailer = rows(
        fx,
        "select retailer_id, sum(net_revenue) from metrics.m_invoice_detail group by 1 order by 1",
    )
    assert by_retailer == [
        (1, pytest.approx(3000 - 300 + 60)),
        (2, pytest.approx(3700 - 350 + 120)),
    ]
    assert one(
        fx, "select net_revenue from metrics.m_invoice_detail where invoice_id = 1"
    ) == pytest.approx(1000 - 100 + 60)


def test_4_open_deduction_balance(fx):
    # open or disputed: D4 (80, pending dispute), D6 (100), D7 (50). Recovered/accepted/written off excluded.
    assert one(fx, "select sum(open_amount) from metrics.m_deduction_detail") == pytest.approx(
        80 + 100 + 50
    )
    by_retailer = rows(
        fx,
        "select retailer_id, sum(open_amount) from metrics.m_deduction_detail group by 1 order by 1",
    )
    assert by_retailer == [(1, pytest.approx(80)), (2, pytest.approx(100 + 50))]


def test_5_aging_buckets(fx):
    # Age = days from deduction date to 2024-06-30: D4 Mar10 -> 21+30+31+30 = 112; D6 Apr15 -> 15+31+30 = 76;
    # D7 May10 -> 21+30 = 51.
    ages = dict(
        rows(
            fx,
            "select deduction_id, age_days from metrics.m_deduction_detail where deduction_id in (4, 6, 7)",
        )
    )
    assert ages == {4: 112, 6: 76, 7: 51}
    buckets = rows(
        fx,
        "select aging_bucket, sum(open_amount) from metrics.m_deduction_detail "
        "where open_amount > 0 group by 1 order by 1",
    )
    assert buckets == [
        ("31-60", pytest.approx(50)),
        ("61-90", pytest.approx(100)),
        ("90+", pytest.approx(80)),
    ]


@pytest.mark.parametrize(
    ("age", "bucket"),
    [
        (0, "0-30"),
        (30, "0-30"),
        (31, "31-60"),
        (60, "31-60"),
        (61, "61-90"),
        (90, "61-90"),
        (91, "90+"),
    ],
)
def test_5_aging_bucket_boundaries(fx, age, bucket):
    assert one(fx, f"select metrics.aging_bucket({age})") == bucket


def test_6_days_to_resolve(fx):
    # X1 Feb5 -> Mar6 (2024 is a leap year: 24 + 6 = 30); X2 Mar31 -> Apr20 = 20; X4 Feb20 -> Mar21 = 9 + 21 = 30.
    got = dict(
        rows(
            fx,
            "select deduction_id, days_to_resolve from metrics.m_deduction_detail where is_disputed",
        )
    )
    assert got == {1: 30, 3: 20, 4: None, 5: 30}  # D4's dispute is pending -> NULL
    assert one(fx, "select avg(days_to_resolve) from metrics.m_deduction_detail") == pytest.approx(
        (30 + 20 + 30) / 3
    )
    assert one(fx, "select median(days_to_resolve) from metrics.m_deduction_detail") == 30


def test_7_dispute_win_rate(fx):
    # Resolved: X1 won, X2 lost, X4 partial -> 2 wins of 3. X3 is pending and excluded.
    sql = "select metrics.dispute_win_rate(count(*) filter (where is_win), count(*) filter (where is_resolved)) from metrics.m_deduction_detail"
    assert one(fx, sql) == pytest.approx(2 / 3)
    by_reason = dict(rows(fx, "select reason_code, win_rate from metrics.m_reason_recovery"))
    assert by_reason["shortage"] == pytest.approx(2 / 2)
    assert by_reason["compliance_fine"] == pytest.approx(0 / 1)
    assert by_reason["pricing"] is None  # only a pending dispute: no resolved disputes, no rate
    assert by_reason["damage"] is None  # never disputed


def test_8_dispute_rate(fx):
    # Disputed deductions: D1 60 + D3 120 + D4 80 + D5 200 = 460 of 650.
    sql = "select metrics.dispute_rate(sum(amount) filter (where is_disputed), sum(amount)) from metrics.m_deduction_detail"
    assert one(fx, sql) == pytest.approx(460 / 650)


def test_9_valid_vs_invalid_share(fx):
    # invalid (won/partial): D1 60 + D5 200 = 260; valid (lost or accepted): D3 120;
    # unresolved (open/pending): D4 80 + D6 100 + D7 50 = 230; undetermined (written off, undisputed): D2 40.
    got = dict(
        rows(fx, "select validity_class, sum(amount) from metrics.m_deduction_detail group by 1")
    )
    assert got == {
        "invalid": pytest.approx(260), "valid": pytest.approx(120),
        "unresolved": pytest.approx(230), "undetermined": pytest.approx(40),
    }  # fmt: skip
    sql = (
        "select metrics.invalid_share(sum(amount) filter (where validity_class = 'invalid'), "
        "sum(amount) filter (where validity_class = 'valid')) from metrics.m_deduction_detail"
    )
    assert one(fx, sql) == pytest.approx(260 / (260 + 120))


def test_10_payment_lag(fx):
    # Days to pay: I1 Jan10 -> Feb14 = 35; I2 Feb15 -> Mar26 = 40; I3 Jan20 -> Mar5 = 45. Past due: 5, 10, 15.
    got = rows(
        fx, "select invoice_id, days_to_pay, days_past_due from metrics.m_invoice_detail order by 1"
    )
    assert got == [(1, 35, 5), (2, 40, 10), (3, 45, 15), (4, None, None)]
    expected = (35 * 900 + 40 * 1800 + 45 * 2700) / (900 + 1800 + 2700)
    assert one(
        fx, "select metrics.payment_lag(days_to_pay, payments_amount) from metrics.m_invoice_detail"
    ) == pytest.approx(expected)


def test_11_recoverable_dollars(fx):
    # Never-disputed and open/written off: D2 (promo), D6 (damage), D7 (shortage). Only shortage has
    # dispute history: win rate 2/2, win recovery ratio = (60 + 120) / (60 + 200) = 180 / 260.
    ids = {r[0] for r in rows(fx, "select deduction_id from metrics.m_recoverable_candidates")}
    assert ids == {2, 6, 7}
    assert one(
        fx,
        "select win_recovery_ratio from metrics.m_reason_recovery where reason_code = 'shortage'",
    ) == pytest.approx(180 / 260)
    total = one(fx, "select sum(expected_recovery) from metrics.m_recoverable_candidates")
    assert total == pytest.approx(
        50 * (2 / 2) * (180 / 260)
    )  # D2 and D6 have no basis -> NULL, not counted


def test_filing_lag_cohorts(fx):
    # Filing lag: D1 Jan25 -> Feb5 = 11; D5 Feb10 -> Feb20 = 10; D3 Mar1 -> Mar31 = 30; D4 Mar10 -> Jun1 = 83.
    got = dict(
        rows(
            fx,
            "select deduction_id, filing_lag_bucket from metrics.m_deduction_detail where is_disputed",
        )
    )
    assert got == {1: "0-14", 5: "0-14", 3: "15-30", 4: "61+"}
    sql = (
        "select filing_lag_bucket, metrics.dispute_win_rate(count(*) filter (where is_win), "
        "count(*) filter (where is_resolved)) from metrics.m_deduction_detail "
        "where is_disputed group by 1 order by 1"
    )
    assert rows(fx, sql) == [
        ("0-14", pytest.approx(2 / 2)),
        ("15-30", pytest.approx(0 / 1)),
        ("61+", None),
    ]


def test_unattributed_sku_bucket(fx):
    # sku 1: D1 60 + D4 80 + D7 50 = 190; sku 2: D3 120 + D5 200 = 320; unattributed (-1): D2 40 + D6 100 = 140.
    got = dict(rows(fx, "select sku_key, sum(amount) from metrics.m_deduction_detail group by 1"))
    assert got == {1: pytest.approx(190), 2: pytest.approx(320), -1: pytest.approx(140)}
    assert sum(got.values()) == pytest.approx(650)  # nothing dropped


def test_data_completeness_flags(fx):
    # Mature if month + 4 months <= 2024-06-30: Jan and Feb yes, May no.
    flags = rows(
        fx,
        "select retailer_id, invoice_month, is_mature_month from metrics.m_retailer_month order by 1, 2",
    )
    assert [f[2] for f in flags] == [True, True, True, False]
    # First invoice 2024-01-10, so deduction months before 2024-04-01 are ramp-up (Jan, Feb, Mar).
    burn = dict(
        rows(
            fx,
            "select deduction_month, bool_and(is_burn_in_month) from metrics.m_deduction_detail group by 1",
        )
    )
    assert burn[datetime.date(2024, 3, 1)] is True
    assert burn[datetime.date(2024, 4, 1)] is False


def test_monthly_deduction_grain(fx):
    # Retailer 1, shortage, Jan 2024: only D1 = 60 (disputed 60, recovered 60).
    row = rows(
        fx,
        "select deduction_amount, disputed_amount, recovered_amount, dispute_rate from metrics.m_deductions_monthly "
        "where retailer_id = 1 and reason_code = 'shortage'",
    )
    assert row == [(pytest.approx(60), pytest.approx(60), pytest.approx(60), pytest.approx(1.0))]
