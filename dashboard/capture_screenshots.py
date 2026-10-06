"""Capture REAL screenshots of the running Streamlit dashboard with headless Google Chrome.

Usage: make screenshots   (needs `make build forecast`, Google Chrome installed, and the
`screenshots` extra: pip install -e ".[screenshots]"). Nothing is mocked: each PNG is a browser
screenshot of the live app. If Chrome is missing this script fails instead of producing placeholders.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "screenshots"
PORT = 8599
PAGES = {
    "sales": ("1_retailer_performance.png", "Retailer performance"),
    "ops": ("2_deduction_operations.png", "Deduction operations"),
    "cfo": ("3_cash_impact.png", "Cash impact"),
}


def wait_for_server(timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://localhost:{PORT}/_stcore/health", timeout=2):
                return
        except OSError:
            time.sleep(0.5)
    raise RuntimeError("Streamlit server did not start")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    server = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "dashboard/app.py", "--server.headless", "true",
         "--server.port", str(PORT), "--browser.gatherUsageStats", "false"],
        cwd=ROOT, env={**os.environ}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )  # fmt: skip
    try:
        wait_for_server()
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 3000})
            for key, (filename, heading) in PAGES.items():
                page.goto(f"http://localhost:{PORT}/?page={key}")
                page.get_by_role("heading", name=heading).wait_for(timeout=60000)
                page.wait_for_selector("[data-testid='stVegaLiteChart']", timeout=60000)
                page.wait_for_timeout(2500)  # let charts finish rendering
                page.screenshot(path=str(OUT / filename), full_page=True)
                print(f"captured {OUT / filename}")
            browser.close()
    finally:
        server.terminate()
        server.wait(timeout=15)


if __name__ == "__main__":
    main()
