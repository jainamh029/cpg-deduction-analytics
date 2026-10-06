#!/usr/bin/env bash
# Phase gate: ruff, format check, pytest, and (unless --no-dbt) dbt build. On success the trimmed
# real output is appended to docs/BUILD_LOG.md. On failure nothing is logged and the exit code is 1.
# Usage: scripts/gate.sh "Phase N: name" [--no-dbt]
set -uo pipefail
cd "$(dirname "$0")/.."
phase="$1"
use_dbt=1
[ "${2:-}" = "--no-dbt" ] && use_dbt=0
export DBT_PROFILES_DIR=.
log="$(mktemp)"
failed=0

run() { # run <tail-lines> <command...>
  local keep="$1"; shift
  local out; out="$(mktemp)"
  echo "\$ $*" >>"$log"
  if "$@" >"$out" 2>&1; then
    tail -n "$keep" "$out" >>"$log"
  else
    echo "GATE FAILED: $*"; tail -n 60 "$out"; failed=1
  fi
  echo >>"$log"
}

run 5 .venv/bin/ruff check .
run 5 .venv/bin/ruff format --check .
if [ "$use_dbt" = 1 ]; then
  run 2 .venv/bin/python -m data_gen.load
  run 14 .venv/bin/dbt build
  export CPG_USE_BUILT=1
fi
run 12 .venv/bin/pytest

if [ "$failed" = 1 ]; then exit 1; fi
{
  echo "## $phase"
  echo
  echo "Run on $(date '+%Y-%m-%d %H:%M %Z'). Output trimmed to the last lines of each command."
  echo
  echo '```'
  sed 's/\x1b\[[0-9;]*m//g' "$log"
  echo '```'
  echo
} >>docs/BUILD_LOG.md
echo "GATE PASSED: $phase (appended to docs/BUILD_LOG.md)"
