# Chicago Air Explorer

Explore air quality across Chicago's Open Air Chicago sensor network, from the latest published observations to longer-term PM₂.₅ and nitrogen dioxide (NO₂) patterns.

**Website:** [Chicago Air Explorer](https://pouyanhb.github.io/chicago-air-explorer/)

> **Data freshness:** This is **not a live or official air-quality alert service**. Readings come from the City of Chicago's published data and may appear days after they were measured. The dashboard displays the date of the latest available observation and when its data were last updated.

## Explore the data

- **Map the network.** Explore monitored sites and switch between PM₂.₅ and NO₂.
- **Explore history.** View daily network trends and the number of reporting sensors over time.
- **Compare locations.** Select up to **five sensors** and compare measurements from matching dates.
- **Compare pollutants.** Examine paired PM₂.₅ and NO₂ measurements for a selected site, including a descriptive scatterplot.
- **Download comparisons.** Export matched-date sensor comparisons as CSV.

## Data and methods

The dashboard uses public *Open Air Chicago* datasets from the City of Chicago:

- [Daily sensor aggregations](https://data.cityofchicago.org/d/rtmx-vkjr) — historical daily PM₂.₅ and NO₂ measurements.
- [Hourly sensor aggregations](https://data.cityofchicago.org/d/di9s-96ws) — most recent available hourly readings.

The site uses published, cloud-calibrated measurement fields, not the original raw measurement fields. Daily observations are provider-published **UTC-day averages**, not recalculated Chicago-local daily means. Network summaries average available sensor-day values equally and show reporting counts, since the sensor network can change over time. Location comparisons use common observed dates.

**Interpretation matters:** These are non-regulatory sensor observations. A sensor reading or network average does not establish neighborhood-wide exposure, a health recommendation, an EPA compliance determination, or the cause of pollution.

## About this project

Chicago Air Explorer is an independent, open-source data-exploration project. It is **not affiliated with, endorsed by, or operated by** the City of Chicago or the sensor manufacturer.

The website is hosted with GitHub Pages. A GitHub Actions workflow periodically checks the public Chicago datasets and publishes compact JSON snapshots; no visitor account, personal data, or access to a private DuckDB database is required.

For maintainers and developers, see [Project operations and setup](docs/PROJECT_OPERATIONS.md). The underlying code and methods are available in this repository.
