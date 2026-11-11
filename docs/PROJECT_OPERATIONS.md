# Project operations and setup

This document is for the repository maintainer, not the website's homepage. The public-facing introduction is in the main [README](../README.md).

## How the pieces work

1. GitHub stores the website's source code (in `site/`) and the updater (in `scripts/build_data.py`).
2. The scheduled [GitHub Actions workflow](../.github/workflows/update-and-deploy.yml) starts a temporary GitHub-hosted computer about every four hours.
3. That computer requests public data from the City of Chicago's Socrata API.
4. The script writes **processed, public JSON snapshots** to `site/data/`. It does **not** commit the full raw API response or a DuckDB file.
5. The workflow commits updated JSON snapshots and deploys the `site/` folder using GitHub Pages.
6. Visitors' browsers load the static HTML, JavaScript, and JSON. GitHub Pages does not run a Python server.

### What the updater downloads

- **First run / full rebuild:** available *daily sensor aggregates* from September 1, 2025 onward, paginated from the public `rtmx-vkjr` dataset.
- **Later runs:** the saved daily snapshot is reused; the script re-fetches a **21-day overlap** to capture recent additions or revisions.
- **Hourly view:** a separate request checks the newest published hour from `di9s-96ws`, then downloads a window covering the previous **72 hours**. This is for the most recent mapped hour and short hourly trends.

The updater writes these files when the requests succeed:

| File | Purpose |
| --- | --- |
| `site/data/daily.json` | Compact daily values, sensor metadata, and derived daily network summaries |
| `site/data/recent.json` | Compact recent hourly values and a single time-matched map snapshot |
| `site/data/manifest.json` | Last successful generation timestamp, measurement dates, counts and data-source error information |

The public `site/data/*.json` files are visible to everyone on GitHub and through GitHub Pages. This is intentional for the public City aggregates. The workflow is **not** a private long-term data warehouse.

## GitHub settings

- Repository: `pouyanhb/chicago-air-explorer`
- **Settings → Pages → Build and deployment → Source:** `GitHub Actions`
- **Actions → Update Chicago air data and deploy:** open a run to see its status and detailed logs
- **Actions → Update Chicago air data and deploy → Run workflow:** start an update manually
- **Settings → Actions → General → Workflow permissions:** permit the workflow's required repository writes

If rate limits become an issue, a Socrata application token can be added as a **GitHub Actions secret** named `SOCRATA_APP_TOKEN`; never place the token in frontend JavaScript.

## Running it locally

To generate data from the public API:

```bash
python -m pip install -r scripts/requirements.txt
python scripts/build_data.py
```

To preview the site (run in a different terminal):

```bash
python -m http.server 8000 --directory site
```

Open http://localhost:8000.

To redo the full historical daily download (including removing historical records deleted by the provider):

```bash
python scripts/build_data.py --rebuild
```

Run the tests:

```bash
python -m unittest discover -s tests -v
node --check site/assets/app.js
python -m compileall -q scripts
```

## What happens to `air.db`?

Nothing. The website does **not** use, open, modify, or upload the `air.db` in Google Drive. Keep it backed up outside the public repository; do not commit it. Your Colab archive and this website's public-source snapshots are independent and may differ due to upstream corrections, retrieval dates, and daily aggregation definitions.

## Methodology and cautions

- Daily source values are published **UTC-day** summaries. The site does not reconstruct Chicago-local daily means from hourly readings. Hourly timestamps are shown in Chicago local time in the interface.
- Per-day network summaries average available sensor measurements equally, but sensor availability varies. This is a *monitored-network* statistic, not a population-weighted exposure estimate.
- The comparison view uses matching dates for all selected sensors; missing values are not silently filled.
- The PM₂.₅/NO₂ correlation view matches the two pollutants within one sensor and day, and is descriptive only.
- The latest-hour map picks a single hour with an adequate cohort of reporting PM₂.₅ sensors. Marker colors are *not* AQI.
- Coordinates use the newest valid reported site coordinate; large reported movements are flagged. Labels are not neighborhood boundaries.
- The source distinguishes raw from corrected fields; the website uses published `_value` fields.
- A 21-day incremental refresh does not detect older provider deletions. Periodically run `--rebuild` if complete historical reconciliation is required.
- No routine completeness threshold from raw hourly observations is reconstructed for the source-published daily aggregates. Do not interpret these as official compliance statistics.

## When a workflow fails

Look at the **Actions** run and expand the first failed step. A timeout or error from the City API can prevent a new snapshot; it doesn't mean the source website is automatically broken. The updater intentionally fails rather than committing partial daily data. An unavailable recent-hour request can retain the prior hourly snapshot with an error recorded in the manifest. Always check the measurement date before calling information current.

## Costs and limitations

GitHub Pages and GitHub Actions have usage, size and policy limits, and their availability can depend on account type and repository visibility. This design is intended for a small public project; increasing data size or traffic may eventually justify external object storage or a database.
