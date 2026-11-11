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

The dashboard is based on the City's public [Open Air Chicago hourly aggregations](https://data.cityofchicago.org/d/di9s-96ws). An initial historical archive is summarized into sensor-day values; subsequent updates use the same public hourly data source.

The site uses cloud-calibrated `_value` readings, not raw measurement fields. Daily observations are **UTC-day means calculated from hourly records**, requiring at least **18 valid hours out of 24** for each sensor and pollutant. These are not Chicago-local daily means. Network summaries average eligible sensor-day values equally and show reporting counts. Location comparisons use common observed dates.

**Interpretation matters:** These are non-regulatory sensor observations. A sensor reading or network average does not establish neighborhood-wide exposure, a health recommendation, an EPA compliance determination, or the cause of pollution.

## About this project

Chicago Air Explorer is an independent, open-source data-exploration project. It is **not affiliated with, endorsed by, or operated by** the City of Chicago or the sensor manufacturer.

The website is hosted with GitHub Pages. A GitHub Actions workflow periodically checks a small window of the public Chicago hourly data and publishes compact JSON snapshots; no visitor account, personal data, or access to a private DuckDB database is required.

For maintainers and developers, see [Project operations and setup](docs/PROJECT_OPERATIONS.md). The underlying code and methods are available in this repository.
