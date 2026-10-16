# UNIDO CIP analysis dashboard

This repository fetches UNIDO's Competitive Industrial Performance (CIP) index, combines it with World Bank WDI variables, runs descriptive and panel analyses, and publishes a static dashboard with chart/table views and CSV, Excel, and PDF downloads.

## Automated collection

The monthly GitHub Actions workflow first reads the **official UNIDO CIP metadata API** at `https://stat.unido.org/portal/dataset/getDataset/CIP`, then requests observations with the documented `getDataWithoutActivities` endpoint, one country per request. It reads the dataset ID, country list, variable codes, and available periods dynamically; it does not hard-code the dataset ID. The downloaded country-year panel is cached at `data/raw/unido/cip_api.csv` in the runner and consumed by the analysis pipeline.

The API client records `_metadata.json` and `_fetch_log.json`. If UNIDO returns HTTP 403, non-JSON content, or changes its payload structure, inspect those files in the workflow's `crawl-log` diagnostics branch. The crawler does not attempt to bypass access challenges. As a manual fallback, CSV or Excel exports from the [UNIDO CIP database](https://stat.unido.org/data/table?dataset=cip) can be placed anywhere under `data/raw/manual/`; the loader supports the official long-format table export and common wide exports. The repository includes a compressed country-year panel in `data/raw/manual/unido/cip_panel.csv.gz`, standardized from the user-provided UNIDO export, so the dashboard can build even when the API is unavailable.

## Run locally

```bash
pip install -r requirements.txt
python -m playwright install chromium
PYTHONPATH=src python -m cipdash.pipeline --fetch --crawl-unido --out site
```

For a dashboard build from an already-downloaded UNIDO file, omit `--crawl-unido`; keep the file under `data/raw/manual/`. The loader maps UN M49 country codes to ISO3 and uses the export's common-currency values for the two per-capita level variables. Optional `data/raw/manual/tiva.csv` (`iso3,year,<indicator>`) adds OECD TiVA comparisons.

## Dashboard analysis and interpretation

The dashboard includes descriptive statistics and country comparisons, industrial-upgrading stage typology, middle-income country/CIP comparisons, country and year fixed-effects associations, convergence measures, and optional GVC/TiVA complements. Dimension scores are this project's own percentile averages, not UNIDO's official dimension scores. Policy regressions are associations rather than causal estimates. Synthetic data are used only for a CI smoke test and are never intentionally used for the production dashboard.

## Reproducibility and checks

GitHub Actions runs regression tests for the API response normalizer and builds a synthetic end-to-end dashboard before attempting the real UNIDO/WDI pipeline. Each scheduled run updates the diagnostics branch with source status, pipeline logs, and data-file inventory.

## Data source and methodology

- UNIDO Statistics Portal, [CIP Index Database](https://stat.unido.org/data/table?dataset=cip)
- UNIDO Statistics Portal API guide: `https://stat.unido.org/unido-statistics-portal-api`
- World Bank Indicators API: `https://api.worldbank.org/v2`

