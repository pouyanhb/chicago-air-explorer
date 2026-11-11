# Chicago Air Explorer — operations guide

This is maintainer documentation; the public project description is in the [README](../README.md).

## What GitHub does

The repository holds the static website in `site/`, processing tools in `scripts/`, and **processed public JSON** in `site/data/`. GitHub Pages serves those files. A scheduled GitHub Action checks the City of Chicago API and updates public summaries. No Python server or full DuckDB file is hosted.

## Initial historical data: one-time import

The initial daily dataset comes from the existing Open Air Chicago DuckDB archive. The GitHub repository does **not** contain or read that `air.db`.

1. In Google Colab, run the companion `Chicago_Air_Explorer_Export.ipynb` notebook with your private Google Drive mounted.
2. It downloads the read-only [exporter](../scripts/export_from_duckdb.py), opens `/content/drive/MyDrive/open_air_chicago/air.db` **read-only**, and creates `daily.json`, `recent.json`, and `manifest.json`.
3. Upload **only those three small files** into this repository's `site/data/` directory (or share the ZIP in ChatGPT for review and GitHub upload). Never upload `air.db`.
4. Confirm the three files appear in the repository. A push triggers **deployment only**, not another large historical API download.

The exporter calculates an **hourly-derived UTC calendar-day mean** for a sensor/pollutant only if at least 18 of that UTC day's 24 hours have valid non-negative numeric readings. PM₂.₅ and NO₂ have separate coverage; missing values are not interpolated or zero-filled. Duplicate sensor-hour keys cause an error to prevent silently biased means. Timestamps are assumed UTC and NO₂ units ppb based on the existing analysis notebook; verify with provider metadata before presenting results as final research.

## Subsequent automated updates

The [workflow](../.github/workflows/update-and-deploy.yml) runs on code pushes and twice per day on a schedule. Code pushes **only deploy the existing site**. Scheduled/manual runs execute [`refresh_hourly.py`](../scripts/refresh_hourly.py), which:

1. Checks for the initial `site/data/daily.json` seed. If it is missing, exits cleanly without attempting a full download.
2. Rechecks two previously scanned UTC dates while catching up, and fetches **up to seven completed UTC days per run**, one day at a time from the City's [public hourly API](https://data.cityofchicago.org/d/di9s-96ws).
3. Uses exactly the same 18-valid-hour per pollutant UTC-day mean rule as the initial archive export.
4. Preserves older sensor-days and incorporates newly eligible/revised readings; an API failure stops further daily requests without throwing away already fetched complete days.
5. Attempts a short recent-hour map update. A failure in that optional request leaves the last valid recent snapshot and records a warning in the manifest.
6. Commits updated public JSON and deploys the website. The source's own publication delay is not reduced by more frequent polling.

Because only seven days are checked per run, it can take several runs to catch up after a long source delay. Once caught up, the cursor cycles through approximately the most recent 14 UTC days. Older source deletions and corrections outside the revisit window are not automatically reconciled. Do not interpret this website as live or a regulatory air-quality warning service.

## Output files

| File | Contents |
|---|---|
| `site/data/daily.json` | Sensor catalog, valid hourly-derived UTC-day concentrations, equally weighted network summaries |
| `site/data/recent.json` | Most recently accessible 72-hour slice and one time-aligned map snapshot |
| `site/data/manifest.json` | Data-generation date, latest observed timestamps, record counts, warnings |

These JSON files are **public**. Anyone visiting GitHub or the website can inspect or download them.

## Manual controls

- [Actions page](https://github.com/pouyanhb/chicago-air-explorer/actions): see runs and logs.
- [Pages configuration](https://github.com/pouyanhb/chicago-air-explorer/settings/pages): deployment source = **GitHub Actions**.
- The workflow includes a **Run workflow** button for manual refresh after the JSON seed exists.
- An optional `SOCRATA_APP_TOKEN` GitHub Actions secret may help with API rate limits but will not cure provider HTTP 503 outages.

## Development and testing

```bash
python -m pip install -r scripts/requirements.txt
python -m unittest discover -s tests -v
python -m compileall -q scripts
node --check site/assets/app.js
python -m http.server 8000 --directory site
```

Open http://localhost:8000 to preview. The old `scripts/build_data.py` is retained as a separate experimental importer for City-published daily aggregates; **do not run it against the hourly-derived production JSON snapshots**, as the methods differ.

## Interpretation limits

The sensor network is not population-weighted; missingness changes which locations contribute. The descriptive 18-of-24-hour completeness rule is not a substitute for EPA regulatory design-value procedures. Comparisons use matching UTC days; correlation does not identify sources. Site positions use last valid locations and may reflect device relocations. Publication delay and unavailable periods should remain visible.

## Why previous runs failed

The original workflow tried to download the entire daily-history dataset before committing anything. GitHub Actions logs showed repeated **HTTP 503** responses from the City of Chicago daily aggregation API at offsets 102,500 and 30,000, so the job failed before deployment. This new design separates one-time history export from small updates and separates the website deployment from data-fetch success.

Do not recreate the repository to address API failures. GitHub Free is sufficient for this public research site; upgrading the GitHub plan does not repair City API availability.
