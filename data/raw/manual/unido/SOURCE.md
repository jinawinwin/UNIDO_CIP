# UNIDO CIP manual data snapshot

- Source: user-provided export from the [UNIDO CIP database](https://stat.unido.org/data/table?dataset=cip).
- Observation years: 1990–2024.
- The compressed panel pivots the export's country-year-variable rows into one row per country-year and maps the UN M49 numeric country codes to ISO3.
- It retains CIP and the ten production, trade, technology, and world-impact indicators used by this dashboard. CIP rank, quintile, and duplicate index-form indicators are omitted from this analysis panel.
- For MVA per capita and manufactured exports per capita, the panel uses the export's `ValueUSD` field so both level variables share a common currency basis. Other indicators use `Value`.
- The original export's values are not estimated or filled. Missing observations remain missing.

The loader also supports the original UNIDO long-format CSV directly. The compressed panel is a ready-to-build snapshot for this repository.
