#!/usr/bin/env bash
# Audit: `make all` twice from fresh clones in a directory whose path contains a space; diff the outputs.
# Usage: scripts/audit_fresh_clone.sh /path/to/python3.11
set -uo pipefail
PY="$1"
SRC="$(cd "$(dirname "$0")/.." && pwd)"
base="$(mktemp -d)/path with space"
mkdir -p "$base"
echo "clone root: $base"
for run in 1 2; do
  git clone -q "$SRC" "$base/clone$run"
  (cd "$base/clone$run" && make all PY="$PY" >"$base/make$run.log" 2>&1; echo "run $run: make all exit code $?")
  (cd "$base/clone$run" && .venv/bin/python -m scripts.fingerprint >"$base/fp$run.json")
  (cd "$base/clone$run" && shasum -a 256 README.md docs/findings.json docs/lineage.mmd docs/img/*.png \
      forecast/RESULTS.md forecast/results/*.csv >"$base/out$run.txt"; git status --porcelain >"$base/dirty$run.txt")
  grep -E "passed|failed|Done\. PASS|0 failure" "$base/make$run.log" | sed 's/\x1b\[[0-9;]*m//g'
done
echo "--- diff of table fingerprints (empty = identical):"; diff "$base/fp1.json" "$base/fp2.json" && echo "identical ($(grep -c '\[' "$base/fp1.json") tables)"
echo "--- diff of output file hashes (empty = identical):"; diff "$base/out1.txt" "$base/out2.txt" && echo "identical ($(wc -l <"$base/out1.txt") files)"
echo "--- tracked files modified by make all (run 1 / run 2):"; wc -l <"$base/dirty1.txt"; wc -l <"$base/dirty2.txt"
echo "--- any 'bad interpreter' / 'No such file' errors:"; grep -c -E "bad interpreter|No such file" "$base/make1.log" "$base/make2.log"
