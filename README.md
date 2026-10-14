# UNIDO CIP analysis dashboard

Crawls the UNIDO Competitive Industrial Performance (CIP) database and World Bank WDI, runs five analyses
(descriptive statistics, industrial-upgrading stage, middle-income trap, development-policy association, GVC complement)
and publishes a static dashboard (GitHub Pages) with CSV / Excel / PDF downloads.

## Run
- GitHub: Settings → Pages → Source = **GitHub Actions**, then Actions → *build-and-deploy-dashboard* → Run workflow.
- Local: `pip install -r requirements.txt && playwright install chromium && PYTHONPATH=src python -m cipdash.pipeline --fetch`

## Data
`src/cipdash/fetch_unido.py` drives a headless browser against stat.unido.org, which has no documented download API.
If it finds nothing, the workflow still uploads `crawl-log/_discovery.json` (every URL the page loaded) so the selector can be fixed.
**Fallback:** download the CIP file from stat.unido.org yourself and commit it to `data/raw/manual/` (csv/xlsx/json, long or wide);
column names are auto-matched (see `schema.py`). Optional: `data/raw/manual/tiva.csv` (`iso3,year,<indicator>`) adds OECD TiVA comparisons.

## Notes
- Dimension scores are this project's own percentile averages, not UNIDO's official dimension scores.
- INDint and MXQual in the UNIDO Reader's Guide appear to be composites of the base indicators; the code uses the eight base
  indicators and ignores the composites when the base ones exist (verify against Appendix A of the CIP report).
- Policy regressions are fixed-effects associations, not causal estimates.
- `tests/make_fixture.py` generates SYNTHETIC data to test the pipeline; its output carries a red banner and is never deployed.
