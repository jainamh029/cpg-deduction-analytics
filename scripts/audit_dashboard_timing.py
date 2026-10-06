"""Audit: how long does each dashboard page take to load on the full dataset?

Measures (1) the page's data functions alone, (2) a headless Streamlit AppTest run, and (3) real Chrome:
navigation until every chart has rendered. Prints medians; run twice to compare cold and warm.
Usage: python -m scripts.audit_dashboard_timing   (needs `make build forecast`, Chrome and the screenshots extra)
"""

from __future__ import annotations

import os
import statistics
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright
from streamlit.testing.v1 import AppTest

from dashboard import data
from dashboard.capture_screenshots import PAGES, ROOT, wait_for_server

PORT = 8598
PAGE_FUNCTIONS = {
    "sales": [
        data.sales_kpis,
        data.retailer_scorecard,
        data.monthly_rate_by_retailer,
        data.trend_halves,
    ],
    "ops": [
        data.ops_kpis,
        data.aging_by_reason,
        data.reason_mix,
        data.filing_cohorts,
        data.worklist,
    ],
    "cfo": [
        data.cash_kpis,
        data.recoverable_grid,
        data.open_balance_by_retailer,
        data.deduction_history,
    ],
}


def timed(fn, repeat: int = 5) -> float:
    fn()
    runs = []
    for _ in range(repeat):
        start = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - start)
    return statistics.median(runs)


def main() -> None:
    con = data.connect()
    lo, hi = data.invoice_date_range(con)
    f = data.Filters(
        tuple(int(i) for i in data.retailers(con)["retailer_id"]),
        lo,
        hi,
        tuple(data.reason_codes(con)),
    )
    print("page   data functions   AppTest page run   Chrome until charts rendered (cold / warm)")
    app_times = {}
    for page, fns in PAGE_FUNCTIONS.items():
        fn_time = timed(lambda fns=fns: [fn(con, f) for fn in fns])
        app = AppTest.from_file(str(ROOT / "dashboard" / "app.py"), default_timeout=90)
        app.run()
        app.sidebar.radio[0].set_value(page)
        app_times[page] = timed(lambda app=app: app.run(), repeat=3)
        print(f"{page:<6} {fn_time * 1000:8.0f} ms   {app_times[page] * 1000:10.0f} ms", flush=True)
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "dashboard/app.py", "--server.headless", "true", "--server.port", str(PORT),
         "--browser.gatherUsageStats", "false"], cwd=ROOT, env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # fmt: skip
    try:
        wait_for_server(PORT)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for key, (_, heading) in PAGES.items():
                times = []
                for _ in range(3):
                    page = browser.new_page(viewport={"width": 1440, "height": 3000})
                    start = time.perf_counter()
                    page.goto(f"http://localhost:{PORT}/?page={key}")
                    page.get_by_role("heading", name=heading).wait_for(timeout=60000)
                    page.wait_for_function(
                        "document.querySelectorAll(\"[data-testid='stVegaLiteChart'] canvas, [data-testid='stVegaLiteChart'] svg\").length >= 3",
                        timeout=60000,
                    )
                    times.append(time.perf_counter() - start)
                    page.close()
                print(
                    f"{key:<6} chrome load: cold {times[0]:.2f}s, warm median {statistics.median(times[1:]):.2f}s, max {max(times):.2f}s"
                )
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)


if __name__ == "__main__":
    main()
