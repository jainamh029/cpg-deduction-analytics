"""The GitHub Pages site: two pages only (home and dashboard), every home-page number resolves from findings.json."""

import json
import re

from scripts.build_site import SRC, chart_data
from scripts.render_readme import TOKEN, lookup, render

from .helpers import REPO_ROOT


def findings() -> dict:
    return json.loads((REPO_ROOT / "docs" / "findings.json").read_text())


def test_home_page_numbers_all_resolve_and_nothing_is_left_unrendered():
    page = render((SRC / "index.html").read_text(), findings())
    assert "{{ " not in page and " }}" not in page
    for match in TOKEN.finditer((SRC / "index.html").read_text()):
        path = match.group(1).partition("|")[0]
        assert lookup(findings(), path) is not None, path


def test_chart_data_has_what_the_home_page_charts_read():
    data = chart_data(findings())
    assert (
        len(data["waterfall"]) == 9
        and data["finding2"]["chart_rows"]
        and data["finding3"]["monthly"]
    )
    assert set(data["finding1"]["by_reason"]) >= {"shortage", "promo"}


def test_site_has_only_the_two_pages_and_no_interview_material():
    sources = {p.name for p in SRC.iterdir()}
    assert sources == {"index.html", "dashboard.html", "assets"}
    for path in [*SRC.rglob("*.html"), *SRC.rglob("*.js"), REPO_ROOT / "scripts" / "build_site.py"]:
        assert not re.search(r"interview", path.read_text(), re.I), path.name
    assert not (REPO_ROOT / "docs" / "INTERVIEW_QA.md").exists()
