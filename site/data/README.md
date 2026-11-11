# Public website data

This directory contains **public, processed data summaries**, not the original DuckDB archive.

The initial three JSON files (`daily.json`, `recent.json`, and `manifest.json`) are produced by the read-only Colab exporter `scripts/export_from_duckdb.py` using the Open Air Chicago hourly archive. It calculates UTC-day means from sensor hours, requiring at least 18 valid hours per pollutant.

After the initial import, `scripts/refresh_hourly.py` uses the same aggregation method to check small date windows from the City of Chicago's public hourly API. GitHub Actions commits updated JSON files and deploys them via GitHub Pages.

**Do not upload `air.db` or other raw/private files here.** These three JSON files are intentionally public and may be viewed or downloaded by any visitor.

See [the operations guide](../../docs/PROJECT_OPERATIONS.md).
