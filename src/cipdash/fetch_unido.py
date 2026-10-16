"""Official UNIDO CIP API client.

Uses the documented metadata endpoint and POST data endpoint. The API requires one
request per country. No browser automation or Cloudflare challenge bypass is attempted.
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE = "https://stat.unido.org/portal/dataset"
METADATA_URL = f"{BASE}/getDataset/CIP"
DATA_URL = f"{BASE}/getDataWithoutActivities"
VALUE_KEYS = ("value", "obsValue", "dataValue", "numericValue", "amount", "val", "v")
YEAR_KEYS = ("year", "period", "periodName", "timePeriod", "referencePeriod", "time")
VAR_KEYS = ("variableCode", "variable_code", "variable", "varCode", "indicatorCode", "indicator", "seriesCode", "series", "key")
CONTAINER_KEYS = ("data", "values", "result", "results", "records", "observations", "items", "rows", "dataset")
PREFERRED_CODES = [
    "cip", "cipRank", "quintile", "MVApc", "MVApc_index", "MXpc", "MXpc_index",
    "MVAsh", "MVAsh_index", "MHVAsh", "MHVAsh_index", "MXsh", "MXsh_index",
    "MHXsh", "MHXsh_index", "ImWMVA", "ImWMVA_index", "ImWMT", "ImWMT_index",
    "INDint_index", "MXQual_index",
]


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "UNIDO-CIP-research-dashboard/1.0 (documented public statistics API)",
    })
    retry = Retry(
        total=4, connect=4, read=3, backoff_factor=1.2,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(("GET", "POST")),
        respect_retry_after_header=True,
    )
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _get_json(session: requests.Session, url: str, *, payload=None):
    if payload is None:
        r = session.get(url, timeout=(15, 60))
    else:
        r = session.post(url, json=payload, timeout=(15, 90))
    if r.status_code == 403:
        raise RuntimeError(
            f"UNIDO API returned HTTP 403 for {url}; the API is protected in this runtime. "
            "The client will not try to bypass the access challenge."
        )
    r.raise_for_status()
    try:
        return r.json()
    except ValueError as exc:
        sample = (r.text or "")[:180].replace("\n", " ")
        raise RuntimeError(f"UNIDO API returned non-JSON content for {url}: {sample}") from exc


def _norm(x) -> str:
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def _number(x):
    if x is None or isinstance(x, (dict, list, tuple, bool)):
        return None
    if isinstance(x, str):
        z = x.strip()
        if not z or z.lower() in {"na", "n/a", "null", "none", "-", ".."}:
            return None
        z = z.replace(",", "")
    else:
        z = x
    try:
        y = float(z)
        return y if pd.notna(y) else None
    except (TypeError, ValueError):
        return None


def _year(x):
    if x is None:
        return None
    m = re.search(r"(?:19|20)\d{2}", str(x))
    return int(m.group(0)) if m else None


def _api_variable_codes(metadata: dict) -> list[str]:
    available = [str(v.get("c")) for v in metadata.get("variables", []) if v.get("c")]
    lookup = {c.lower(): c for c in available}
    selected = [lookup[c.lower()] for c in PREFERRED_CODES if c.lower() in lookup]
    return selected or available


def _extract_records(payload, iso3: str, country: str, valid_codes: list[str], label_to_code: dict) -> list[dict]:
    """Convert common long, wide, and nested JSON responses to country-year-variable rows."""
    valid = {c.lower(): c for c in valid_codes}
    labels = {_norm(k): v for k, v in label_to_code.items()}
    rows = []
    seen = set()

    def resolve_var(value):
        if value is None:
            return None
        s = str(value).strip()
        return valid.get(s.lower()) or labels.get(_norm(s))

    def append(year, variable, value):
        yy, vv, val = _year(year), resolve_var(variable), _number(value)
        if yy is None or vv is None or val is None:
            return
        key = (yy, vv)
        if key in seen:
            return
        seen.add(key)
        rows.append({"iso3": iso3, "country": country, "year": yy, "variable": vv, "value": val})

    def walk(node, inherited_year=None, inherited_var=None):
        if isinstance(node, list):
            for item in node:
                walk(item, inherited_year, inherited_var)
            return
        if not isinstance(node, dict):
            if inherited_year is not None and inherited_var is not None:
                append(inherited_year, inherited_var, node)
            return

        year = inherited_year
        var = inherited_var
        val = None
        for k in YEAR_KEYS:
            if k in node and _year(node[k]) is not None:
                year = _year(node[k])
                break
        for k in VAR_KEYS:
            if k in node:
                candidate = resolve_var(node[k])
                if candidate:
                    var = candidate
                    break
        for k in VALUE_KEYS:
            if k in node and not isinstance(node[k], (dict, list)):
                val = node[k]
                break
        if year is not None and var is not None and val is not None:
            append(year, var, val)

        # Wide observation objects often contain one year and many variables.
        if year is not None:
            for k, v in node.items():
                candidate = resolve_var(k)
                if candidate and not isinstance(v, (dict, list)):
                    append(year, candidate, v)

        for k, v in node.items():
            kl = str(k).strip()
            child_year = _year(kl) if re.fullmatch(r"(?:19|20)\d{2}", kl) else year
            child_var = resolve_var(kl) or var
            if child_year != year or child_var != var:
                walk(v, child_year, child_var)
            elif str(k).lower() in CONTAINER_KEYS or isinstance(v, (dict, list)):
                walk(v, year, var)
            elif year is not None and var is not None and str(k).lower() in VALUE_KEYS:
                append(year, var, v)

    walk(payload)
    return rows


def run(out: Path = Path("data/raw/unido"), *, pause: float = 0.12) -> int:
    """Download CIP observations through the official per-country API; return row count."""
    out.mkdir(parents=True, exist_ok=True)
    session = _session()
    metadata = _get_json(session, METADATA_URL)
    dataset_id = metadata.get("id")
    if dataset_id is None:
        raise RuntimeError(f"UNIDO metadata has no dataset id; keys={list(metadata)[:20]}")

    countries = metadata.get("countries") or []
    periods = [str(p) for p in metadata.get("periods", []) if _year(p) is not None]
    variables = _api_variable_codes(metadata)
    labels = {}
    for v in metadata.get("variables", []):
        code = v.get("c")
        label = (v.get("lang") or {}).get("en")
        if code and label:
            labels[label] = str(code)
    if not countries or not periods or not variables:
        raise RuntimeError(
            f"Incomplete UNIDO CIP metadata: countries={len(countries)}, periods={len(periods)}, variables={len(variables)}"
        )

    stale_unparsed = out / "_unparsed_response.json"
    if stale_unparsed.exists():
        stale_unparsed.unlink()

    (out / "_metadata.json").write_text(
        json.dumps({
            "source": METADATA_URL, "dataset_id": dataset_id,
            "production_year": metadata.get("production_year"),
            "dataset_updated": metadata.get("dat_ins"),
            "country_count": len(countries), "periods": periods,
            "variables": variables, "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    records, failures, countries_ok = [], [], 0
    for idx, c in enumerate(countries, start=1):
        iso3 = str(c.get("iso3") or "").strip().upper()
        country = str(((c.get("lang") or {}).get("en")) or iso3).strip()
        country_code = c.get("c")
        if not iso3 or not country_code:
            continue
        payload = {
            "datasetId": dataset_id,
            "countryCode": str(country_code),
            "fullPrecision": True,
            "variableCodes": variables,
            "periods": periods,
        }
        try:
            response = _get_json(session, DATA_URL, payload=payload)
            country_rows = _extract_records(response, iso3, country, variables, labels)
            if country_rows:
                records.extend(country_rows)
                countries_ok += 1
            else:
                failures.append({"iso3": iso3, "country": country, "error": "No observations parsed from API response"})
                if not (out / "_unparsed_response.json").exists():
                    (out / "_unparsed_response.json").write_text(
                        json.dumps({"iso3": iso3, "response": response}, ensure_ascii=False, indent=2)[:500_000],
                        encoding="utf-8",
                    )
        except Exception as exc:
            failures.append({"iso3": iso3, "country": country, "error": str(exc)[:600]})
            if "HTTP 403" in str(exc):
                break
        if idx % 20 == 0:
            print(f"UNIDO CIP API: checked {idx}/{len(countries)} countries; observations={len(records)}")
        if pause:
            time.sleep(pause)

    log = {
        "source": METADATA_URL, "data_endpoint": DATA_URL,
        "dataset_id": dataset_id, "dataset_name": metadata.get("name"),
        "production_year": metadata.get("production_year"),
        "dataset_updated": metadata.get("dat_ins"),
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "countries_in_metadata": len(countries), "countries_with_data": countries_ok,
        "period_count": len(periods), "year_min": min(map(int, periods)) if periods else None,
        "year_max": max(map(int, periods)) if periods else None,
        "requested_variables": variables, "long_observations": len(records),
        "failures": failures,
    }
    (out / "_fetch_log.json").write_text(json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8")

    if records:
        long = pd.DataFrame(records).drop_duplicates(["iso3", "year", "variable"], keep="last")
        wide = long.pivot_table(
            index=["iso3", "country", "year"], columns="variable", values="value", aggfunc="last"
        ).reset_index()
        wide.columns.name = None
        target = out / "cip_api.csv"
        if target.exists():
            try:
                old = pd.read_csv(target)
                merged = pd.concat([old, wide], ignore_index=True, sort=False)
                # Keep the latest non-missing value per variable if a refresh only
                # returned part of the panel; do not erase cached values with nulls.
                merged = merged.groupby(["iso3", "year"], as_index=False, sort=False).last()
                wide = merged.sort_values(["iso3", "year"]).reset_index(drop=True)
            except Exception as exc:
                print(f"Warning: unable to merge prior CIP cache: {exc}")
        wide.to_csv(target, index=False, encoding="utf-8-sig")
        print(
            f"UNIDO CIP API complete: {len(wide):,} country-year rows, "
            f"{wide.iso3.nunique()} countries, years {wide.year.min()}–{wide.year.max()}; "
            f"dataset updated {metadata.get('dat_ins')}"
        )
    else:
        print(
            f"UNIDO CIP API returned no usable observations (metadata countries={len(countries)}). "
            "Review _fetch_log.json; no cached observations were overwritten."
        )
    return len(records)


if __name__ == "__main__":
    run()
