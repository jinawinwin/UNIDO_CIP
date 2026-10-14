"""SYNTHETIC test data only (never deployed): checks that the pipeline runs end to end."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

rng = np.random.default_rng(1)
codes = ("KOR JPN DEU CHN USA VNM MYS THA BRA MEX IDN IND TUR ZAF ARG EGY PHL PAK BGD KEN ETH NGA GHA TZA UGA SGP IRL NLD FRA GBR ITA ESP "
         "POL CZE HUN SWE CHE AUT BEL DNK FIN NOR PRT GRC ROU BGR RUS UKR KAZ SAU ARE IRN COL PER CHL ECU MAR TUN LKA NPL KHM MMR LAO "
         "MNG UZB AUS CAN NZL ISR SVK SVN HRV LTU LVA EST SRB").split()
income = {c: ("HIC" if c in "KOR JPN DEU USA SGP IRL NLD FRA GBR ITA ESP POL CZE HUN SWE CHE AUT BEL DNK FIN NOR PRT GRC SAU ARE CHL AUS CAN NZL ISR SVK SVN HRV LTU LVA EST".split()
          else "UMC" if c in "CHN MYS THA BRA MEX TUR ZAF ARG ROU BGR RUS KAZ COL PER ECU SRB IRN".split()
          else "LMC" if c in "VNM IDN IND EGY PHL PAK BGD KEN GHA UKR MAR TUN LKA NPL KHM MMR LAO MNG UZB NGA".split() else "LIC") for c in codes}
years = range(2005, 2023)
lat = {c: {"HIC": 1.0, "UMC": 0.2, "LMC": -0.5, "LIC": -1.2}[income[c]] + rng.normal(0, .5) for c in codes}
rows, wbrows = [], []
for c in codes:
    for i, y in enumerate(years):
        g = lat[c] + 0.03 * i * (1.5 if income[c] in ("UMC", "LMC") else .6) + rng.normal(0, .05)
        e = np.exp
        r = dict(iso3=c, country=c, year=y, MVApc=e(6 + 1.2 * g), MXpc=e(6.2 + 1.5 * g), MVAsh=18 + 3 * g + rng.normal(0, 1), MHVAsh=35 + 12 * g + rng.normal(0, 3),
                 MXsh=60 + 12 * g + rng.normal(0, 3), MHXsh=30 + 14 * g + rng.normal(0, 3), ImWMVA=e(-6 + 1.4 * g), ImWMT=e(-6.2 + 1.5 * g))
        r["CIP"] = 0.15 + 0.12 * g + rng.normal(0, .01)
        rows.append(r)
        wbrows.append(dict(iso3=c, year=y, gdppc_ppp=e(8.5 + .7 * g + .01 * i), fdi_gdp=2 + rng.normal(0, 1.5) + .3 * g, trade_gdp=70 + 15 * g + rng.normal(0, 8),
                           gcf_gdp=24 + rng.normal(0, 4), rd_gdp=max(.1, 1.2 + .6 * g + rng.normal(0, .2)), mva_gdp=18 + 3 * g + rng.normal(0, 1)))
base = Path(sys.argv[1] if len(sys.argv) > 1 else ".fixture")
(base / "raw").mkdir(parents=True, exist_ok=True)
(base / "wb").mkdir(parents=True, exist_ok=True)
pd.DataFrame(rows).to_csv(base / "raw" / "cip_synthetic.csv", index=False)
pd.DataFrame([dict(iso3=c, name=c, region="X", income=income[c]) for c in codes]).to_csv(base / "wb" / "meta.csv", index=False)
pd.DataFrame(wbrows).to_csv(base / "wb" / "indicators.csv", index=False)
print("fixture written to", base)
