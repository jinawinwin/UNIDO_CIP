"""Analysis modules: descriptive stats, upgrading stage, middle-income trap, policy evaluation, GVC complement.

Each module returns tables (DataFrames), figures (plotly) and facts (numbers used by the dashboard text boxes).
All statements generated from facts are descriptive; the policy module is associational, not causal.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import statsmodels.api as sm
from linearmodels.panel import PanelOLS
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

# ---------- palette (validated reference palette, light mode) ----------
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6", "#e87ba4", "#eda100", "#008300", "#e34948"]
BLUES = ["#cfe0f7", "#9fc2ef", "#6ea3e6", "#2a78d6", "#1b4f93"]
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e6e5e1"
FONT = "Noto Sans KR, Noto Sans CJK KR, Malgun Gothic, Apple SD Gothic Neo, system-ui, sans-serif"

BASE_IND = ["mvapc", "mxpc", "mvash", "mhvash", "mxsh", "mhxsh", "imwmva", "imwmt"]
DIMS = {"capacity": ["mvapc", "mxpc"], "deepening": ["mvash", "mhvash", "mxsh", "mhxsh"], "impact": ["imwmva", "imwmt"]}
DIM_KO = {"capacity": "생산·수출 역량", "deepening": "기술 심화·고도화", "impact": "세계 영향력"}
IND_KO = {"mvapc": "1인당 제조업 부가가치", "mxpc": "1인당 제조업 수출", "mvash": "GDP 대비 제조업 부가가치",
          "mhvash": "중고위기술 부가가치 비중", "mxsh": "총수출 중 제조업 비중", "mhxsh": "제조업 수출 중 중고위기술 비중",
          "imwmva": "세계 제조업 부가가치 점유율", "imwmt": "세계 제조업 수출 점유율"}
INCOME_KO = {"LIC": "저소득", "LMC": "중하위소득", "UMC": "중상위소득", "HIC": "고소득"}
INCOME_ORDER = ["저소득", "중하위소득", "중상위소득", "고소득"]
STAGES = ["초기 산업화형", "추격·성장형", "기술 선행형", "규모 선행형", "선진 고도화형"]
PEERS = ["KOR", "JPN", "DEU", "CHN", "USA", "VNM"]


def style(fig, title=None, height=420, legend=True):
    fig.update_layout(
        title=dict(text=title, x=0, font=dict(size=15, color=INK)) if title else None,
        height=height, paper_bgcolor="white", plot_bgcolor="white",
        font=dict(family=FONT, size=12, color=INK2), margin=dict(l=55, r=20, t=55 if title else 20, b=50),
        legend=dict(orientation="h", y=1.08, x=0, font=dict(size=11)), showlegend=legend, hoverlabel=dict(font_family=FONT))
    fig.update_xaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, linecolor=GRID)
    return fig


def pct_rank(df, col):
    return df.groupby("year")[col].rank(pct=True) * 100


# ---------------------------------------------------------------- preparation
def prepare(panel: pd.DataFrame, meta, wbind, kor="KOR") -> pd.DataFrame:
    df = panel.copy()
    if meta is not None:
        m = meta.copy()
        m["income_ko"] = m["income"].map(INCOME_KO)
        df = df.merge(m[["iso3", "income", "income_ko", "region"]], on="iso3", how="left")
    else:
        df["income"] = np.nan
        df["income_ko"] = np.nan
        df["region"] = np.nan
    if wbind is not None:
        df = df.merge(wbind, on=["iso3", "year"], how="left")
    have = [c for c in BASE_IND if c in df]
    for c in have:
        df[f"p_{c}"] = pct_rank(df, c)
    for d, cols in DIMS.items():
        use = [f"p_{c}" for c in cols if c in df]
        df[f"dim_{d}"] = df[use].mean(axis=1) if use else np.nan
    if "cip" not in df:  # fallback proxy, clearly labelled
        df["cip"] = df[[f"p_{c}" for c in have]].mean(axis=1) / 100
        df.attrs["cip_is_proxy"] = True
    df["cip_rank"] = df.groupby("year")["cip"].rank(ascending=False, method="min")
    df["cip_pct"] = pct_rank(df, "cip")
    df["n_year"] = df.groupby("year")["cip"].transform("count")
    d1, d2 = df["dim_capacity"], df["dim_deepening"]
    stage = np.select(
        [(d1 >= 66.7) & (d2 >= 66.7), d1 >= 66.7, d2 >= 66.7, (d1 >= 33.3) | (d2 >= 33.3)],
        ["선진 고도화형", "규모 선행형", "기술 선행형", "추격·성장형"], default="초기 산업화형")
    df["stage"] = np.where(d1.notna() & d2.notna(), stage, None)
    return df


def _kor_row(df, kor, year):
    r = df[(df.iso3 == kor) & (df.year == year)]
    return r.iloc[0] if len(r) else None


def table_html_ready(t: pd.DataFrame, nd=2) -> pd.DataFrame:
    return t.round(nd)


# ---------------------------------------------------------------- 1. descriptive
def descriptive(df, kor="KOR"):
    T, F, facts = {}, {}, {}
    cip = df.dropna(subset=["cip"])
    L, first = int(cip.year.max()), int(cip.year.min())
    lat = cip[cip.year == L]
    facts.update(latest=L, first=first, n_latest=len(lat), n_countries=cip.iso3.nunique(), n_years=cip.year.nunique())
    ind = [c for c in ["cip"] + BASE_IND if c in df]
    d = lat[ind].describe().T[["count", "mean", "std", "min", "25%", "50%", "75%", "max"]]
    d.index = [("CIP 종합점수" if i == "cip" else f"{i.upper()} ({IND_KO[i]})") for i in d.index]
    T["summary_latest"] = d
    top = lat.sort_values("cip", ascending=False)[["cip_rank", "country", "iso3", "cip"] + [f"dim_{k}" for k in DIMS]].head(15)
    top.columns = ["순위", "국가", "ISO3", "CIP"] + [DIM_KO[k] + "(백분위)" for k in DIMS]
    T["top15"] = top.set_index("순위")
    if lat["income_ko"].notna().any():
        g = lat.groupby("income_ko")["cip"].agg(["count", "mean", "median"]).reindex(INCOME_ORDER).dropna(how="all")
        g.columns = ["국가 수", "평균", "중위수"]
        T["by_income"] = g
    # Korea
    kr = _kor_row(df, kor, L)
    if kr is not None:
        facts.update(kor_rank=int(kr.cip_rank), kor_cip=float(kr.cip))
        yb = max(first, L - 10)
        kb = _kor_row(df, kor, yb)
        if kb is not None:
            facts.update(kor_rank_base=int(kb.cip_rank), base_year=yb, kor_cip_base=float(kb.cip))
    # peers trend
    fig = go.Figure()
    peers = [p for p in PEERS if p in set(cip.iso3)]
    for i, p in enumerate(peers):
        s = cip[cip.iso3 == p]
        fig.add_trace(go.Scatter(x=s.year, y=s.cip, name=s.country.iloc[0], mode="lines",
                                 line=dict(width=3 if p == kor else 2, color=SERIES[i])))
    F["peers_trend"] = style(fig, "CIP 종합점수 추이: 한국과 비교국", 400)
    F["peers_trend"].update_yaxes(title="CIP 점수")
    # radar
    fig = go.Figure()
    cats = [DIM_KO[k] for k in DIMS if lat[f"dim_{k}"].notna().any()]
    keys = [k for k in DIMS if lat[f"dim_{k}"].notna().any()]
    for i, p in enumerate(peers):
        r = lat[lat.iso3 == p]
        if len(r):
            v = [float(r[f"dim_{k}"].iloc[0]) for k in keys]
            fig.add_trace(go.Scatterpolar(r=v + v[:1], theta=cats + cats[:1], name=r.country.iloc[0],
                                          line=dict(color=SERIES[i], width=3 if p == kor else 2), fill="none"))
    fig.update_layout(polar=dict(radialaxis=dict(range=[0, 100], gridcolor=GRID, linecolor=GRID), angularaxis=dict(gridcolor=GRID)))
    F["radar"] = style(fig, f"차원별 상대 위치 ({L}년, 백분위 0–100)", 420)
    # distribution
    fig = go.Figure(go.Histogram(x=lat.cip, nbinsx=25, marker=dict(color=BLUES[2], line=dict(color="white", width=1))))
    if kr is not None:
        fig.add_vline(x=float(kr.cip), line=dict(color=SERIES[1], width=2), annotation_text="한국", annotation_font_color=INK2)
    F["dist"] = style(fig, f"CIP 점수 분포 ({L}년)", 360, legend=False)
    F["dist"].update_xaxes(title="CIP 점수").update_yaxes(title="국가 수")
    # sigma convergence
    sg = cip[cip.cip > 0].groupby("year")["cip"].apply(lambda s: np.log(s).std()).reset_index(name="sd")
    cnt = cip.groupby("year")["iso3"].nunique().reset_index(name="n")
    sg = sg.merge(cnt, on="year")
    fig = go.Figure(go.Scatter(x=sg.year, y=sg.sd, mode="lines+markers", line=dict(color=SERIES[0], width=2), marker=dict(size=6),
                               customdata=sg.n, hovertemplate="%{x}: %{y:.3f} (n=%{customdata})<extra></extra>"))
    F["sigma"] = style(fig, "σ-수렴: ln(CIP)의 국가 간 표준편차", 360, legend=False)
    F["sigma"].update_yaxes(title="표준편차")
    facts["sigma_first"], facts["sigma_last"] = float(sg.sd.iloc[0]), float(sg.sd.iloc[-1])
    facts["sigma_n_first"], facts["sigma_n_last"] = int(sg.n.iloc[0]), int(sg.n.iloc[-1])
    # beta convergence on balanced pair
    a = cip[cip.year == first].set_index("iso3")["cip"]
    b = cip[cip.year == L].set_index("iso3")["cip"]
    j = pd.concat([a, b], axis=1, keys=["a", "b"]).dropna()
    j = j[(j.a > 0) & (j.b > 0)]
    if len(j) > 20 and L > first:
        y = (np.log(j.b) - np.log(j.a)) / (L - first)
        res = sm.OLS(y, sm.add_constant(np.log(j.a))).fit(cov_type="HC1")
        facts.update(beta=float(res.params.iloc[1]), beta_p=float(res.pvalues.iloc[1]), beta_n=int(len(j)))
        T["beta_conv"] = pd.DataFrame({"계수": res.params.values, "표준오차(HC1)": res.bse.values, "p값": res.pvalues.values},
                                      index=["상수항", f"ln(CIP {first})"])
    # correlation
    cols = [c for c in BASE_IND if c in lat and lat[c].notna().sum() > 10]
    if len(cols) >= 3:
        C = lat[cols].rank().corr()
        fig = go.Figure(go.Heatmap(z=C.values, x=[c.upper() for c in cols], y=[c.upper() for c in cols], zmin=-1, zmax=1,
                                   colorscale=[[0, "#eb6834"], [0.5, "#f1f0ec"], [1, "#2a78d6"]],
                                   text=np.round(C.values, 2), texttemplate="%{text}", hovertemplate="%{x} × %{y}: %{z:.2f}<extra></extra>"))
        F["corr"] = style(fig, f"하위지표 순위상관 ({L}년, 스피어만)", 420, legend=False)
        F["corr"].update_yaxes(autorange="reversed")
    return dict(tables=T, figs=F, facts=facts)


# ---------------------------------------------------------------- 2. upgrading stage
def upgrading(df, kor="KOR"):
    T, F, facts = {}, {}, {}
    s = df.dropna(subset=["stage", "cip"])
    if s.empty:
        return dict(tables=T, figs=F, facts=dict(skipped="차원 점수를 계산할 하위지표가 부족합니다."))
    L = int(s.year.max())
    lat = s[s.year == L]
    # scatter
    fig = go.Figure()
    for i, st in enumerate(STAGES):
        z = lat[lat.stage == st]
        if len(z):
            fig.add_trace(go.Scatter(x=z.dim_capacity, y=z.dim_deepening, mode="markers", name=st,
                                     marker=dict(size=9, color=BLUES[i], line=dict(color="white", width=1.5)),
                                     text=z.country, hovertemplate="%{text}<br>역량 %{x:.0f} / 심화 %{y:.0f}<extra></extra>"))
    k = lat[lat.iso3 == kor]
    if len(k):
        fig.add_trace(go.Scatter(x=k.dim_capacity, y=k.dim_deepening, mode="markers+text", text=["한국"], textposition="top center",
                                 name="한국", marker=dict(size=14, color=SERIES[1], line=dict(color="white", width=2))))
        facts["kor_stage"] = k.stage.iloc[0]
        facts["kor_dims"] = (float(k.dim_capacity.iloc[0]), float(k.dim_deepening.iloc[0]))
    for v in (33.3, 66.7):
        fig.add_vline(x=v, line=dict(color=GRID, dash="dot"))
        fig.add_hline(y=v, line=dict(color=GRID, dash="dot"))
    F["stage_scatter"] = style(fig, f"산업 고도화 단계 지도 ({L}년)", 480)
    F["stage_scatter"].update_xaxes(title="생산·수출 역량 (백분위)", range=[0, 102]).update_yaxes(title="기술 심화·고도화 (백분위)", range=[0, 102])
    # stage counts
    cnt = lat.stage.value_counts().reindex(STAGES).fillna(0).astype(int)
    T["stage_counts"] = cnt.rename("국가 수").to_frame()
    if lat.income_ko.notna().any():
        ct = pd.crosstab(lat.income_ko, lat.stage).reindex(index=INCOME_ORDER, columns=STAGES).dropna(how="all").fillna(0)
        share = ct.div(ct.sum(axis=1), axis=0) * 100
        fig = go.Figure()
        for i, st in enumerate(STAGES):
            fig.add_trace(go.Bar(y=share.index, x=share[st], name=st, orientation="h", marker=dict(color=BLUES[i], line=dict(color="white", width=2)),
                                 hovertemplate="%{y} · " + st + ": %{x:.0f}%<extra></extra>"))
        fig.update_layout(barmode="stack")
        F["stage_income"] = style(fig, "소득군별 단계 구성비 (%)", 320)
        F["stage_income"].update_yaxes(autorange="reversed")
        T["stage_income"] = ct.astype(int)
    # Korea path
    kp = s[s.iso3 == kor].sort_values("year")
    if len(kp):
        fig = go.Figure()
        for i, key in enumerate(DIMS):
            if kp[f"dim_{key}"].notna().any():
                fig.add_trace(go.Scatter(x=kp.year, y=kp[f"dim_{key}"], name=DIM_KO[key], mode="lines", line=dict(color=SERIES[i], width=2.5)))
        F["kor_path"] = style(fig, "한국의 차원별 백분위 추이", 360)
        F["kor_path"].update_yaxes(range=[0, 102], title="백분위")
        chg = kp.assign(chg=kp.stage != kp.stage.shift()).query("chg")[["year", "stage"]]
        T["kor_stage_changes"] = chg.rename(columns={"year": "연도", "stage": "단계"}).set_index("연도")
    # transition
    yrs = sorted(s.year.unique())
    t0 = min(yrs, key=lambda y: abs(y - (L - 10)))
    if t0 < L:
        a = s[s.year == t0].set_index("iso3").stage
        b = lat.set_index("iso3").stage
        j = pd.concat([a, b], axis=1, keys=["from", "to"]).dropna()
        tm = pd.crosstab(j["from"], j["to"]).reindex(index=STAGES, columns=STAGES).fillna(0).astype(int)
        tm.index.name = f"{t0}년 단계 ↓ / {L}년 단계 →"
        T["transition"] = tm
        up = (j["from"].map({s_: i for i, s_ in enumerate(STAGES)}) < j["to"].map({s_: i for i, s_ in enumerate(STAGES)})).sum()
        facts.update(t0=t0, trans_n=len(j), trans_up=int(up), trans_same=int((j["from"] == j["to"]).sum()))
    # clusters
    feats = [f"p_{c}" for c in BASE_IND if f"p_{c}" in lat and lat[f"p_{c}"].notna().all()]
    X = lat.dropna(subset=feats) if feats else lat.iloc[0:0]
    if len(feats) >= 3 and len(X) >= 30:
        best, bk = -1, 3
        for k_ in range(3, 7):
            lab = KMeans(k_, n_init=10, random_state=0).fit_predict(X[feats])
            sc = silhouette_score(X[feats], lab)
            if sc > best:
                best, bk = sc, k_
        km = KMeans(bk, n_init=10, random_state=0).fit(X[feats])
        X = X.assign(cl=km.labels_)
        order = X.groupby("cl")["cip"].mean().sort_values(ascending=False).index
        name = {c: f"군집 {chr(65 + i)}" for i, c in enumerate(order)}
        X["군집"] = X.cl.map(name)
        prof = X.groupby("군집")[feats].mean()
        prof.columns = [c[2:].upper() for c in prof.columns]
        prof.insert(0, "CIP 평균", X.groupby("군집")["cip"].mean())
        prof.insert(0, "국가 수", X.groupby("군집").size())
        prof["대표 국가"] = X.sort_values("cip", ascending=False).groupby("군집")["country"].apply(lambda v: ", ".join(v.head(3)))
        T["clusters"] = prof.sort_index()
        facts.update(k=bk, silhouette=float(best), kor_cluster=(X[X.iso3 == kor]["군집"].iloc[0] if (X.iso3 == kor).any() else None))
    facts["latest"] = L
    return dict(tables=T, figs=F, facts=facts)


# ---------------------------------------------------------------- 3. middle-income trap
def mit(df, kor="KOR"):
    T, F, facts = {}, {}, {}
    if "gdppc_ppp" not in df or df.gdppc_ppp.notna().sum() < 100:
        return dict(tables=T, figs=F, facts=dict(skipped="World Bank 1인당 GDP 자료가 없어 이 분석은 건너뛰었습니다."))
    s = df.dropna(subset=["cip", "gdppc_ppp"]).copy()
    L = int(s.year.max())
    lat = s[s.year == L].copy()
    lat["lny"] = np.log(lat.gdppc_ppp)
    co = np.polyfit(lat.lny, lat.cip, 2)
    lat["fit"] = np.polyval(co, lat.lny)
    lat["resid"] = lat.cip - lat.fit
    lat["gap"] = lat.cip_pct - pct_rank(lat.assign(year=L), "gdppc_ppp")  # CIP pctile minus income pctile
    facts["r2"] = float(1 - ((lat.cip - lat.fit) ** 2).sum() / ((lat.cip - lat.cip.mean()) ** 2).sum())
    facts["latest"] = L
    # scatter
    xs = np.linspace(lat.lny.min(), lat.lny.max(), 100)
    fig = go.Figure()
    mic = lat.income.isin(["LMC", "UMC"])
    for nm, mask, col in (("중소득국(세계은행 분류)", mic, BLUES[3]), ("그 외", ~mic, BLUES[0])):
        z = lat[mask]
        fig.add_trace(go.Scatter(x=np.exp(z.lny), y=z.cip, mode="markers", name=nm, text=z.country,
                                 marker=dict(size=8, color=col, line=dict(color="white", width=1.2)),
                                 hovertemplate="%{text}<br>소득 %{x:,.0f} / CIP %{y:.3f}<extra></extra>"))
    fig.add_trace(go.Scatter(x=np.exp(xs), y=np.polyval(co, xs), mode="lines", name="2차 적합선", line=dict(color=INK2, width=2, dash="dot")))
    k = lat[lat.iso3 == kor]
    if len(k):
        fig.add_trace(go.Scatter(x=k.gdppc_ppp, y=k.cip, mode="markers+text", text=["한국"], textposition="top left", name="한국",
                                 marker=dict(size=13, color=SERIES[1], line=dict(color="white", width=2))))
    F["income_cip"] = style(fig, f"소득 수준과 CIP ({L}년)", 460)
    F["income_cip"].update_xaxes(type="log", title="1인당 GDP, PPP (2021 고정 국제달러 등, 로그축)").update_yaxes(title="CIP 점수")
    # gap among MICs
    m = lat[mic].dropna(subset=["gap"])
    if len(m):
        both = pd.concat([m.nlargest(8, "gap"), m.nsmallest(8, "gap")]).drop_duplicates("iso3").sort_values("gap")
        fig = go.Figure(go.Bar(x=both.gap, y=both.country, orientation="h", marker=dict(color=[SERIES[1] if g < 0 else BLUES[3] for g in both.gap]),
                               hovertemplate="%{y}: %{x:+.0f}p<extra></extra>"))
        F["gap"] = style(fig, "중소득국의 CIP 백분위 − 소득 백분위 (상·하위 8개국)", 460, legend=False)
        F["gap"].update_xaxes(title="백분위 격차 (양수=소득 대비 제조업 경쟁력 높음)")
        facts["n_mic"] = int(len(m))
    # trap candidates: MIC, CIP percentile not improved over ~10y
    yrs = sorted(s.year.unique())
    t0 = min(yrs, key=lambda y: abs(y - (L - 10)))
    if t0 < L:
        a = s[s.year == t0].set_index("iso3")
        rows = []
        for iso, r in lat[mic].set_index("iso3").iterrows():
            if iso in a.index and pd.notna(a.loc[iso, "cip_pct"]):
                g0, g1 = a.loc[iso, "gdppc_ppp"], r.gdppc_ppp
                rows.append(dict(ISO3=iso, 국가=r.country, **{f"CIP 백분위 {t0}": a.loc[iso, "cip_pct"], f"CIP 백분위 {L}": r.cip_pct},
                                 변화=r.cip_pct - a.loc[iso, "cip_pct"],
                                 **{"1인당 GDP 연평균 성장(%)": ((g1 / g0) ** (1 / (L - t0)) - 1) * 100 if pd.notna(g0) and pd.notna(g1) else np.nan},
                                 **{"MVA/GDP 변화(p)": (r.mva_gdp - a.loc[iso, "mva_gdp"]) if "mva_gdp" in a and pd.notna(r.get("mva_gdp")) and pd.notna(a.loc[iso, "mva_gdp"]) else np.nan}))
        tc = pd.DataFrame(rows)
        if len(tc):
            med_g = tc["1인당 GDP 연평균 성장(%)"].median()
            tc["판정"] = np.where((tc["변화"] <= 0) & (tc["1인당 GDP 연평균 성장(%)"] < med_g), "정체 후보",
                                 np.where(tc["변화"] > 5, "고도화 진행", "중간"))
            T["mic_table"] = tc.sort_values("변화").set_index("ISO3")
            facts.update(t0=t0, n_trap=int((tc["판정"] == "정체 후보").sum()), n_up=int((tc["판정"] == "고도화 진행").sum()), n_tc=len(tc))
    # Korea + MIC peers paths
    fig = go.Figure()
    peers = [p for p in ["KOR", "MYS", "THA", "BRA", "MEX", "CHN"] if p in set(s.iso3)]
    for i, p in enumerate(peers):
        z = s[s.iso3 == p].sort_values("year")
        fig.add_trace(go.Scatter(x=z.gdppc_ppp, y=z.cip_pct, mode="lines+markers", name=z.country.iloc[0],
                                 line=dict(color=SERIES[i], width=3 if p == kor else 2), marker=dict(size=4),
                                 text=z.year, hovertemplate="%{text}: 소득 %{x:,.0f} / CIP 백분위 %{y:.0f}<extra></extra>"))
    F["paths"] = style(fig, "소득 증가와 CIP 백분위의 경로", 420)
    F["paths"].update_xaxes(type="log", title="1인당 GDP (로그축)").update_yaxes(title="CIP 백분위")
    return dict(tables=T, figs=F, facts=facts)


# ---------------------------------------------------------------- 4. policy evaluation
def policy(df, kor="KOR"):
    T, F, facts = {}, {}, {}
    xs = [c for c in ["fdi_gdp", "trade_gdp", "gcf_gdp", "rd_gdp"] if c in df and df[c].notna().sum() > 200]
    if "gdppc_ppp" not in df or not xs:
        return dict(tables=T, figs=F, facts=dict(skipped="정책 변수(FDI, 개방도 등)가 없어 이 분석은 건너뛰었습니다."))
    d = df.sort_values(["iso3", "year"]).copy()
    d["lngdp"] = np.log(d.gdppc_ppp)
    reg = ["lngdp"] + xs
    for c in reg:
        d[f"l_{c}"] = d.groupby("iso3")[c].shift(1)
    labels = {"l_lngdp": "ln 1인당 GDP(t-1)", "l_fdi_gdp": "FDI 순유입/GDP(t-1)", "l_trade_gdp": "무역개방도(t-1)",
              "l_gcf_gdp": "총자본형성/GDP(t-1)", "l_rd_gdp": "R&D/GDP(t-1)"}
    out = []
    for spec, cols in (("(1) 기본", [f"l_{c}" for c in reg if c != "rd_gdp"]), ("(2) R&D 추가", [f"l_{c}" for c in reg])):
        cols = [c for c in cols if c in d]
        if spec.startswith("(2)") and "l_rd_gdp" not in cols:
            continue
        z = d.dropna(subset=["cip"] + cols).set_index(["iso3", "year"])
        if len(z) < 150 or z.index.get_level_values(0).nunique() < 30:
            continue
        m = PanelOLS(z["cip"], z[cols], entity_effects=True, time_effects=True, drop_absorbed=True).fit(cov_type="clustered", cluster_entity=True)
        ci = m.conf_int()
        for c in m.params.index:
            out.append(dict(모형=spec, 변수=labels.get(c, c), 계수=m.params[c], 표준오차=m.std_errors[c], p값=m.pvalues[c],
                            하한=ci.loc[c, "lower"], 상한=ci.loc[c, "upper"], N=int(m.nobs), 국가수=int(m.entity_info["total"]),
                            within_R2=float(m.rsquared_within)))
    if out:
        R = pd.DataFrame(out)
        T["fe_regression"] = R[["모형", "변수", "계수", "표준오차", "p값", "N", "국가수", "within_R2"]].set_index(["모형", "변수"])
        fig = go.Figure()
        for i, (spec, g) in enumerate(R.groupby("모형")):
            fig.add_trace(go.Scatter(x=g.계수, y=g.변수, mode="markers", name=spec, marker=dict(size=9, color=SERIES[i], line=dict(color="white", width=1.5)),
                                     error_x=dict(type="data", symmetric=False, array=g.상한 - g.계수, arrayminus=g.계수 - g.하한, color=SERIES[i], thickness=1.5),
                                     hovertemplate="%{y}: %{x:.4f}<extra>" + spec + "</extra>"))
        fig.add_vline(x=0, line=dict(color=INK2, width=1))
        F["fe_coef"] = style(fig, "국가·연도 고정효과 패널회귀 계수 (95% 신뢰구간, 국가 클러스터 표준오차)", 400)
        F["fe_coef"].update_yaxes(autorange="reversed")
        F["fe_coef"].update_xaxes(title="CIP 점수에 대한 한계효과(단위 변화당)")
        facts["fe_rows"] = R.to_dict("records")
    # 2018 shock: descriptive pre/post by income group
    s = df.dropna(subset=["cip"])
    if s.year.min() <= 2013 and s.year.max() >= 2019 and s.income_ko.notna().any():
        base = 2017
        idx = s.assign(v=s.cip).groupby(["income_ko", "year"])["v"].median().unstack(0)
        idx = idx.reindex(columns=[c for c in INCOME_ORDER if c in idx]).dropna(how="all")
        idxn = idx / idx.loc[base] * 100 if base in idx.index else idx
        fig = go.Figure()
        for i, c in enumerate(idxn.columns):
            fig.add_trace(go.Scatter(x=idxn.index, y=idxn[c], name=c, mode="lines", line=dict(color=SERIES[i], width=2.5)))
        fig.add_vline(x=2018, line=dict(color=INK2, dash="dot"), annotation_text="2018", annotation_font_color=INK2)
        F["index_group"] = style(fig, "소득군별 CIP 중위수 (2017=100)", 400)
        pre = s[(s.year >= 2013) & (s.year <= 2017)]
        post = s[s.year >= 2018]
        def ann(x):
            x = x.sort_values("year")
            return (np.log(x.cip.iloc[-1]) - np.log(x.cip.iloc[0])) / max(1, x.year.iloc[-1] - x.year.iloc[0]) * 100 if len(x) > 1 and (x.cip > 0).all() else np.nan
        pr = pre.groupby("iso3").apply(ann, include_groups=False).rename("pre")
        po = post.groupby("iso3").apply(ann, include_groups=False).rename("post")
        g = pd.concat([pr, po], axis=1).join(s.drop_duplicates("iso3").set_index("iso3")[["income_ko", "country"]]).dropna(subset=["pre", "post"])
        tab = g.groupby("income_ko")[["pre", "post"]].median().reindex(INCOME_ORDER).dropna(how="all")
        tab["차이"] = tab.post - tab.pre
        tab["국가 수"] = g.groupby("income_ko").size()
        tab.columns = ["2013–17 연평균 증가율(%) 중위수", "2018 이후 연평균 증가율(%) 중위수", "차이(p)", "국가 수"]
        T["prepost"] = tab
        if kor in g.index:
            facts.update(kor_pre=float(g.loc[kor, "pre"]), kor_post=float(g.loc[kor, "post"]))
        facts["prepost_ok"] = True
    return dict(tables=T, figs=F, facts=facts)


# ---------------------------------------------------------------- 5. GVC complement
def gvc(df, kor="KOR", tiva=None):
    T, F, facts = {}, {}, {}
    s = df.copy()
    if {"mxpc", "mvapc"} <= set(s):
        s["xva"] = s.mxpc / s.mvapc  # manufactured exports per $ of manufacturing value added
    if {"imwmt", "imwmva"} <= set(s):
        s["xva_share"] = s.imwmt / s.imwmva  # world export share / world MVA share
    key = "xva" if "xva" in s else "xva_share" if "xva_share" in s else None
    if key is None:
        return dict(tables=T, figs=F, facts=dict(skipped="수출·부가가치 하위지표가 없어 GVC 보완 지표를 만들 수 없습니다."))
    s = s.replace([np.inf, -np.inf], np.nan).dropna(subset=[key, "cip"])
    L = int(s.year.max())
    lat = s[s.year == L].copy()
    lat = lat[lat[key] > 0]
    lab = {"xva": "제조업 수출 / 제조업 부가가치 (1인당 기준 배율)", "xva_share": "세계 수출 점유율 ÷ 세계 MVA 점유율"}[key]
    facts.update(key=key, label=lab, latest=L)
    q_hi = lat[key].quantile(0.9)
    top = lat.nlargest(10, key)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=lat.cip, y=lat[key], mode="markers", name="국가", text=lat.country, marker=dict(size=8, color=BLUES[2], line=dict(color="white", width=1.2)),
                             hovertemplate="%{text}<br>CIP %{x:.3f} / 배율 %{y:.2f}<extra></extra>"))
    k = lat[lat.iso3 == kor]
    if len(k):
        fig.add_trace(go.Scatter(x=k.cip, y=k[key], mode="markers+text", text=["한국"], textposition="top center", name="한국",
                                 marker=dict(size=13, color=SERIES[1], line=dict(color="white", width=2))))
        facts["kor_ratio"] = float(k[key].iloc[0])
        facts["kor_ratio_pct"] = float((lat[key] < k[key].iloc[0]).mean() * 100)
    F["scatter"] = style(fig, f"CIP와 수출-부가가치 배율 ({L}년)", 460)
    F["scatter"].update_yaxes(type="log", title=lab).update_xaxes(title="CIP 점수")
    t = top[["country", "iso3", "cip", key]].copy()
    t.columns = ["국가", "ISO3", "CIP", "배율"]
    T["top_ratio"] = t.set_index("ISO3")
    fig = go.Figure()
    peers = [p for p in PEERS if p in set(s.iso3)]
    for i, p in enumerate(peers):
        z = s[s.iso3 == p]
        fig.add_trace(go.Scatter(x=z.year, y=z[key], name=z.country.iloc[0], mode="lines", line=dict(color=SERIES[i], width=3 if p == kor else 2)))
    F["trend"] = style(fig, "수출-부가가치 배율 추이", 380)
    F["trend"].update_yaxes(title="배율")
    facts["q_hi"] = float(q_hi)
    if tiva is not None and len(tiva):
        tv = tiva.copy()
        col = [c for c in tv.columns if c not in ("iso3", "year")][0]
        z = lat.merge(tv[tv.year == tv.year.max()][["iso3", col]], on="iso3")
        if len(z) > 15:
            fig = go.Figure(go.Scatter(x=z.cip, y=z[col], mode="markers", text=z.country, marker=dict(size=8, color=SERIES[2], line=dict(color="white", width=1.2))))
            F["tiva"] = style(fig, f"CIP와 TiVA 지표 ({col})", 420, legend=False)
            facts["tiva_col"] = col
    return dict(tables=T, figs=F, facts=facts)


def run_all(df, kor="KOR", tiva=None):
    return dict(descriptive=descriptive(df, kor), upgrading=upgrading(df, kor), mit=mit(df, kor), policy=policy(df, kor), gvc=gvc(df, kor, tiva))
