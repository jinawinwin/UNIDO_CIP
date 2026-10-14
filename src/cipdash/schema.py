"""Read whatever UNIDO CIP export we get (csv / xlsx / json, long or wide) into one tidy panel.

Output columns: iso3, country, year, cip, <indicators...>
Unknown layouts fail loudly with the detected column names so the mapping can be fixed.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

import pandas as pd

INDICATORS = ["mvapc", "mxpc", "mvash", "mhvash", "mxsh", "mhxsh", "imwmva", "imwmt", "indint", "mxqual"]

ALIASES = {
    "country": ["country", "economy", "countryname", "economyname", "name", "countryeconomy", "countryorarea"],
    "iso3": ["iso3", "iso", "isocode", "countrycode", "economycode", "code", "isoalpha3", "iso3code", "wbcode", "ccode"],
    "year": ["year", "time", "period", "refyear", "reference year"],
    "cip": ["cip", "cipindex", "cipscore", "cipvalue", "cipindexvalue", "competitiveindustrialperformance",
            "competitiveindustrialperformanceindex", "cipindexscore"],
    "mvapc": ["mvapc", "mvapercapita", "mvapcusd", "manufacturingvalueaddedpercapita"],
    "mxpc": ["mxpc", "mxpercapita", "mxpcusd", "manufacturingexportspercapita"],
    "mvash": ["mvash", "mvashare", "mvasharegdp", "mvashareingdp", "mvagdp"],
    "mhvash": ["mhvash", "mhtvash", "mhvashare", "mhtshareinmva", "mhtmvashare"],
    "mxsh": ["mxsh", "mxshare", "mxshareintotalexports", "mxtotalexports"],
    "mhxsh": ["mhxsh", "mhtxsh", "mhxshare", "mhtshareinmx", "mhtmxshare"],
    "imwmva": ["imwmva", "impactworldmva", "shareinworldmva", "worldmvashare"],
    "imwmt": ["imwmt", "impactworldmt", "shareinworldmanufacturingtrade", "worldmxshare", "imwmx"],
    "indint": ["indint", "industrializationintensity"],
    "mxqual": ["mxqual", "exportquality"],
}


def norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _match_columns(cols) -> dict:
    out, used = {}, set()
    for key, aliases in ALIASES.items():
        for c in cols:
            n = norm(c)
            if c in used or "rank" in n:
                continue
            if n in aliases:
                out[key] = c
                used.add(c)
                break
    return out


def read_any(path: Path) -> list[pd.DataFrame]:
    suf = path.suffix.lower()
    if suf == ".csv":
        for enc in ("utf-8-sig", "cp949", "latin-1"):
            try:
                return [pd.read_csv(path, encoding=enc, sep=None, engine="python")]
            except Exception:
                continue
        raise ValueError(f"cannot read {path}")
    if suf in (".xlsx", ".xls"):
        return [d for d in pd.read_excel(path, sheet_name=None).values() if len(d) > 5]
    if suf == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            for v in raw.values():
                if isinstance(v, list) and v and isinstance(v[0], dict):
                    raw = v
                    break
        if isinstance(raw, list) and raw and isinstance(raw[0], dict):
            return [pd.json_normalize(raw)]
    return []


def _wide_to_long(df: pd.DataFrame) -> pd.DataFrame | None:
    year_cols = [c for c in df.columns if re.fullmatch(r"(19|20)\d\d", str(c).strip())]
    if len(year_cols) < 5:
        return None
    id_cols = [c for c in df.columns if c not in year_cols]
    long = df.melt(id_vars=id_cols, value_vars=year_cols, var_name="year", value_name="value")
    long["year"] = long["year"].astype(int)
    ind_col = next((c for c in id_cols if norm(c) in ("indicator", "variable", "series", "subindex", "indicatorname")), None)
    if ind_col is None:
        return None
    long["_ind"] = long[ind_col].map(lambda v: next((k for k, a in ALIASES.items() if k in INDICATORS + ["cip"] and norm(v) in a), None))
    long = long.dropna(subset=["_ind"])
    keep = [c for c in id_cols if c != ind_col]
    wide = long.pivot_table(index=keep + ["year"], columns="_ind", values="value", aggfunc="first").reset_index()
    return wide


def normalise(df: pd.DataFrame, source: str = "") -> pd.DataFrame | None:
    wide = _wide_to_long(df)
    if wide is not None:
        df = wide
    m = _match_columns(list(df.columns))
    if "year" not in m or "cip" not in m and not any(k in m for k in INDICATORS):
        return None
    if "iso3" not in m and "country" not in m:
        return None
    out = pd.DataFrame({k: df[v] for k, v in m.items()})
    out["year"] = pd.to_numeric(out["year"], errors="coerce")
    out = out.dropna(subset=["year"])
    out["year"] = out["year"].astype(int)
    for k in ["cip"] + INDICATORS:
        if k in out:
            out[k] = pd.to_numeric(out[k], errors="coerce")
    return out


def load_panel(raw_dir: Path, country_names: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[str]]:
    files = [p for p in sorted(raw_dir.rglob("*")) if p.suffix.lower() in (".csv", ".xlsx", ".xls", ".json")
             and "_discovery" not in p.name and "wb" not in p.parts]
    frames, log = [], []
    for f in files:
        try:
            for d in read_any(f):
                n = normalise(d, f.name)
                if n is None:
                    log.append(f"skip {f.name}: columns not recognised -> {list(d.columns)[:15]}")
                else:
                    frames.append(n)
                    log.append(f"read {f.name}: {len(n)} rows, columns {[c for c in n.columns if c not in ('iso3','country','year')]}")
        except Exception as e:  # keep going, report
            log.append(f"error {f.name}: {e}")
    if not frames:
        raise SystemExit("No usable CIP file in %s.\n%s" % (raw_dir, "\n".join(log) or "(directory empty)"))
    keycol = "iso3" if all("iso3" in f for f in frames) else "country"
    panel = frames[0]
    for f in frames[1:]:
        panel = panel.set_index([keycol, "year"]).combine_first(f.set_index([keycol, "year"])).reset_index()
    if "iso3" not in panel and country_names is not None:
        lut = {norm(n): i for n, i in zip(country_names["name"], country_names["iso3"])}
        lut.update({"korearepublicof": "KOR", "republicofkorea": "KOR", "russianfederation": "RUS", "vietnam": "VNM",
                    "turkiye": "TUR", "turkey": "TUR", "iranislamicrepublicof": "IRN", "unitedstatesofamerica": "USA"})
        panel["iso3"] = panel["country"].map(lambda v: lut.get(norm(v)))
    if "iso3" not in panel:
        raise SystemExit("No ISO3 column and no country-name lookup available.")
    panel["iso3"] = panel["iso3"].astype(str).str.strip().str.upper()
    panel = panel[panel["iso3"].str.fullmatch(r"[A-Z]{3}")]
    if "country" not in panel:
        panel["country"] = panel["iso3"]
    bad = panel["country"].astype(str).str.contains(r"world|income|total|region|developing|developed|average|oecd", case=False, regex=True)
    panel = panel[~bad]
    return panel.sort_values(["iso3", "year"]).reset_index(drop=True), log
