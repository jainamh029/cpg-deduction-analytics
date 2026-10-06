# Synthetic-data analytics project. See README.md.
# PY: any Python 3.11 interpreter, e.g. `make setup PY=$(uv python find 3.11)`
PY ?= python3.11
VENV := .venv
BIN := $(VENV)/bin
STAMP := $(VENV)/.installed
export DBT_PROFILES_DIR := .

.PHONY: all setup data patterns lint test build forecast screenshots docs clean

all: setup lint data build forecast test

setup: $(STAMP)

$(STAMP): pyproject.toml
	$(PY) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e ".[dev]"
	touch $(STAMP)

data: $(STAMP)
	$(BIN)/python -m data_gen.load

patterns: $(STAMP)
	$(BIN)/python -m scripts.pattern_report

lint: $(STAMP)
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

test: forecast
	CPG_USE_BUILT=1 $(BIN)/pytest

build: data
	$(BIN)/dbt build

forecast: build
	$(BIN)/python -m forecast.run

docs: $(STAMP)
	$(BIN)/dbt docs generate

clean:
	rm -rf $(VENV) target logs warehouse/*.duckdb warehouse/*.duckdb.wal .pytest_cache .ruff_cache

screenshots: forecast
	$(BIN)/python -m dashboard.capture_screenshots
