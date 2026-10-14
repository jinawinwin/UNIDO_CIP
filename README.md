# UNIDO CIP analysis dashboard

Crawls the UNIDO Competitive Industrial Performance (CIP) database and World Bank WDI, runs five analyses
(descriptive statistics, industrial-upgrading stage, middle-income trap, development-policy association, GVC complement)
and publishes a static dashboard (GitHub Pages) with CSV / Excel / PDF downloads.

## Run
- GitHub: Settings → Pages → Source = **GitHub Actions**, then Actions → *build-and-deploy-dashboard* → Run workflow.
- Local: `pip install -r requirements.txt && playwright install chromium && PYTHONPATH=src python -m cipdash.pipeline --fetch`

## Data
**stat.unido.org is protected by a Cloudflare bot challenge (verified in the Actions run, Oct 2026), so automated download is not possible**
and this project does not try to bypass it. Download the CIP file (csv/xlsx) from the portal yourself and commit it to `data/raw/manual/`;
the workflow rebuilds on every push. Column names are auto-matched (see `schema.py`); long and wide layouts both work.
World Bank WDI variables are fetched automatically. Optional: `data/raw/manual/tiva.csv` (`iso3,year,<indicator>`) adds OECD TiVA comparisons.
`--crawl-unido` keeps the experimental portal crawler available; its diagnostics go to the `crawl-log` branch.

## Notes
- Dimension scores are this project's own percentile averages, not UNIDO's official dimension scores.
- INDint and MXQual in the UNIDO Reader's Guide appear to be composites of the base indicators; the code uses the eight base
  indicators and ignores the composites when the base ones exist (verify against Appendix A of the CIP report).
- Policy regressions are fixed-effects associations, not causal estimates.
- `tests/make_fixture.py` generates SYNTHETIC data to test the pipeline; its output carries a red banner and is never deployed.
