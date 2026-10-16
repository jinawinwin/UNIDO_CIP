"""python -m cipdash.pipeline [--fetch] [--crawl-unido] [--raw data/raw] [--wb data/raw/wb] [--out site]"""
from __future__ import annotations
import argparse
from pathlib import Path

import pandas as pd

from . import analysis, dashboard, fetch_wb, schema

EXPORT_COLS = ["iso3", "country", "year", "cip", "cip_rank", "cip_pct", "dim_capacity", "dim_deepening", "dim_impact", "stage",
               "income", "region", "gdppc_ppp", "fdi_gdp", "trade_gdp", "gcf_gdp", "rd_gdp", "mva_gdp"] + schema.INDICATORS


PLACEHOLDER = """<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UNIDO CIP 대시보드</title><body style="font:16px/1.7 'Noto Sans KR',system-ui,sans-serif;max-width:760px;margin:48px auto;padding:0 20px;color:#0b0b0b">
<h1>UNIDO CIP 대시보드: 데이터 수집 확인 필요</h1>
<p>이번 빌드에서 분석에 필요한 CIP 관측치를 확보하지 못했습니다. 빈 그래프나 임의의 실측치를 표시하지 않았습니다.</p>
<ol><li><a href="https://stat.unido.org/portal/dataset/getDataset/CIP">UNIDO 공식 CIP API 메타데이터</a> 및 <a href="https://stat.unido.org/unido-statistics-portal-api">API 가이드</a>의 응답 상태를 확인합니다.</li>
<li>저장소의 <code>crawl-log</code> 브랜치에서 <code>_fetch_log.json</code> 및 <code>pipeline.log</code>를 열어 오류를 확인합니다.</li>
<li>API 접근이 일시적으로 불가능하면 공식 포털에서 CIP CSV/Excel을 내려받아 <code>data/raw/manual/</code>에 올리면 대체 입력으로 분석할 수 있습니다.</li></ol></body></html>"""


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
    ap.add_argument("--fetch", action="store_true", help="download World Bank data first")
    ap.add_argument("--crawl-unido", action="store_true", help="download CIP observations using UNIDO's documented public API")
    ap.add_argument("--raw", default="data/raw")
    ap.add_argument("--wb", default="data/raw/wb")
    ap.add_argument("--out", default="site")
    ap.add_argument("--kor", default="KOR")
    ap.add_argument("--fixture", action="store_true")
    a = ap.parse_args(argv)
    raw, wbdir, out = Path(a.raw), Path(a.wb), Path(a.out)
    if a.crawl_unido:
        from . import fetch_unido
        try:
            fetch_unido.run(raw / "unido")
        except Exception as e:
            print("UNIDO API collection failed:", e)
    if a.fetch:
        try:
            fetch_wb.fetch_all(wbdir)
        except Exception as e:
            print("World Bank fetch failed:", e)
    meta, wbind = fetch_wb.load(wbdir)
    try:
        panel, log = schema.load_panel(raw, meta[["iso3", "name"]] if meta is not None else None)
    except SystemExit as e:
        print("::warning title=No CIP data::" + str(e).replace("\n", " | ")[:900])
        out.mkdir(parents=True, exist_ok=True)
        (out / "index.html").write_text(PLACEHOLDER, encoding="utf-8")
        print("No CIP observations found: wrote a diagnostic page, not an empty analytical dashboard.")
        return
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
