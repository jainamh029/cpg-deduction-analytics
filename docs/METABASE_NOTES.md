# Metabase notes - NOT VERIFIED

> Status: **not verified.** Docker and Java are not installed on the development machine, so Metabase was never
> run for this project. The dashboard that actually exists and is tested is the Streamlit app in `dashboard/`.
> Everything below is a desk check of a path I could not execute. All data is synthetic.

## Intended path
- Run Metabase (Docker image) with the MotherDuck-maintained DuckDB driver JAR mounted into `plugins/`
  (the driver README also lists a pre-built image, `ghcr.io/motherduckdb/metabase-duckdb`).
- Point it at `warehouse/warehouse.duckdb` read-only and build questions on `marts.*` and `metrics.*` only.

## Risks I could not test
1. **DuckDB storage-format compatibility.** The driver bundles its own DuckDB JDBC version. A file written by
   the Python `duckdb` used here (1.5.6) may not open in an older bundled version. Mitigation options: pin Python
   `duckdb` to the driver's bundled version, or export the marts to Parquet and query those.
2. **Parquet export mitigation (sketch, untested here):**
   `copy (select * from marts.fct_deductions) to 'export/fct_deductions.parquet' (format parquet)` for each mart and
   metrics view, then attach the Parquet files from Metabase.
3. **Catalog name.** dbt views embed the database name (the file stem, `warehouse`); a renamed file breaks them
   (see DECISIONS.md D33). Keep the file name or attach with the alias `warehouse`.
4. **Macros.** The `metrics.*` macros live in the DuckDB catalog; custom SQL questions can call them, but
   Metabase's visual query builder cannot, so ratio metrics need native-SQL questions or Parquet views that
   precompute them.
5. **Version pairing.** The driver supports specific Metabase versions (listed in its `metabase_versions.json`).

No dashboard export, screenshot, or card definition for Metabase exists in this repository.
