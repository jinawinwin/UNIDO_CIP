"""Read whatever UNIDO CIP export we get (csv / xlsx / json, long or wide) into one tidy panel.

Output columns: iso3, country, year, cip, <indicators...>
Unknown layouts fail loudly with the detected column names so the mapping can be fixed.
"""
from __future__ import annotations
import json
import re
import gzip
import base64
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
    if path.name.lower().endswith(".csv.gz"):
        try:
            with gzip.open(path, "rt", encoding="utf-8-sig") as f:
                return [pd.read_csv(f)]
        except Exception as e:
            raise ValueError(f"cannot read {path}: {e}") from e
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


LONG_VARIABLES = {
    "cip": "cip",
    "mvapc": "mvapc",
    "mxpc": "mxpc",
    "mvash": "mvash",
    "mhvash": "mhvash",
    "mxsh": "mxsh",
    "mhxsh": "mhxsh",
    "imwmva": "imwmva",
    "imwmt": "imwmt",
    "indintindex": "indint",
    "mxqualindex": "mxqual",
}


def _unido_long_to_wide(df: pd.DataFrame) -> pd.DataFrame | None:
    """Convert the UNIDO table export (one country-year-variable per row)."""
    by_norm = {norm(c): c for c in df.columns}
    year_col = by_norm.get("year")
    country_col = by_norm.get("country")
    var_col = by_norm.get("variablecode") or by_norm.get("unconsolidatedvariablecode")
    value_col = by_norm.get("value")
    code_col = by_norm.get("countrycode")
    if not all((year_col, country_col, var_col, value_col)):
        return None

    variables = df[var_col].astype(str).map(norm).map(LONG_VARIABLES)
    keep = variables.notna()
    if not keep.any():
        return None
    x = df.loc[keep, [year_col, country_col, value_col] + ([code_col] if code_col else [])].copy()
    x["_indicator"] = variables.loc[keep]
    x["year"] = pd.to_numeric(x[year_col], errors="coerce")
    x["_value"] = pd.to_numeric(x[value_col], errors="coerce")

    # The export includes a common-currency column for the two per-capita level
    # variables. Use it so comparisons and their ratio share a currency basis.
    usd_col = by_norm.get("valueusd")
    if usd_col:
        level = x["_indicator"].isin(["mvapc", "mxpc"])
        usd = pd.to_numeric(df.loc[keep, usd_col], errors="coerce")
        x.loc[level, "_value"] = usd.loc[level].where(usd.loc[level].notna(), x.loc[level, "_value"])

    x = x.dropna(subset=["year", "_value"])
    x["year"] = x["year"].astype(int)
    x["country"] = x[country_col].astype(str).str.strip()

    if code_col:
        code = df.loc[x.index, code_col].astype(str).str.strip().str.replace(r"\.0$", "", regex=True).str.zfill(3)
        m49_path = Path(__file__).with_name("m49_to_iso3.json")
        m49_to_iso3 = json.loads(m49_path.read_text(encoding="utf-8"))
        x["iso3"] = code.map(m49_to_iso3)

    index = [c for c in ("iso3", "country", "year") if c in x]
    wide = x.pivot_table(index=index, columns="_indicator", values="_value", aggfunc="first").reset_index()
    wide.columns.name = None
    return wide


def normalise(df: pd.DataFrame, source: str = "") -> pd.DataFrame | None:
    wide = _unido_long_to_wide(df)
    if wide is None:
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


def _restore_chunked_panel(raw_dir: Path) -> Path | None:
    """Reassemble the compressed manual snapshot from text-safe repository parts."""
    parts = sorted(raw_dir.rglob("cip_panel.csv.gz.b64/part-*"))
    if not parts:
        return None
    encoded = "".join(p.read_text(encoding="ascii").strip() for p in parts)
    target = parts[0].parent.parent / "cip_panel.csv.gz"
    try:
        target.write_bytes(base64.b64decode(encoded, validate=True))
    except Exception as e:
        raise SystemExit(f"Invalid chunked CIP panel in {parts[0].parent}: {e}") from e
    return target


def load_panel(raw_dir: Path, country_names: pd.DataFrame | None = None) -> tuple[pd.DataFrame, list[str]]:
    # Large GitHub blobs are supplied as small base64 text parts by the repository
    # uploader; reassemble the source snapshot before scanning the raw directory.
    _restore_chunked_panel(raw_dir)
    files = [p for p in sorted(raw_dir.rglob("*")) if (p.suffix.lower() in (".csv", ".xlsx", ".xls", ".json") or p.name.lower().endswith(".csv.gz"))
             and "_discovery" not in p.name and "wb" not in p.parts]
    files.sort(key=lambda p: (0 if p.relative_to(raw_dir).parts[0] == "unido" else 1, str(p)))
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

