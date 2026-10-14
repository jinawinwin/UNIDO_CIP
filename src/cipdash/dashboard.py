"""Assemble the static dashboard (one HTML file) from analysis results."""
from __future__ import annotations

import html
from datetime import date

import pandas as pd

from .analysis import DIM_KO, IND_KO, STAGES

CSS = """
:root{color-scheme:light;--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e6e5e1;--blue:#2a78d6;--def:#eef4fd;--read:#eef7f2;--warn:#fff6e0;--warnb:#c98500}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.65 "Noto Sans KR","Noto Sans CJK KR","Malgun Gothic","Apple SD Gothic Neo",system-ui,sans-serif}
header{padding:32px 24px 20px;max-width:1100px;margin:0 auto}h1{font-size:26px;margin:0 0 6px}header p{margin:0;color:var(--ink2)}
nav{position:sticky;top:0;background:rgba(252,252,251,.95);border-bottom:1px solid var(--line);z-index:5}
nav div{max-width:1100px;margin:0 auto;padding:8px 24px;display:flex;gap:6px;flex-wrap:wrap}nav a{color:var(--ink2);text-decoration:none;padding:4px 10px;border-radius:14px;font-size:13px}nav a:hover{background:var(--def);color:var(--blue)}
main{max-width:1100px;margin:0 auto;padding:0 24px 80px}section{padding-top:28px}h2{font-size:21px;margin:0 0 14px;padding-bottom:6px;border-bottom:2px solid var(--ink)}h3{font-size:16px;margin:22px 0 8px}
.box{border-left:4px solid;border-radius:6px;padding:10px 14px;margin:12px 0;font-size:14px}.box b.t{display:block;margin-bottom:2px;font-size:13px;letter-spacing:.02em}
.box.def{background:var(--def);border-color:var(--blue)}.box.read{background:var(--read);border-color:#1baf7a}.box.warn{background:var(--warn);border-color:var(--warnb)}
.box ul{margin:4px 0 0 18px;padding:0}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.card{border:1px solid var(--line);border-radius:8px;padding:8px;background:#fff;margin:12px 0;break-inside:avoid}
.tbl{border-collapse:collapse;width:100%;font-size:13px;margin:8px 0}.tbl th,.tbl td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}.tbl th:first-child,.tbl td:first-child{text-align:left}.tbl thead th{background:#f4f3ef;font-weight:600}
.tw{overflow-x:auto;margin:8px 0}.cap{font-size:12px;color:var(--ink2);margin:6px 0 0}.banner{background:#e34948;color:#fff;padding:10px 24px;text-align:center;font-weight:700}
.float{position:fixed;right:18px;bottom:18px;z-index:20;font-size:14px}.float button{background:var(--blue);color:#fff;border:0;border-radius:24px;padding:11px 18px;font:inherit;font-weight:600;cursor:pointer;box-shadow:0 4px 14px rgba(0,0,0,.25)}
.float .panel{display:none;background:#fff;border:1px solid var(--line);border-radius:10px;padding:12px;margin-bottom:8px;box-shadow:0 6px 20px rgba(0,0,0,.2);min-width:230px}.float.open .panel{display:block}
.float a{display:block;padding:8px 10px;border-radius:6px;color:var(--ink);text-decoration:none}.float a:hover{background:var(--def)}.float small{display:block;color:var(--ink2);padding:0 10px 6px}
@media(max-width:800px){.grid{grid-template-columns:1fr}}
@media print{nav,.float{display:none}.grid{grid-template-columns:1fr}body{font-size:12.5px}section{break-before:auto}h2{break-after:avoid}.box,.card{break-inside:avoid}}
"""


def box(kind, title, body):
    return f'<div class="box {kind}"><b class="t">{html.escape(title)}</b>{body}</div>'


def tbl(df: pd.DataFrame, cap=None, nd=3):
    if df is None or df.empty:
        return ""
    d = df.copy()
    for c in d.columns:
        if pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].map(lambda v: "" if pd.isna(v) else (f"{v:,.{nd}f}" if abs(v) < 100 else f"{v:,.1f}"))
    h = d.to_html(classes="tbl", border=0, escape=True)
    return f'<div class="tw">{h}</div>' + (f'<p class="cap">{html.escape(cap)}</p>' if cap else "")


