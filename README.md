# Chicago Air Explorer

An independent, GitHub Pages-friendly dashboard for the City of Chicago's **Open Air Chicago** PM2.5 and NO₂ sensor data. It uses two publicly available City datasets and does **not** require an API key, a server, your Google Drive, or your DuckDB database. The public API can publish measurements several days after they are collected: the site reports **latest published** measurements, **not live air quality**.

## Features

- Interactive mapped sensor locations with the latest *same-hour* readings where available, latest UTC day, and historical period averages
- PM2.5 and NO₂ toggle, 30-day, 90-day, 1-year, and all-available-date views
- Monitored-network equal-sensor-weight daily mean, and a separate contributing-sensor count chart
- Compare up to **five** sensors on common UTC dates, with shared-day counts and CSV export
- PM2.5 versus NO₂ matched-day scatterplot and descriptive Pearson correlation for the first selected sensor
- Explicit measurement date, update timestamp, publication delay, and methodology/limitations page
- Automated data refresh and GitHub Pages deployment using GitHub Actions

## Get it online (new repository recommended)

1. On GitHub, create a **new public repository** named `chicago-air-explorer`. Do not put this in another project repository.
2. Upload **all contents** of this folder, including hidden directories `.github/` and `site/.nojekyll`, to the new repository's `main` branch. The GitHub web uploader may conceal hidden files in some desktop views, so verify `.github/workflows/update-and-deploy.yml` appears in GitHub.
3. Under **Settings → Pages → Build and deployment → Source**, choose **GitHub Actions**.
4. Under **Actions**, open **Update Chicago air data and deploy** → **Run workflow**. The first run backfills historical source-published daily aggregates; later runs only fetch the last 21 days while retaining cached older aggregates. Data is committed as `site/data/*.json`.
5. After successful completion, open the GitHub Pages URL shown in the workflow's deployment result. For a repository under `pouyanhb`, this is normally `https://pouyanhb.github.io/chicago-air-explorer/`. It is not a verified live URL until Pages deployment succeeds.

**Important:** if the API request times out or the first run fails, the workflow should show a red status. This is a *source availability problem*, not an invitation to upload your private data. Rerun it when the source responds. The website deliberately shows a no-data message until real data have been imported; it never substitutes fabricated measurements.

### Automation

`.github/workflows/update-and-deploy.yml` runs about every four hours (GitHub Actions scheduling is best-effort). It tries the public daily dataset first, then fetches the last 72 hours from the newest available hourly timestamp. A failed hourly request does not discard the last successfully published hourly snapshot; the manifest records the failure. A failed daily request prevents deployment of partial results. GitHub Actions commits updated **public, processed** JSON and deploys it in the same workflow. Pushes made using `GITHUB_TOKEN` won't trigger a second automatic run.

If the source enforces rate limits, optionally add the secret `SOCRATA_APP_TOKEN` in Settings → Secrets and variables → Actions, using a token obtained from the City of Chicago portal; never add secrets to frontend JS or repository files.

### Local preview

```bash
python -m http.server 8000 --directory site
# open http://localhost:8000
```

Before the first data refresh, the website will display a clear message that real data are not yet available. To generate real data locally (requires internet and the official City API):

```bash
pip install -r scripts/requirements.txt
python scripts/build_data.py
```

To fully rebuild the daily cache, including provider deletions: `python scripts/build_data.py --rebuild`.

## What happens to `air.db`?

Nothing. The app never opens, copies, uploads, or modifies your original `air.db`. **Do not commit the file to GitHub**. A `.gitignore` blocks common database filenames and Colab notebooks, but still inspect `git status` before pushing. Only City-published aggregated data in `site/data/` are made public. The original DuckDB remains in your private Google Drive or local backup for deeper scientific analysis. If you eventually want to reproduce *exactly* the contents of your own archive instead of retrieving public City data independently, that would be a separate optional import feature and would require access to a copy of that database.

## Sources and important methodological details

- [City of Chicago: Open Air Chicago Day Aggregations (`rtmx-vkjr`)](https://data.cityofchicago.org/d/rtmx-vkjr)
- [City of Chicago: Open Air Chicago Hour Aggregations (`di9s-96ws`)](https://data.cityofchicago.org/d/di9s-96ws)
- [US EPA: Air Sensor Toolbox](https://www.epa.gov/air-sensor-toolbox)

Daily values are **published UTC-day aggregates** (NOT reconstructed Chicago-local calendar days). Hourly values are UTC timestamps and converted to Chicago local time only for display. The daily per-sensor aggregate is not recalculated by this software from individual hourly records. An hourly day-completeness rule cannot be reconstructed from the published daily values alone. The monitored-network series first takes one published daily reading per sensor, then averages sensors equally on each UTC day; the network's membership can change across dates. The comparison view uses only common valid UTC days; the correlation panel pairs two pollutants within the same sensor on the same UTC day. No missing values are imputed.

The source is non-regulatory sensor data; this tool must **not** be used to infer compliance with annual PM2.5 or NO₂ standards, neighborhood-wide exposure, health advice, or pollution source attribution. Marker colors are relative to the displayed sensor readings, not AQI categories. The City dataset distinguishes `.raw` readings from cloud-calibrated `.value`; this explorer uses `.value`. Its `latest published hour` selection requires a minimum simultaneous PM2.5 cohort before creating a same-hour map. The history period map requires valid daily readings for at least 75% of the available UTC days.

Coordinates come from the most recently provided valid geolocation, **not averaged across deployment locations**. Major changes in location are flagged in the map detail. Sensor names are labels, not neighborhood spatial boundaries.

**Data retention:** the incremental cache updates past sensor-day values within a rolling 21-day overlap; it does not detect source deletions outside the window. Run a full rebuild periodically to reconcile these.

## Testing

```bash
python -m unittest discover -s tests -v
node --check site/assets/app.js
python -m compileall -q scripts
```

## Tech stack

Static HTML/CSS/JavaScript + Chart.js + Leaflet + OpenStreetMap/CARTO map tiles; Python Requests data processing; GitHub Actions; GitHub Pages. All libraries are loaded via their respective public CDNs. This package includes no fabricated sensor readings and no credentials.
