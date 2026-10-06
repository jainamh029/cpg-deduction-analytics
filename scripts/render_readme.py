"""Render README.md from docs/README.template.md and docs/findings.json (SYNTHETIC data).

No number in the README is typed by hand: every `{{ path|filter }}` token is resolved from findings.json.
Usage: python -m scripts.render_readme
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from dashboard.ui import money

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "docs" / "README.template.md"
FINDINGS = ROOT / "docs" / "findings.json"
README = ROOT / "README.md"
TOKEN = re.compile(r"\{\{\s*([^}]+?)\s*\}\}")

FILTERS = {
    "money": money,
    "pct0": lambda v: f"{v:.0%}",
    "pct1": lambda v: f"{v:.1%}",
    "pct2": lambda v: f"{v:.2%}",
    "int": lambda v: f"{int(v):,}",
    "x1": lambda v: f"{v:.1f}x",
    "num1": lambda v: f"{v:.1f}",
    "num2": lambda v: f"{v:.2f}",
    "x2": lambda v: f"{v:.2f}x",
    "pts1": lambda v: f"{v:.1f}",
    "join": lambda v: ", ".join(str(x) for x in v),
    "keys": lambda v: ", ".join(f"`{k}` x{n}" for k, n in v.items()),
    "nonefound": lambda v: "no findings" if not v else str(v),
    "str": str,
}


def lookup(findings: dict, path: str):
    value = findings
    for part in path.split("."):
        value = value[part]
    return value


def render(template: str, findings: dict, root: Path = ROOT) -> str:
    def replace(match: re.Match) -> str:
        expr = match.group(1)
        if expr.startswith("include:"):
            return (root / expr.removeprefix("include:")).read_text().rstrip("\n")
        path, _, name = expr.partition("|")
        return FILTERS[name or "str"](lookup(findings, path))

    return TOKEN.sub(replace, template)


def main() -> None:
    findings = json.loads(FINDINGS.read_text())
    README.write_text(render(TEMPLATE.read_text(), findings))
    print(f"wrote {README.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
