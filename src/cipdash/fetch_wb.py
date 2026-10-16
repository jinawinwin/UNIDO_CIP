"""World Bank WDI supporting variables with duplicate-safe country-year merges."""
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
KEYS = ["iso3", "year"]


def _get(url, params):
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    data = r.json()
    if not isinstance(data, list) or len(data) < 2:
        raise RuntimeError(f"Unexpected World Bank API response for {url}: {str(data)[:200]}")
    return data


def fetch_meta() -> pd.DataFrame:
    rows, page = [], 1
    while True:
        j = _get(f"{API}/country", {"format": "json", "per_page": 400, "page": page})
        rows += j[1] or []
        if page >= int(j[0].get("pages", 1)):
            break
        page += 1
    data = []
    for r in rows:
        region = (r.get("region") or {}).get("value")
        income = (r.get("incomeLevel") or {}).get("id")
        data.append({"iso3": r.get("id"), "name": r.get("name"), "region": region, "income": income})
    df = pd.DataFrame(data, columns=["iso3", "name", "region", "income"])
    df["iso3"] = df["iso3"].astype(str).str.strip().str.upper()
    df = df[df["region"] != "Aggregates"]
    df = df[df["iso3"].str.fullmatch(r"[A-Z]{3}", na=False)]
    return df.drop_duplicates("iso3", keep="last").reset_index(drop=True)


def fetch_indicator(code: str, start=1990, end=2030) -> pd.DataFrame:
    rows, page = [], 1
    while True:
        j = _get(
            f"{API}/country/all/indicator/{code}",
            {"format": "json", "per_page": 20000, "date": f"{start}:{end}", "page": page},
        )
        if j[1] is None:
            break
        for r in j[1]:
            if r.get("value") is None:
                continue
            try:
                year = int(r.get("date"))
            except (TypeError, ValueError):
                continue
            rows.append({"iso3": r.get("countryiso3code"), "year": year, "value": r["value"]})
        if page >= int(j[0].get("pages", 1)):
            break
        page += 1
    return pd.DataFrame(rows, columns=["iso3", "year", "value"])


def tidy(d: pd.DataFrame, name: str) -> pd.DataFrame:
    """Return a unique (ISO3, year) index; normalize key types before de-duplication."""
    if d.empty:
        empty = pd.DataFrame(columns=["iso3", "year", name])
        empty = empty.set_index(KEYS)
        empty.index.names = KEYS
        return empty
    d = d.copy().rename(columns={"value": name})
    d["iso3"] = d["iso3"].astype(str).str.strip().str.upper()
    d["year"] = pd.to_numeric(d["year"], errors="coerce")
    d[name] = pd.to_numeric(d[name], errors="coerce")
    d = d[d["iso3"].str.fullmatch(r"[A-Z]{3}", na=False)].dropna(subset=["year"])
    d["year"] = d["year"].astype(int)
    # Grouping handles mixed-type keys (e.g. 2020 and "2020") that drop_duplicates
    # alone can leave looking different before the index is constructed.
    d = d.groupby(KEYS, as_index=False, sort=False)[name].last()
    return d.set_index(KEYS).sort_index()


def _combine_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Outer-join indicator panels on normalized unique keys, never align non-unique indexes."""
    combined = None
    for frame in frames:
        d = frame.reset_index() if isinstance(frame.index, pd.MultiIndex) else frame.copy()
        if not all(k in d.columns for k in KEYS):
            raise ValueError(f"Indicator frame needs {KEYS}; got columns={list(d.columns)}")
        d["iso3"] = d["iso3"].astype(str).str.strip().str.upper()
        d["year"] = pd.to_numeric(d["year"], errors="coerce")
        d = d.dropna(subset=["year"])
        d["year"] = d["year"].astype(int)
        d = d[d["iso3"].str.fullmatch(r"[A-Z]{3}", na=False)]
        value_cols = [c for c in d.columns if c not in KEYS]
        d = d.groupby(KEYS, as_index=False, sort=False)[value_cols].last()
        if combined is None:
            combined = d
        else:
            combined = combined.merge(d, on=KEYS, how="outer", validate="one_to_one")
    if combined is None:
        return pd.DataFrame(columns=KEYS)
    return combined.sort_values(KEYS).reset_index(drop=True)


def _merge_cached(new: pd.DataFrame, old: pd.DataFrame | None) -> pd.DataFrame:
    """Preserve cached values if a source temporarily omits countries or indicators."""
    if old is None or old.empty:
        return new
    new = new.copy()
    old = old.copy()
    # Make every metric column a common column so pandas applies predictable suffixes.
    for c in INDICATORS:
        if c not in new:
            new[c] = pd.NA
        if c not in old:
            old[c] = pd.NA
    new["iso3"] = new["iso3"].astype(str).str.strip().str.upper()
    new["year"] = pd.to_numeric(new["year"], errors="coerce")
    new = new.dropna(subset=["year"])
    new["year"] = new["year"].astype(int)
    old["iso3"] = old["iso3"].astype(str).str.strip().str.upper()
    old["year"] = pd.to_numeric(old["year"], errors="coerce")
    old = old.dropna(subset=["year"])
    old["year"] = old["year"].astype(int)
    old = old.groupby(KEYS, as_index=False, sort=False).last()
    merged = new.merge(old, on=KEYS, how="outer", suffixes=("_new", "_old"), validate="one_to_one")
    for c in INDICATORS:
        nc, oc = f"{c}_new", f"{c}_old"
        if nc in merged and oc in merged:
            merged[c] = merged[nc].where(merged[nc].notna(), merged[oc])
        elif nc in merged:
            merged[c] = merged[nc]
        elif oc in merged:
            merged[c] = merged[oc]
        else:
            merged[c] = pd.NA
        for col in (nc, oc):
            if col in merged:
                merged.drop(columns=col, inplace=True)
    return merged.sort_values(KEYS).reset_index(drop=True)


def fetch_all(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    meta_path, indicator_path = out / "meta.csv", out / "indicators.csv"
    try:
        meta = fetch_meta()
        if not meta.empty:
            meta.to_csv(meta_path, index=False)
        else:
            raise RuntimeError("World Bank country metadata response was empty")
    except Exception as exc:
        if meta_path.exists():
            print(f"World Bank metadata refresh failed; using cached metadata: {exc}")
        else:
            raise

    prior = None
    if indicator_path.exists():
        try:
            prior = pd.read_csv(indicator_path)
        except Exception as exc:
            print(f"Warning: unable to read cached World Bank indicators: {exc}")

    frames = []
    for name, code in INDICATORS.items():
        try:
            d = tidy(fetch_indicator(code), name)
            print("WB", name, len(d))
        except Exception as exc:
            print(f"World Bank indicator refresh failed ({name}/{code}): {exc}")
            d = pd.DataFrame(columns=["iso3", "year", name]).set_index(KEYS)
        frames.append(d)

    combined = _combine_frames(frames)
    for name in INDICATORS:
        if name not in combined:
            combined[name] = pd.NA
    combined = _merge_cached(combined, prior)
    combined.to_csv(indicator_path, index=False)
    print(f"World Bank indicators saved: {len(combined):,} country-year rows; {combined.iso3.nunique()} countries")


def load(wb_dir: Path):
    m, i = wb_dir / "meta.csv", wb_dir / "indicators.csv"
    if not (m.exists() and i.exists()):
        return None, None
    return pd.read_csv(m), pd.read_csv(i)


if __name__ == "__main__":
    fetch_all(Path("data/raw/wb"))
