"""Run the data-quality rules in validate.sql against a schema."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import duckdb

RULES_FILE = Path(__file__).with_name("validate.sql")
RULE_HEADER = re.compile(r"^-- rule: (\w+)\s*$", re.MULTILINE)


def load_rules() -> dict[str, str]:
    text = RULES_FILE.read_text()
    headers = list(RULE_HEADER.finditer(text))
    rules = {}
    for i, match in enumerate(headers):
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        rules[match.group(1)] = text[match.end() : end].strip().rstrip(";")
    return rules


def run_rules(con: duckdb.DuckDBPyConnection, schema: str) -> dict[str, int]:
    """Violation count for every rule (zeros included)."""
    return {
        name: int(con.execute(sql.format(s=schema)).fetchone()[0])
        for name, sql in load_rules().items()
    }


def findings(con: duckdb.DuckDBPyConnection, schema: str) -> dict[str, int]:
    """Only the rules that found something."""
    return {name: n for name, n in run_rules(con, schema).items() if n}


def main() -> None:
    """Gate for the build: exit 1 if the source schema has ANY finding (so dirty data never reaches dbt)."""
    from data_gen.load import DEFAULT_PATH

    parser = argparse.ArgumentParser(description="Validate a source schema before transforming it.")
    parser.add_argument("--schema", default="raw")
    parser.add_argument("--warehouse", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    con = duckdb.connect(str(args.warehouse), read_only=True)
    found = findings(con, args.schema)
    con.close()
    if found:
        print(f"validation FAILED for schema {args.schema}: {found}")
        sys.exit(1)
    print(f"validation passed for schema {args.schema}: {len(load_rules())} rules, 0 findings")


if __name__ == "__main__":
    main()
