"""Assemble a GitHub Pages (Jekyll) site in site/ from the repo's markdown, images and reports (SYNTHETIC data).

The Streamlit dashboard needs a Python server, so Pages shows its real screenshots instead. Links to files that are not
part of the site (SQL, code) are rewritten to the GitHub blob URL. Usage: python -m scripts.build_site [--repo owner/name]
"""

from __future__ import annotations

import argparse
import json
import posixpath
import re
import shutil
from pathlib import Path

from data_gen.load import DEFAULT_PATH

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"
PAGES = {  # repo path -> site path
    "README.md": "memo.md",
    "PLANTED_PATTERNS.md": "PLANTED_PATTERNS.md",
    "forecast/RESULTS.md": "forecast/RESULTS.md",
    **{f"docs/{n}": f"docs/{n}" for n in (
        "AUDIT_REPORT.md", "AUDIT_LOG.md", "INTERVIEW_QA.md", "METRICS.md", "DECISIONS.md", "FINAL_REPORT.md",
        "PERFORMANCE.md", "METABASE_NOTES.md", "data_model.md", "BUILD_LOG.md",
    )},
}  # fmt: skip
ASSET_DIRS = ["docs/img", "dashboard/screenshots"]
SITE_ONLY = {"memo.html", "dashboard/"}  # pages that exist only in the built site
LINK = re.compile(r"(\]\()([^)\s]+)(\))")

LAYOUT = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ page.title | default: "CPG Deduction Analytics (synthetic data)" }}</title>
<style>
 :root{--ink:#1f2937;--muted:#64748b;--accent:#2563eb;--bg:#fff;--soft:#f1f5f9}
 @media (prefers-color-scheme: dark){:root{--ink:#e5e7eb;--muted:#94a3b8;--accent:#60a5fa;--bg:#0f172a;--soft:#1e293b}}
 body{font:16px/1.6 -apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:var(--bg);margin:0}
 header{background:var(--soft);border-bottom:1px solid #cbd5e1;padding:.6rem 1rem}
 header a{margin-right:1rem;color:var(--accent);text-decoration:none;font-size:.9rem}
 .banner{background:#fef3c7;color:#78350f;padding:.5rem 1rem;font-size:.9rem}
 main{max-width:60rem;margin:0 auto;padding:1rem}
 img{max-width:100%;height:auto} table{border-collapse:collapse;display:block;overflow-x:auto}
 th,td{border:1px solid #cbd5e1;padding:.3rem .6rem;text-align:left;vertical-align:top}
 pre{background:var(--soft);padding:.8rem;overflow-x:auto} code{background:var(--soft);padding:0 .2rem}
 pre code{padding:0} a{color:var(--accent)}
</style></head><body>
<div class="banner"><strong>All data is synthetic.</strong> Not Confido's data or schema; findings demonstrate a method on planted patterns.</div>
<header><a href="{{ site.baseurl }}/">Overview</a><a href="{{ site.baseurl }}/dashboard/"><strong>Dashboard</strong></a><a href="{{ site.baseurl }}/memo.html">Findings memo</a><a href="{{ site.baseurl }}/docs/AUDIT_REPORT.html">Audit report</a>
<a href="{{ site.baseurl }}/docs/INTERVIEW_QA.html">Interview Q&amp;A</a><a href="{{ site.baseurl }}/docs/METRICS.html">Metrics</a>
<a href="{{ site.baseurl }}/docs/data_model.html">Data model</a><a href="{{ site.baseurl }}/forecast/RESULTS.html">Forecast</a>
<a href="{{ site.baseurl }}/PLANTED_PATTERNS.html">Planted patterns</a><a href="{{ site.baseurl }}/docs/DECISIONS.html">Decisions</a>
<a href="https://github.com/{{ site.github.repository_nwo }}">Source</a></header>
<main>{{ content }}</main>
<script type="module">
 import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs";
 document.querySelectorAll("pre > code.language-mermaid").forEach(c => {
   const d = document.createElement("div"); d.className = "mermaid"; d.textContent = c.textContent; c.parentElement.replaceWith(d);
 });
 mermaid.initialize({startOnLoad: false, theme: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "default"});
 mermaid.run();
</script></body></html>
"""


def rewrite(text: str, source: str, repo: str) -> str:
    folder = posixpath.dirname(source)

    def fix(match: re.Match) -> str:
        target = match.group(2)
        if re.match(r"^(https?:|mailto:|#)", target):
            return match.group(0)
        path, _, anchor = target.partition("#")
        if path in SITE_ONLY:
            return match.group(0)
        resolved = posixpath.normpath(posixpath.join(folder, path))
        in_site = resolved in PAGES or any(resolved.startswith(d + "/") for d in ASSET_DIRS)
        if in_site:
            new = PAGES.get(resolved, resolved)
            rel = posixpath.relpath(new, posixpath.dirname(PAGES[source]) or ".")
            if rel.endswith(".md"):
                rel = rel[:-3] + ".html"
            return f"{match.group(1)}{rel}{'#' + anchor if anchor else ''}{match.group(3)}"
        kind = "tree" if (ROOT / resolved).is_dir() else "blob"
        return f"{match.group(1)}https://github.com/{repo}/{kind}/main/{resolved}{'#' + anchor if anchor else ''}{match.group(3)}"

    return LINK.sub(fix, text)


def landing(repo: str) -> str:
    """The plain-English overview page: site_src/index.md with numbers filled from docs/findings.json."""
    from scripts.render_readme import render

    findings = json.loads((ROOT / "docs" / "findings.json").read_text())
    text = render((ROOT / "site_src" / "index.md").read_text(), findings)
    text = text.replace("{: .button }", "")
    return rewrite(text, "README.md", repo).replace("memo.html#", "memo.html#")


def build(repo: str) -> None:
    shutil.rmtree(SITE, ignore_errors=True)
    (SITE / "_layouts").mkdir(parents=True)
    (SITE / "_layouts" / "default.html").write_text(LAYOUT)
    (SITE / "_config.yml").write_text(
        "title: CPG Deduction Analytics (synthetic data)\nmarkdown: kramdown\nkramdown:\n  input: GFM\n  hard_wrap: false\n"
        "plugins:\n  - jekyll-optional-front-matter\n  - jekyll-titles-from-headings\n  - jekyll-github-metadata\n"
        "repository: " + repo + "\nexclude:\n  - README.md\n"
    )
    for source, dest in PAGES.items():
        body = rewrite((ROOT / source).read_text(), source, repo)
        out = SITE / dest
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("---\nlayout: default\n---\n{% raw %}\n" + body + "\n{% endraw %}\n")
    (SITE / "index.md").write_text(
        "---\nlayout: default\n---\n{% raw %}\n" + landing(repo) + "\n{% endraw %}\n"
    )
    (SITE / "dashboard").mkdir(exist_ok=True)
    shutil.copy(ROOT / "site_src" / "dashboard.html", SITE / "dashboard" / "index.html")
    from scripts.export_dashboard_data import export

    (SITE / "dashboard" / "data.json").write_text(
        json.dumps(export(DEFAULT_PATH), separators=(",", ":"))
    )
    for directory in ASSET_DIRS:
        shutil.copytree(ROOT / directory, SITE / directory)
    print(f"built {SITE.relative_to(ROOT)}: {len(PAGES)} pages")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default="jainamh029/cpg-deduction-analytics")
    build(parser.parse_args().repo)