class Fig:
    def __init__(self):
        self.first = True

    def __call__(self, fig):
        h = fig.to_html(full_html=False, include_plotlyjs=True if self.first else False,
                        config={"displaylogo": False, "responsive": True, "toImageButtonOptions": {"format": "png", "scale": 2}})
        self.first = False
        return f'<div class="card">{h}</div>'


def _rk(f):
    if "kor_rank" not in f:
        return ""
    s = f"{f['latest']}년 한국의 CIP는 {f['kor_rank']}위/{f['n_latest']}개국(점수 {f['kor_cip']:.3f})입니다."
    if "kor_rank_base" in f:
        d = f["kor_rank_base"] - f["kor_rank"]
        mv = "상승" if d > 0 else "하락" if d < 0 else "유지"
        s += f" {f['base_year']}년({f['kor_rank_base']}위) 대비 순위는 {abs(d)}계단 {mv}했습니다."
    return s


def build(res, df, meta_info, kor="KOR", fixture=False, files=None) -> str:
    fg = Fig()
    D, U, M, P, G = res["descriptive"], res["upgrading"], res["mit"], res["policy"], res["gvc"]
    d = D["facts"]
    out = []
    # ---------------- section 1
    s = ['<section id="s1"><h2>1. 기술통계 (Descriptive statistics)</h2>']
    s.append(box("def", "정의", "<ul><li><b>CIP</b>(Competitive Industrial Performance): UNIDO가 각국이 제조업을 경쟁력 있게 생산·수출하는 능력을 하위지표로 요약한 합성지표</li>"
                 "<li><b>3개 차원</b>: 생산·수출 역량 / 기술 심화·고도화 / 세계 영향력. 아래 차원 점수는 각 하위지표의 연도별 백분위를 평균한 <u>이 대시보드의 자체 요약치</u>이며 UNIDO 공식 차원 점수가 아닙니다.</li>"
                 "<li><b>σ-수렴</b>: ln(CIP)의 국가 간 표준편차가 줄어드는 현상. <b>β-수렴</b>: 초기 수준이 낮을수록 증가율이 높은 현상.</li></ul>"))
    s.append(f'<p>표본: {d["n_countries"]}개국, {d["first"]}–{d["latest"]}년({d["n_years"]}개 연도), 최신연도 {d["n_latest"]}개국.</p>')
    s.append('<div class="grid">' + fg(D["figs"]["peers_trend"]) + fg(D["figs"]["radar"]) + "</div>")
    t = D["tables"]
    s.append("<h3>최신연도 요약통계</h3>" + tbl(t["summary_latest"]))
    s.append("<h3>CIP 상위 15개국</h3>" + tbl(t["top15"], nd=2))
    if "by_income" in t:
        s.append("<h3>소득군별 CIP</h3>" + tbl(t["by_income"], "소득군은 세계은행 현재 분류 기준(과거 연도에 소급 적용)."))
    s.append('<div class="grid">' + fg(D["figs"]["dist"]) + fg(D["figs"]["sigma"]) + "</div>")
    if "corr" in D["figs"]:
        s.append(fg(D["figs"]["corr"]))
    if "beta_conv" in t:
        s.append("<h3>β-수렴 회귀</h3>" + tbl(t["beta_conv"], f"종속변수: {d['first']}–{d['latest']} ln(CIP) 연평균 증가율, 표본 {d['beta_n']}개국, 이분산 강건 표준오차."))
    items = [_rk(d)] if _rk(d) else []
    if "sigma_first" in d:
        dirn = "커져" if d["sigma_last"] > d["sigma_first"] else "작아져"
        items.append(f"ln(CIP)의 국가 간 표준편차는 {d['sigma_first']:.2f}에서 {d['sigma_last']:.2f}로 {dirn} σ-수렴 {'증거가 없습니다' if dirn=='커져' else '방향입니다'}. 다만 표본 국가 수가 {d['sigma_n_first']}개국에서 {d['sigma_n_last']}개국으로 달라졌다면 구성 효과를 함께 봐야 합니다.")
    if "beta" in d:
        conv = d["beta"] < 0 and d["beta_p"] < 0.1
        items.append(f"β 계수는 {d['beta']:.4f}(p={d['beta_p']:.3f})로, 이 표본·기간에서 {'조건 없는 β-수렴(낮은 초기 수준일수록 빠른 증가)과 부합합니다' if conv else '조건 없는 β-수렴을 뒷받침하지 않습니다'}.")
    s.append(box("read", "해석", "<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in items) + "</ul>"))
    s.append(box("warn", "주의", "CIP의 세계 점유율 지표는 국가 간 합이 일정하므로, 한 국가의 상승이 다른 국가의 하락과 기계적으로 연결됩니다. 순위는 표본 구성이 바뀌면 함께 변합니다."))
    s.append("</section>")
    out.append("".join(s))
    # ---------------- section 2
    s = ['<section id="s2"><h2>2. 산업 고도화 단계 진단</h2>']
    s.append(box("def", "정의", "<ul><li><b>단계 분류 규칙</b>: 연도별 ‘생산·수출 역량’(x)과 ‘기술 심화·고도화’(y) 백분위를 3분위로 나눕니다. 둘 다 상위 1/3 = <b>선진 고도화형</b>, x만 상위 = <b>규모 선행형</b>, y만 상위 = <b>기술 선행형</b>, 둘 다 하위 1/3 = <b>초기 산업화형</b>, 그 외 = <b>추격·성장형</b>.</li>"
                 "<li><b>군집(k-means)</b>: 하위지표 백분위로 국가를 데이터 기반 유형으로 묶고, k는 실루엣 계수로 3~6 중 선택합니다.</li></ul>"))
    if "skipped" in U["facts"]:
        s.append(box("warn", "건너뜀", U["facts"]["skipped"]))
    else:
        f = U["facts"]
        s.append(fg(U["figs"]["stage_scatter"]))
        if "stage_income" in U["figs"]:
            s.append('<div class="grid">' + fg(U["figs"]["stage_income"]) + (fg(U["figs"]["kor_path"]) if "kor_path" in U["figs"] else "") + "</div>")
        elif "kor_path" in U["figs"]:
            s.append(fg(U["figs"]["kor_path"]))
        T = U["tables"]
        s.append("<h3>단계별 국가 수</h3>" + tbl(T["stage_counts"]))
        if "kor_stage_changes" in T:
            s.append("<h3>한국의 단계 변화</h3>" + tbl(T["kor_stage_changes"]))
        if "transition" in T:
            s.append(f"<h3>단계 이동 행렬 ({f['t0']}→{f['latest']})</h3>" + tbl(T["transition"]))
        if "clusters" in T:
            s.append(f"<h3>군집 프로필 (k={f['k']}, 실루엣 {f['silhouette']:.2f})</h3>" + tbl(T["clusters"], "하위지표 열은 백분위 평균."))
        items = []
        if "kor_stage" in f:
            items.append(f"한국은 {f['latest']}년 ‘{f['kor_stage']}’로 분류됩니다(역량 {f['kor_dims'][0]:.0f}, 심화 {f['kor_dims'][1]:.0f} 백분위).")
        if "trans_n" in f:
            items.append(f"{f['t0']}년과 {f['latest']}년 모두 자료가 있는 {f['trans_n']}개국 중 {f['trans_up']}개국이 상위 단계로 이동했고 {f['trans_same']}개국이 같은 단계에 머물렀습니다. 백분위 기준이라 ‘상대적’ 이동이며 절대 수준의 향상과는 다릅니다.")
        if f.get("kor_cluster"):
            items.append(f"한국은 데이터 기반 군집 중 {f['kor_cluster']}에 속합니다.")
        s.append(box("read", "해석", "<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in items) + "</ul>"))
        s.append(box("warn", "주의", "분류 임계값(33.3/66.7 백분위)은 분석자의 선택이며 UNIDO 공식 분류가 아닙니다. 임계값을 바꾸면 경계 국가의 단계가 달라질 수 있습니다."))
    s.append("</section>")
    out.append("".join(s))
    # ---------------- section 3
    s = ['<section id="s3"><h2>3. 중진국 함정 (Middle-income trap) 논의</h2>']
    s.append(box("def", "정의", "<ul><li><b>중진국 함정</b>: 중소득 수준에 도달한 뒤 제조업 고도화와 생산성 향상이 정체되어 고소득으로 넘어가지 못하는 현상(통일된 정량 정의는 없음).</li>"
                 "<li><b>CIP 격차(gap)</b> = CIP 백분위 − 1인당 소득 백분위. 양수면 소득 대비 제조업 경쟁력이 높고, 음수면 낮습니다.</li>"
                 "<li><b>정체 후보</b>(이 대시보드의 조작적 정의): 세계은행 분류상 중소득국이면서 최근 약 10년간 CIP 백분위가 개선되지 않았고 1인당 GDP 성장률이 중소득국 중위수보다 낮은 국가.</li></ul>"))
    if "skipped" in M["facts"]:
        s.append(box("warn", "건너뜀", M["facts"]["skipped"]))
    else:
        f = M["facts"]
        s.append(fg(M["figs"]["income_cip"]))
        s.append('<div class="grid">' + (fg(M["figs"]["gap"]) if "gap" in M["figs"] else "") + fg(M["figs"]["paths"]) + "</div>")
        if "mic_table" in M["tables"]:
            s.append("<h3>중소득국의 10년 변화 (CIP 백분위 하위 순)</h3>" + tbl(M["tables"]["mic_table"], f"기준 연도 {f['t0']} → {f['latest']}.", nd=1))
        items = [f"소득(로그)과 CIP의 2차 적합 설명력은 R²={f['r2']:.2f}입니다. 소득만으로 설명되지 않는 부분이 국가 간 제조업 경쟁력의 독자적 차이입니다."]
        if "n_tc" in f:
            items.append(f"중소득국 {f['n_tc']}개국 중 {f['n_trap']}개국이 ‘정체 후보’, {f['n_up']}개국이 ‘고도화 진행’(CIP 백분위 5p 초과 상승)으로 분류됩니다.")
        s.append(box("read", "해석", "<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in items) + "</ul>"))
        s.append(box("warn", "주의", "소득군은 세계은행 현재 분류이며, ‘정체 후보’는 기술적(descriptive) 기준이지 함정의 인과 판정이 아닙니다. 자원 가공 비중이 높은 국가는 CIP가 높아도 고도화 수준이 낮을 수 있습니다."))
    s.append("</section>")
    out.append("".join(s))
    # ---------------- section 4
    s = ['<section id="s4"><h2>4. 개발정책 평가</h2>']
    s.append(box("def", "정의", "<ul><li><b>고정효과 패널회귀</b>: 국가별·연도별 고정효과를 통제하고, 1기 지연된 FDI, 무역개방도, 총자본형성, R&D가 CIP 점수와 같이 움직이는지 추정합니다. 표준오차는 국가 단위 클러스터.</li>"
                 "<li><b>2018년 전후 비교</b>: 2018년 이후 무역정책 충격 시기의 CIP 증가율을 직전 5년과 소득군별로 비교하는 기술적 분석입니다.</li></ul>"))
    if "skipped" in P["facts"]:
        s.append(box("warn", "건너뜀", P["facts"]["skipped"]))
    else:
        f = P["facts"]
        if "fe_coef" in P["figs"]:
            s.append(fg(P["figs"]["fe_coef"]))
            s.append("<h3>회귀 결과표</h3>" + tbl(P["tables"]["fe_regression"], nd=4))
        if "index_group" in P["figs"]:
            s.append(fg(P["figs"]["index_group"]))
            s.append("<h3>2018년 전후 CIP 증가율</h3>" + tbl(P["tables"]["prepost"], nd=2))
        items = []
        for r in f.get("fe_rows", []):
            if r["p값"] < 0.05 and "GDP" not in r["변수"]:
                items.append(f"{r['모형']}: {r['변수']}의 계수는 {r['계수']:.4f}(p={r['p값']:.3f})로 5% 수준에서 유의합니다.")
        if f.get("fe_rows") and not items:
            items.append("정책 관련 설명변수 중 5% 수준에서 유의한 계수는 없습니다.")
        if "kor_pre" in f:
            items.append(f"한국의 ln(CIP) 연평균 증가율은 2013–17년 {f['kor_pre']:.2f}%, 2018년 이후 {f['kor_post']:.2f}%입니다.")
        s.append(box("read", "해석", "<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in items) + "</ul>"))
        s.append(box("warn", "주의", "계수는 인과효과가 아니라 고정효과 조건부 연관성입니다. 역인과, 누락 변수, 지연 구조 설정이 결과에 영향을 줄 수 있습니다. 관세·수출통제 노출도 자료를 결합한 이벤트스터디가 인과 식별에 더 적합한 다음 단계입니다."))
    s.append("</section>")
    out.append("".join(s))
    # ---------------- section 5
    s = ['<section id="s5"><h2>5. GVC 위치와의 보완 해석</h2>']
    s.append(box("def", "정의", "<ul><li>CIP의 수출 지표는 <b>총수출(gross)</b> 기준이라 수출에 담긴 해외 부가가치를 구분하지 못합니다.</li>"
                 "<li><b>수출-부가가치 배율</b>(이 대시보드의 대리지표): 제조업 수출이 제조업 부가가치 대비 얼마나 큰지를 나타냅니다. 값이 매우 크면 수입 중간재를 가공·재수출하는 조립·허브형일 가능성을 시사하지만 확정 증거는 아닙니다.</li>"
                 "<li><b>TiVA</b>(OECD): 수출의 국내·해외 부가가치를 분해한 자료. data/raw/manual/tiva.csv(iso3, year, 지표열)를 두면 직접 비교가 추가됩니다.</li></ul>"))
    if "skipped" in G["facts"]:
        s.append(box("warn", "건너뜀", G["facts"]["skipped"]))
    else:
        f = G["facts"]
        s.append('<div class="grid">' + fg(G["figs"]["scatter"]) + fg(G["figs"]["trend"]) + "</div>")
        if "tiva" in G["figs"]:
            s.append(fg(G["figs"]["tiva"]))
        s.append("<h3>배율 상위 10개국</h3>" + tbl(G["tables"]["top_ratio"]))
        items = [f"정의: {f['label']}."]
        if "kor_ratio" in f:
            items.append(f"한국의 배율은 {f['kor_ratio']:.2f}로 {f['latest']}년 표본의 {f['kor_ratio_pct']:.0f}백분위입니다.")
        items.append("CIP가 높은 국가 중에서도 배율이 높은 국가는 수출 규모에 비해 국내 부가가치 창출이 작은 구조일 수 있어 TiVA의 국내 부가가치율로 확인해야 합니다.")
        s.append(box("read", "해석", "<ul>" + "".join(f"<li>{html.escape(i)}</li>" for i in items) + "</ul>"))
        s.append(box("warn", "주의", "이 배율은 TiVA를 대체하지 못합니다. 단위가 다른 1인당 수출과 1인당 부가가치의 비율이어서 환율·물가 수준과 허브 경제(재수출)의 영향을 받습니다."))
    s.append("</section>")
    out.append("".join(s))
    # ---------------- data
    s = ['<section id="s6"><h2>데이터와 방법</h2>']
    s.append(box("def", "데이터 출처", "<ul><li>UNIDO Statistics Portal CIP 데이터베이스: https://stat.unido.org</li><li>보조 변수: World Bank WDI (1인당 GDP PPP, FDI, 무역, 총자본형성, R&D, 제조업 부가가치/GDP) 및 국가 소득분류</li></ul>"))
    s.append(f"<p class='cap'>읽은 파일: {html.escape('; '.join(meta_info.get('log', [])))}</p>")
    s.append(f"<p class='cap'>생성일 {date.today().isoformat()} · 지표 코드는 UNIDO Reader's Guide 약어를 따름: " + ", ".join(f"{k.upper()}={v}" for k, v in IND_KO.items()) + "</p>")
    s.append("</section>")
    out.append("".join(s))
    banner = '<div class="banner">합성 테스트 데이터입니다. 실제 UNIDO 자료가 아니며 배포 대상이 아닙니다.</div>' if fixture else ""
    nav = "".join(f'<a href="#s{i}">{t}</a>' for i, t in [(1, "기술통계"), (2, "고도화 단계"), (3, "중진국 함정"), (4, "정책 평가"), (5, "GVC"), (6, "데이터")])
    files = files or {}
    fl = f"""<div class="float" id="fl"><div class="panel"><small>데이터와 보고서 내려받기</small>
<a href="{files.get('csv','#')}" download>⬇ 분석용 패널 데이터 (CSV)</a>
<a href="{files.get('xlsx','#')}" download>⬇ 전체 표 (Excel)</a>
<a href="{files.get('pdf','#')}" download>⬇ 보고서 (PDF)</a></div>
<button onclick="document.getElementById('fl').classList.toggle('open')" aria-expanded="false">⬇ 데이터 · 보고서</button></div>"""
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>UNIDO CIP 대시보드</title><style>{CSS}</style></head><body>{banner}
<header><h1>UNIDO 경쟁적 산업성과지수(CIP) 분석 대시보드</h1><p>제조업 경쟁력의 기술통계, 고도화 단계, 중진국 함정, 정책 연관성, GVC 보완 해석</p></header>
<nav><div>{nav}</div></nav><main>{''.join(out)}</main>{fl}</body></html>"""
