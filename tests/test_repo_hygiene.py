"""Repo hygiene on tracked files: no absolute local paths, no secrets, no large binaries, and the
SYNTHETIC-data label is present in every top-level doc."""

import re
import subprocess

import pytest

from .helpers import REPO_ROOT

MAX_BYTES = 1_000_000
SECRET_PATTERNS = [
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(api[_-]?key|secret|password|token)\s*[:=]\s*['\"][^'\"]{8,}['\"]"),
]
ABSOLUTE_PATH = re.compile(r"/(Users|home)/[A-Za-z0-9_.-]+/")


def tracked_files():
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    if out.returncode != 0:
        pytest.skip("not a git checkout")
    return [REPO_ROOT / line for line in out.stdout.splitlines() if (REPO_ROOT / line).is_file()]


def text_files():
    return [p for p in tracked_files() if p.suffix not in {".png", ".duckdb"}]


def test_no_large_files_are_tracked():
    big = [(p.name, p.stat().st_size) for p in tracked_files() if p.stat().st_size > MAX_BYTES]
    assert big == []


def test_no_database_or_generated_data_is_tracked():
    bad = [
        p.name
        for p in tracked_files()
        if p.suffix in {".duckdb", ".parquet", ".csv"} and "fixtures" not in p.parts
    ]
    assert bad == []


def test_no_absolute_local_paths_in_tracked_text_files():
    offenders = [
        p.relative_to(REPO_ROOT).as_posix()
        for p in text_files()
        if ABSOLUTE_PATH.search(p.read_text(errors="ignore"))
    ]
    assert offenders == []


def test_no_secrets_in_tracked_text_files():
    offenders = []
    for path in text_files():
        text = path.read_text(errors="ignore")
        if any(p.search(text) for p in SECRET_PATTERNS):
            offenders.append(path.relative_to(REPO_ROOT).as_posix())
    assert offenders == []


@pytest.mark.parametrize(
    "doc",
    ["README.md", "PLAN.md", "PLANTED_PATTERNS.md", "docs/METRICS.md", "docs/METABASE_NOTES.md"],
)
def test_docs_label_the_data_as_synthetic(doc):
    text = (REPO_ROOT / doc).read_text().lower()
    assert "synthetic" in text
