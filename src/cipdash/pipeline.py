"""python -m cipdash.pipeline [--fetch] [--raw data/raw] [--wb data/raw/wb] [--out site]"""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path

import pandas as pd

from . import analysis, dashboard, fetch_wb, schema

EXPORT_COLS = ["iso3", "country", "year", "cip", "cip_rank", "cip_pct", "dim_capacity", "dim_deepening", "dim_impact", "stage",
               "income", "region", "gdppc_ppp", "fdi_gdp", "trade_gdp", "gcf_gdp", "rd_gdp", "mva_gdp"] + schema.INDICATORS


def make_pdf(html_path: Path, pdf_path: Path) -> bool:
    from playwright.sync_api import sync_playwright
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page(viewport={"width": 1000, "height": 1400})
            pg.goto(html_path.resolve().as_uri(), wait_until="load")
            pg.wait_for_timeout(1500)
            pg.emulate_media(media="print")
            pg.pdf(path=str(pdf_path), format="A4", print_background=True, margin=dict(top="12mm", bottom="12mm", left="10mm", right="10mm"))
            b.close()
        return True
    except Exception as e:
        print("PDF failed:", e)
        return False


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="crawl UNIDO and download World Bank data first")
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--wb", default="data/raw/wb")
    ap.add_argument("--out", default="site")
    ap.add_argument("--kor", default="KOR")
    ap.add_argument("--fixture", action="store_true")
    a = ap.parse_args(argv)
    raw, wbdir, out = Path(a.raw), Path(a.wb), Path(a.out)
    if a.fetch:
        from . import fetch_unido
        try:
            fetch_wb.fetch_all(wbdir)
        except Exception as e:
            print("World Bank fetch failed:", e)
        try:
            fetch_unido.run(raw / "unido")
        except Exception as e:
            print("UNIDO crawl failed:", e)
    meta, wbind = fetch_wb.load(wbdir)
    try:
        panel, log = schema.load_panel(raw, meta[["iso3", "name"]] if meta is not None else None)
    except SystemExit as e:
        print("::error title=No CIP data::" + str(e).replace("\n", " | ")[:900])
        raise
    print("\n".join(log))
    if meta is not None:  # keep only real economies when classification is available
        panel = panel[panel.iso3.isin(meta.iso3)]
    df = analysis.prepare(panel, meta, wbind, a.kor)
    tiva = None
    tp = raw / "manual" / "tiva.csv"
    if tp.exists():
        tiva = pd.read_csv(tp)
    res = analysis.run_all(df, a.kor, tiva)
    out.mkdir(parents=True, exist_ok=True)
    dl = out / "downloads"
    dl.mkdir(exist_ok=True)
    cols = [c for c in EXPORT_COLS if c in df]
    df[cols].to_csv(dl / "cip_panel.csv", index=False, encoding="utf-8-sig")
    with pd.ExcelWriter(dl / "cip_analysis.xlsx") as xw:
        df[cols].to_excel(xw, sheet_name="panel", index=False)
        for mod, r in res.items():
            for name, t in r["tables"].items():
                t.to_excel(xw, sheet_name=f"{mod[:4]}_{name}"[:31])
    files = {"csv": "downloads/cip_panel.csv", "xlsx": "downloads/cip_analysis.xlsx", "pdf": "downloads/cip_report.pdf"}
    html = dashboard.build(res, df, {"log": log}, a.kor, a.fixture, files)
    (out / "index.html").write_text(html, encoding="utf-8")
    ok = make_pdf(out / "index.html", dl / "cip_report.pdf")
    print("dashboard:", out / "index.html", "| pdf:", ok)


if __name__ == "__main__":
    main()
