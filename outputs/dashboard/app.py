"""성남시 청년 양극화 대시보드 — Streamlit.

실행: streamlit run outputs/dashboard/app.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import folium
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

ROOT = Path(__file__).resolve().parent.parent.parent
PROCESSED = ROOT / "data" / "processed"
GEOJSON = ROOT / "data" / "geojson" / "seongnam_admdong.geojson"
OUT_HTML = ROOT / "outputs" / "interactive"

st.set_page_config(
    page_title="판교의 빛은 식었다 — 성남 청년 양극화",
    layout="wide",
)

st.title("판교의 빛은 식었다")
st.subheader("성남 청년 양극화 — 신축 vs 노후 단지의 분수령")
st.caption("데이터: 행정안전부 인구이동(2024) + 행정동 성·연령별 인구 (data.go.kr)")


# ──────────────────────────────────────────────────────────────
@st.cache_data
def load_dong():
    return pd.read_csv(PROCESSED / "youth_migration_by_dong.csv")


@st.cache_data
def load_sgg():
    return pd.read_csv(PROCESSED / "youth_migration_by_sgg.csv")


@st.cache_data
def load_monthly_sgg():
    df = pd.read_csv(PROCESSED / "od_youth_monthly_sgg.csv")
    df["month"] = pd.to_datetime(df["statsYm"], format="%Y%m")
    return df


@st.cache_data
def load_monthly_dong():
    df = pd.read_csv(PROCESSED / "od_youth_monthly_dong.csv")
    df["month"] = pd.to_datetime(df["statsYm"], format="%Y%m")
    return df


@st.cache_data
def load_od_out():
    return pd.read_csv(PROCESSED / "od_youth_seongnam_dong_to_outside.csv")


@st.cache_data
def load_geojson():
    with open(GEOJSON, encoding="utf-8") as f:
        return json.load(f)


dong = load_dong()
sgg = load_sgg()
monthly_sgg = load_monthly_sgg()
monthly_dong = load_monthly_dong()
od_out = load_od_out()
geo = load_geojson()


# 사이드바 —
st.sidebar.header("필터")
all_dongs = sorted(dong["dong"].dropna().unique())
spotlight = st.sidebar.selectbox(
    "스포트라이트 동",
    options=["(없음)"] + all_dongs,
    help="선택 시 해당 동의 시계열·OD가 강조됩니다.",
)

# 메트릭 ─────────────────────────────────────────
col1, col2, col3, col4 = st.columns(4)
total_in = int(sgg["청년_전입"].sum())
total_out = int(sgg["청년_전출"].sum())
col1.metric("청년 전입 (2024)", f"{total_in:,}")
col2.metric("청년 전출 (2024)", f"{total_out:,}")
col3.metric("성남 전체 net", f"{total_in - total_out:+,}")
top_outflow = dong.iloc[0]
col4.metric(
    f"최대 유출동: {top_outflow['dong']}",
    f"{top_outflow['청년_순유출률']:+.2f}%",
)

st.divider()

# 1단 ─────────────────────────────────────────
st.header("① 어디서 빠지고 어디로 모이나 (동별 청년 순유출률)")

tab_dong, tab_sgg = st.tabs(["동 단위 (49개)", "시군구 단위 (3구)"])

with tab_dong:
    st.markdown(
        "🔴 **빨강** = 청년 유출 / 🔵 **파랑** = 청년 유입. "
        "동그라미 호버하면 수치가 뜹니다."
    )
    # Folium choropleth
    import branca.colormap as cm

    vmax = float(dong["청년_순유출률"].abs().max())
    cmap = cm.LinearColormap(
        ["#2166ac", "#67a9cf", "#f7f7f7", "#ef8a62", "#b2182b"],
        vmin=-vmax, vmax=vmax,
        caption="청년(20-34) 순유출률 % — 양수=유출",
    )
    val_map = dict(zip(dong["dong"], dong["청년_순유출률"]))
    extra_in = dict(zip(dong["dong"], dong["청년_전입"]))
    extra_out = dict(zip(dong["dong"], dong["청년_전출"]))
    extra_pop = dict(zip(dong["dong"], dong["청년_인구"]))

    g = dict(geo)
    for feat in g["features"]:
        nm = feat["properties"].get("adm_nm", "").split()[-1]
        v = val_map.get(nm)
        feat["properties"]["dong"] = nm
        feat["properties"]["순유출률(%)"] = round(float(v), 2) if v is not None else None
        feat["properties"]["청년 전입"] = int(extra_in.get(nm, 0))
        feat["properties"]["청년 전출"] = int(extra_out.get(nm, 0))
        feat["properties"]["청년 인구"] = int(extra_pop.get(nm, 0))

    m = folium.Map(location=[37.43, 127.13], zoom_start=12, tiles="cartodbpositron")

    def style(feat):
        v = feat["properties"].get("순유출률(%)")
        return {
            "fillColor": cmap(v) if v is not None else "#cccccc",
            "color": "white" if feat["properties"]["dong"] != spotlight else "black",
            "weight": 0.5 if feat["properties"]["dong"] != spotlight else 3,
            "fillOpacity": 0.85 if v is not None else 0.3,
        }

    folium.GeoJson(
        g,
        style_function=style,
        tooltip=folium.GeoJsonTooltip(
            fields=["dong", "순유출률(%)", "청년 전입", "청년 전출", "청년 인구"],
            aliases=["동", "순유출률(%)", "청년 전입", "청년 전출", "청년 인구"],
            sticky=True,
        ),
    ).add_to(m)
    cmap.add_to(m)
    st_folium(m, width=None, height=600, returned_objects=[])

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("🔴 청년 유출 TOP 10")
        st.dataframe(
            dong.head(10)[["dong","청년_전입","청년_전출","청년_순이동_6m","청년_인구","청년_순유출률"]]
            .style.format({"청년_순유출률": "{:+.2f}%"}),
            use_container_width=True, hide_index=True,
        )
    with col_b:
        st.subheader("🔵 청년 유입 TOP 10")
        st.dataframe(
            dong.tail(10).iloc[::-1][["dong","청년_전입","청년_전출","청년_순이동_6m","청년_인구","청년_순유출률"]]
            .style.format({"청년_순유출률": "{:+.2f}%"}),
            use_container_width=True, hide_index=True,
        )

with tab_sgg:
    st.dataframe(sgg.style.format({c: "{:+,}" for c in ["청년_순이동","청년_순유출"]}),
                 use_container_width=True, hide_index=True)
    st.info(
        "시군구 단위 합산은 분당 -430 / 수정 +1108 / 중원 +99로 거의 평형. "
        "**진짜 양극화는 동 단위에서 드러난다.**"
    )

st.divider()

# 2단 ─────────────────────────────────────────
st.header("② 어디로 흘러갔나 — Sankey (동 → 외부 시군구)")
st.caption("선 굵기 = 흐름 인원. 분당구 동(파랑) / 수정구(빨강) / 중원구(초록).")

n_top = st.slider("표시 도착지 수 (TOP N)", 10, 60, 25)
min_n = st.slider("최소 흐름 (n명 이상)", 5, 100, 30)

sub = od_out.copy()
sub["dest"] = (
    sub["dest_sido"].str.replace("특별자치도|특별자치시|특별시|광역시|도", "", regex=True).str.strip()
    + " " + sub["dest_sgg"]
)
top_dests = sub.groupby("dest")["n"].sum().nlargest(n_top).index
sub = sub[sub["dest"].isin(top_dests) & (sub["n"] >= min_n)]

if spotlight != "(없음)":
    sub = sub[sub["origin_dong"] == spotlight]

origins = sub["origin_dong"].unique().tolist()
dests = sub["dest"].unique().tolist()
nodes = origins + dests
node_idx = {n: i for i, n in enumerate(nodes)}
fig = go.Figure(go.Sankey(
    node=dict(label=nodes, pad=10, thickness=14),
    link=dict(
        source=[node_idx[o] for o in sub["origin_dong"]],
        target=[node_idx[d] for d in sub["dest"]],
        value=sub["n"].astype(float).tolist(),
        color="rgba(120,120,120,0.3)",
    )
))
fig.update_layout(height=700, font=dict(family="Malgun Gothic, NanumGothic"))
st.plotly_chart(fig, use_container_width=True)

st.divider()

# 3단 ─────────────────────────────────────────
st.header("③ 시계열 — 월별 청년 순이동")

col_x, col_y = st.columns(2)
with col_x:
    st.subheader("시군구 단위 (3구)")
    fig = px.line(monthly_sgg, x="month", y="순이동", color="sgg", markers=True)
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(height=400, font=dict(family="Malgun Gothic, NanumGothic"),
                      hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

with col_y:
    st.subheader("핫스팟 동 (유입 TOP5 + 유출 TOP5)")
    annual = monthly_dong.groupby("dong")["순이동"].sum().sort_values()
    spotlight_set = list(annual.head(5).index) + list(annual.tail(5).index)
    if spotlight != "(없음)" and spotlight not in spotlight_set:
        spotlight_set.append(spotlight)
    sub_m = monthly_dong[monthly_dong["dong"].isin(spotlight_set)]
    fig = px.line(sub_m, x="month", y="순이동", color="dong", markers=True)
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(height=400, font=dict(family="Malgun Gothic, NanumGothic"),
                      hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

st.divider()

# 4단 자리 ─────────────────────────────────────────
st.header("④ 무엇을 떠나며 무엇이 남았나 (민원 + 경제) — 데이터 수집 중")
st.warning(
    "data.seongnam.go.kr 동별 민원 키워드는 사이트가 SPA로 자동 스크래핑이 어려움. "
    "수동으로 CSV 수집 후 `data/raw/seongnam_complaint/keywords.csv` 에 넣으면 자동으로 통합."
)

st.divider()

# narrative ─────────────────────────────────────────
with st.expander("📌 핵심 발견 (Narrative)"):
    st.markdown("""
**판교의 빛은 이미 식었다 — 성남 청년 양극화의 진짜 축은 '신축 vs 노후'**

- 분당 1세대 아파트(정자/수내/이매/분당동)에서도 청년이 **유출**
- 청년이 모이는 곳: 위례신도시, 신흥2동(재개발), 판교 운중·삼평
- 시군구 단위로는 안 보이지만 **동 단위에서 명확한 양극화**
- 통념과 달리 **수정구(특히 신흥2동 -14.7%)가 가장 강한 청년 유입**

데이터 출처:
- 행안부 지역별 인구이동 현황 (data.go.kr 15108093, 2024년 12개월)
- 행안부 행정동 성·연령별 인구 (data.go.kr 15097972, 2026.03 기준)
- 행정동 GeoJSON: [raqoon886/Local_HangJeongDong](https://github.com/raqoon886/Local_HangJeongDong)
""")
