"""Best-effort crawler for the UNIDO CIP database page.

stat.unido.org is a JavaScript portal and its download endpoints are not documented, so this script
(1) opens the page in headless Chromium, (2) records every network response that looks like data,
(3) clicks anything that says Download/Export/CSV/Excel and saves the downloads, and
(4) writes data/raw/unido/_discovery.json listing every URL it saw so the selector can be refined.
Whatever lands in data/raw/unido or data/raw/manual is picked up by the pipeline.
"""
from __future__ import annotations
import json
import re
from pathlib import Path

PORTAL = "https://stat.unido.org/database/CIP%20-%20Competitive%20Industrial%20Performance%20Index"
DATA_TYPES = ("json", "csv", "excel", "spreadsheet", "octet-stream", "zip")


def run(out: Path = Path("data/raw/unido")) -> int:
    from playwright.sync_api import sync_playwright

    out.mkdir(parents=True, exist_ok=True)
    seen, saved = [], 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(accept_downloads=True, locale="en-US")
        page = ctx.new_page()

        def on_response(r):
            nonlocal saved
            ct = (r.headers.get("content-type") or "").lower()
            seen.append({"url": r.url, "status": r.status, "type": ct})
            if r.status == 200 and any(t in ct for t in DATA_TYPES) and "stat.unido.org" in r.url:
                try:
                    body = r.body()
                except Exception:
                    return
                if len(body) > 2000:
                    ext = "json" if "json" in ct else "csv" if "csv" in ct else "xlsx" if ("excel" in ct or "sheet" in ct) else "bin"
                    if ext != "bin":
                        saved += 1
                        (out / f"api_{saved:03d}.{ext}").write_bytes(body)

        page.on("response", on_response)
        try:
            page.goto(PORTAL, wait_until="domcontentloaded", timeout=60_000)
        except Exception as e:
            print("goto warning:", e)
        page.wait_for_timeout(15_000)
        try:
            page.screenshot(path=str(out / "portal.png"), full_page=True)
            body_text = page.inner_text("body")[:6000]
        except Exception as e:
            body_text = f"(no body: {e})"
        links = page.eval_on_selector_all("a[href]", "els => els.map(e => [e.href, e.innerText])")
        for href, text in links:
            if re.search(r"\.(csv|xlsx?|zip)(\?|$)", href, re.I):
                try:
                    resp = ctx.request.get(href)
                    name = re.sub(r"[^A-Za-z0-9._-]", "_", href.split("/")[-1].split("?")[0])
                    (out / name).write_bytes(resp.body())
                    saved += 1
                except Exception as e:
                    seen.append({"url": href, "error": str(e)})
        for label in ("Download", "Export", "CSV", "Excel", "XLSX"):
            for el in page.get_by_text(re.compile(label, re.I)).all()[:5]:
                try:
                    with page.expect_download(timeout=20_000) as dl:
                        el.click(timeout=3000)
                    d = dl.value
                    d.save_as(out / re.sub(r"[^A-Za-z0-9._-]", "_", d.suggested_filename))
                    saved += 1
                except Exception:
                    continue
        (out / "_discovery.json").write_text(json.dumps({"body_text": body_text, "page_links": links[:300], "responses": seen[:500]}, indent=1))
        browser.close()
    print(f"UNIDO crawler saved {saved} data file(s); see {out}/_discovery.json")
    return saved


if __name__ == "__main__":
    run()
