"""Build the two-page static site (home + interactive dashboard) for GitHub Pages into site/ (SYNTHETIC data).

Home page numbers are filled from docs/findings.json; the dashboard reads cubes exported from the warehouse.
Usage: python -m scripts.build_site
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from data_gen.load import DEFAULT_PATH
from scripts.export_dashboard_data import export
from scripts.render_readme import render

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
SRC = ROOT / "site_src"


def chart_data(f: dict) -> dict:
    """The slice of findings.json the home page's interactive charts need."""
    return {
        "headline": {k: f["headline"][k] for k in ("gross", "deductions", "recovered")},
        "waterfall": f["waterfall"],
        "finding1": {
            k: f["finding1"][k] for k in ("shortage_win_rate", "shortage_dispute_rate", "by_reason")
        },
        "finding2": {
            k: f["finding2"][k]
            for k in ("retailer", "top2_share_of_all", "top2_skus", "chart_rows")
        },
        "finding3": {k: f["finding3"][k] for k in ("median_spike_index", "monthly")},
    }


def build() -> None:
    findings = json.loads((ROOT / "docs" / "findings.json").read_text())
    shutil.rmtree(SITE, ignore_errors=True)
    (SITE / "dashboard").mkdir(parents=True)
    shutil.copytree(SRC / "assets", SITE / "assets")
    (SITE / ".nojekyll").write_text("")
    page = render((SRC / "index.html").read_text(), findings)
    payload = json.dumps(chart_data(findings), separators=(",", ":")).replace("</", "<\\/")
    (SITE / "index.html").write_text(page.replace("__FINDINGS_JSON__", payload))
    shutil.copy(SRC / "dashboard.html", SITE / "dashboard" / "index.html")
    (SITE / "dashboard" / "data.json").write_text(
        json.dumps(export(DEFAULT_PATH), separators=(",", ":"))
    )
    print(
        f"built {SITE.relative_to(ROOT)}: index.html, dashboard/index.html, dashboard/data.json, assets/"
    )


if __name__ == "__main__":
    build()
