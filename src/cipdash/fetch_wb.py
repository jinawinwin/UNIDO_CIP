"""World Bank WDI supporting variables (income group, GDP per capita, FDI, openness, R&D ...)."""
from __future__ import annotations
from pathlib import Path

import pandas as pd
import requests

API = "https://api.worldbank.org/v2"
INDICATORS = {
    "gdppc_ppp": "NY.GDP.PCAP.PP.KD",
    "fdi_gdp": "BX.KLT.DINV.WD.GD.ZS",
    "trade_gdp": "NE.TRD.GNFS.ZS",
    "gcf_gdp": "NE.GDI.TOTL.ZS",
    "rd_gdp": "GB.XPD.RSDV.GD.ZS",
    "mva_gdp": "NV.IND.MANF.ZS",
}


def _get(url, params):
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    return r.json()


def fetch_meta() -> pd.DataFrame:
    rows, page = [], 1
    while True:
        j = _get(f"{API}/country", {"format": "json", "per_page": 400, "page": page})
        rows += j[1]
        if page >= j[0]["pages"]:
            break
        page += 1
    df = pd.DataFrame([{"iso3": r["id"], "name": r["name"], "region": r["region"]["value"],
                        "income": r["incomeLevel"]["id"]} for r in rows])
    return df[df["region"] != "Aggregates"].reset_index(drop=True)


def fetch_indicator(code: str, start=1990, end=2030) -> pd.DataFrame:
    rows, page = [], 1
    while True:
        j = _get(f"{API}/country/all/indicator/{code}",
                 {"format": "json", "per_page": 20000, "date": f"{start}:{end}", "page": page})
        if len(j) < 2 or j[1] is None:
            break
        rows += [{"iso3": r["countryiso3code"], "year": int(r["date"]), "value": r["value"]} for r in j[1] if r["value"] is not None]
        if page >= j[0]["pages"]:
            break
        page += 1
    return pd.DataFrame(rows)


def tidy(d: pd.DataFrame, name: str) -> pd.DataFrame:
    """Drop aggregate rows (blank/odd ISO3) and duplicates so the (iso3, year) index is unique."""
    if d.empty:
        return pd.DataFrame(columns=["iso3", "year", name]).set_index(["iso3", "year"])
    d = d.rename(columns={"value": name})
    d = d[d["iso3"].astype(str).str.fullmatch(r"[A-Z]{3}")].drop_duplicates(["iso3", "year"])
    return d.set_index(["iso3", "year"])


def fetch_all(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    fetch_meta().to_csv(out / "meta.csv", index=False)
    frames = []
    for name, code in INDICATORS.items():
        d = tidy(fetch_indicator(code), name)
        frames.append(d)
        print("WB", name, len(d))
    pd.concat(frames, axis=1).reset_index().to_csv(out / "indicators.csv", index=False)


def load(wb_dir: Path):
    m, i = wb_dir / "meta.csv", wb_dir / "indicators.csv"
    if not (m.exists() and i.exists()):
        return None, None
    return pd.read_csv(m), pd.read_csv(i)


if __name__ == "__main__":
    fetch_all(Path("data/raw/wb"))
