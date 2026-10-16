# UNIDO_CIP update package

This is an overlay patch for `jinawinwin/UNIDO_CIP`; it contains replacement/new files only.

## Included changes

- Replace the experimental page-click crawler with UNIDO's documented `getDataset/CIP` + `getDataWithoutActivities` API flow.
- Request metadata-defined country codes, periods and CIP indicator codes; normalize common long/wide JSON shapes; save a country-year CSV and fetch diagnostics.
- Run the CIP API collection in the monthly GitHub Actions job before analysis and deployment.
- Add API-normalizer regression tests and an end-to-end synthetic pipeline smoke test.
- Update the README and no-data page so it does not imply API-based collection is categorically impossible.

## Apply

Unzip this package into the repository root, allowing the included files to overwrite the same paths. Commit and push the changes to `main`, or create a pull request from a working branch.

The actual observations must be retrieved by the GitHub Actions runner from UNIDO's official API. If UNIDO rejects the request with HTTP 403 or changes its JSON schema, inspect `_fetch_log.json` and `_unparsed_response.json` in the `crawl-log` diagnostics branch; the code deliberately does not attempt to bypass access controls.
