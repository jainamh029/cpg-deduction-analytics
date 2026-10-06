"""Generate docs/lineage.mmd (Mermaid) from dbt's manifest, so the lineage diagram cannot drift.

Usage: python -m scripts.lineage   (requires `make build` so target/manifest.json exists)
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "target" / "manifest.json"
OUT = ROOT / "docs" / "lineage.mmd"
LAYERS = ("staging", "intermediate", "marts", "metrics")


def build(manifest: dict) -> str:
    lines = ["flowchart LR", "    subgraph raw[raw schema - synthetic]"]
    sources = sorted(v["name"] for v in manifest["sources"].values())
    lines += [f"        raw_{n}[{n}]" for n in sources]
    lines.append("    end")
    models = {k: v for k, v in manifest["nodes"].items() if v["resource_type"] == "model"}
    for layer in LAYERS:
        lines.append(f"    subgraph {layer}[{layer}]")
        lines += [
            f"        {v['name']}[{v['name']}]"
            for v in sorted(models.values(), key=lambda m: m["name"])
            if v["path"].startswith(layer)
        ]
        lines.append("    end")
    for model in sorted(models.values(), key=lambda m: m["name"]):
        for parent in sorted(model["depends_on"]["nodes"]):
            if parent.startswith("source."):
                lines.append(f"    raw_{parent.split('.')[-1]} --> {model['name']}")
            elif parent in models:
                lines.append(f"    {models[parent]['name']} --> {model['name']}")
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT.write_text(build(json.loads(MANIFEST.read_text())))
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
