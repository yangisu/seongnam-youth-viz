"""4단 분석 시각화 통합. 각 함수는 독립 호출 가능하며 HTML/PNG 산출물을 저장한다.

핵심 함수:
  - make_youth_choropleth(df, geojson_path, output_path) -> folium.Map
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GEOJSON, OUT_HTML, PROCESSED  # noqa: E402


def _load_geojson(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _detect_dong_property(geojson: dict, sample_dong: str) -> str:
    """GeoJSON properties 중 행정동명을 담은 키를 찾는다."""
    if not geojson["features"]:
        raise ValueError("GeoJSON에 features 없음")
    props = geojson["features"][0]["properties"]
    candidates = ["adm_nm", "ADM_NM", "EMD_KOR_NM", "EMD_NM", "동명", "DONG_NM", "name"]
    for k in candidates:
        if k in props:
            return k
    # fallback: 첫 번째 문자열 속성
    for k, v in props.items():
        if isinstance(v, str):
            return k
    raise ValueError(f"행정동명 키를 찾을 수 없음. properties={list(props.keys())}")


def make_youth_choropleth(
    df: pd.DataFrame,
    geojson_path: Path | str,
    output_path: Optional[Path | str] = None,
    value_col: str = "청년_순유출률",
    dong_col: str = "dong",
) -> "folium.Map":  # noqa: F821
    """행정동별 청년 순유출률 Choropleth.

    Args:
        df: ['dong', value_col, '청년_전입', '청년_전출', '청년_인구'] 포함
        geojson_path: 성남시 행정동 경계 GeoJSON
        output_path: 저장할 HTML 경로. None이면 저장 안 함.
        value_col: 색상 인코딩에 쓸 컬럼 (기본: 청년_순유출률, +면 유출, -면 유입)
        dong_col: df의 동명 컬럼

    Returns:
        folium.Map 객체. 컬러맵은 RdBu_r (빨강=유출, 파랑=유입), 0 기준 대칭.
    """
    import branca.colormap as cm
    import folium

    geo = _load_geojson(Path(geojson_path))
    geo_dong_key = _detect_dong_property(geo, sample_dong=df[dong_col].iloc[0])

    # 동명 정규화: 공백 제거 + '성남시 X구 Y동' → 'Y동'
    def _norm(s: str) -> str:
        s = str(s).strip()
        return s.split()[-1] if " " in s else s

    df = df.copy()
    df["_dong_norm"] = df[dong_col].map(_norm)
    value_map = dict(zip(df["_dong_norm"], df[value_col]))

    # GeoJSON properties에 값 주입
    for feat in geo["features"]:
        raw = feat["properties"].get(geo_dong_key, "")
        norm = _norm(raw)
        feat["properties"]["_dong_norm"] = norm
        v = value_map.get(norm)
        feat["properties"][value_col] = float(v) if v is not None and pd.notna(v) else None

    # 0 기준 대칭 컬러맵
    series = pd.Series(list(value_map.values())).dropna()
    if len(series) == 0:
        vmax = 1.0
    else:
        vmax = max(abs(series.min()), abs(series.max()))
    colormap = cm.LinearColormap(
        colors=["#2166ac", "#67a9cf", "#f7f7f7", "#ef8a62", "#b2182b"],
        vmin=-vmax, vmax=vmax,
        caption=f"{value_col} (%) — 양수=유출 / 음수=유입",
    )

    # 성남시 중심 좌표 근사
    m = folium.Map(location=[37.42, 127.13], zoom_start=12, tiles="cartodbpositron")

    def _style(feature):
        v = feature["properties"].get(value_col)
        return {
            "fillColor": colormap(v) if v is not None else "#cccccc",
            "color": "white",
            "weight": 0.5,
            "fillOpacity": 0.78 if v is not None else 0.3,
        }

    tooltip_fields = ["_dong_norm", value_col]
    tooltip_aliases = ["행정동", value_col]
    # df에 부가 컬럼이 있으면 툴팁 보강
    extra_cols = [c for c in ("청년_전입", "청년_전출", "청년_인구") if c in df.columns]
    if extra_cols:
        extra_map = {row["_dong_norm"]: row for _, row in df.iterrows()}
        for feat in geo["features"]:
            d = feat["properties"]["_dong_norm"]
            if d in extra_map:
                for c in extra_cols:
                    feat["properties"][c] = float(extra_map[d][c]) if pd.notna(extra_map[d][c]) else None
        tooltip_fields += extra_cols
        tooltip_aliases += extra_cols

    folium.GeoJson(
        geo,
        name="청년 순유출률",
        style_function=_style,
        tooltip=folium.GeoJsonTooltip(
            fields=tooltip_fields, aliases=tooltip_aliases, localize=True, sticky=True
        ),
    ).add_to(m)
    colormap.add_to(m)
    folium.LayerControl().add_to(m)

    if output_path:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        m.save(str(output_path))
        print(f"[저장] {output_path}")
    return m


def make_sgg_choropleth(
    sgg_df: pd.DataFrame,
    geojson_path: Path | str,
    output_path: Optional[Path | str] = None,
) -> "folium.Map":  # noqa: F821
    """성남 시군구(분당/수정/중원) 단위 청년 순유출 Choropleth.

    Args:
        sgg_df: ['sgg', '청년_전입', '청년_전출', '청년_순유출'] 포함
        geojson_path: 성남 행정동 GeoJSON (sggnm property로 시군구 집계)
    """
    import branca.colormap as cm
    import folium

    geo = _load_geojson(Path(geojson_path))
    # GeoJSON property 이름 자동 탐지: sgg/sggnm가 보통 들어있음
    sgg_key = None
    sample_props = geo["features"][0]["properties"]
    for k in ["sggnm", "sgg", "SGG_NM", "SGG_KOR_NM"]:
        if k in sample_props:
            sgg_key = k
            break
    if not sgg_key:
        raise ValueError(f"GeoJSON에 시군구명 키 없음: {list(sample_props.keys())}")

    # 정규화: 공백 제거 후 마지막 '구'만 추출 (분당구/수정구/중원구)
    def _norm_sgg(s: str) -> str:
        s = str(s).replace(" ", "")
        for gu in ("분당구", "수정구", "중원구"):
            if s.endswith(gu):
                return gu
        return s

    sgg_df = sgg_df.copy()
    sgg_df["_sgg_norm"] = sgg_df["sgg"].apply(_norm_sgg)
    val_map = dict(zip(sgg_df["_sgg_norm"], sgg_df["청년_순유출"]))
    in_map = dict(zip(sgg_df["_sgg_norm"], sgg_df["청년_전입"]))
    out_map = dict(zip(sgg_df["_sgg_norm"], sgg_df["청년_전출"]))

    for feat in geo["features"]:
        sgg_raw = feat["properties"].get(sgg_key, "")
        sgg_norm = _norm_sgg(sgg_raw)
        feat["properties"]["_sgg_norm"] = sgg_norm
        feat["properties"]["청년_순유출"] = float(val_map.get(sgg_norm, 0))
        feat["properties"]["청년_전입"] = int(in_map.get(sgg_norm, 0))
        feat["properties"]["청년_전출"] = int(out_map.get(sgg_norm, 0))

    vmax = max(abs(v) for v in val_map.values())
    colormap = cm.LinearColormap(
        colors=["#2166ac", "#67a9cf", "#f7f7f7", "#ef8a62", "#b2182b"],
        vmin=-vmax, vmax=vmax,
        caption="청년(20-34) 순유출 명 — 양수=유출 / 음수=유입 (2024년 합)",
    )

    m = folium.Map(location=[37.42, 127.13], zoom_start=12, tiles="cartodbpositron")

    def _style(feature):
        v = feature["properties"].get("청년_순유출", 0)
        return {
            "fillColor": colormap(v),
            "color": "white", "weight": 0.6, "fillOpacity": 0.78,
        }

    folium.GeoJson(
        geo, name="청년 순유출 (시군구)",
        style_function=_style,
        tooltip=folium.GeoJsonTooltip(
            fields=["adm_nm", "_sgg_norm", "청년_전입", "청년_전출", "청년_순유출"],
            aliases=["행정동", "시군구", "청년 전입", "청년 전출", "청년 순유출"],
            localize=True, sticky=True,
        ),
    ).add_to(m)
    colormap.add_to(m)
    folium.LayerControl().add_to(m)

    if output_path:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        m.save(str(output_path))
        print(f"[저장] {output_path}")
    return m


def build_choropleth_from_processed() -> None:
    geojson_files = list(GEOJSON.glob("*.geojson"))
    geojson_files = [g for g in geojson_files if "seongnam" in g.name.lower()]
    if not geojson_files:
        print("[건너뜀] data/geojson에 seongnam_admdong.geojson 없음")
        return
    geo = geojson_files[0]

    # 1) 시군구 단위 (Phase A)
    sgg_src = PROCESSED / "youth_migration_by_sgg.csv"
    if sgg_src.exists():
        sgg_df = pd.read_csv(sgg_src)
        make_sgg_choropleth(sgg_df, geo, OUT_HTML / "01_sgg_choropleth.html")

    # 2) 동 단위 (Phase B)
    dong_src = PROCESSED / "youth_migration_by_dong.csv"
    if dong_src.exists():
        dong_df = pd.read_csv(dong_src)
        # 2024년 6개월 데이터로 만들었으므로 라벨 명시
        if "청년_순유출률" in dong_df.columns and dong_df["청년_순유출률"].abs().sum() > 0:
            make_youth_choropleth(
                dong_df, geo, OUT_HTML / "01_dong_choropleth.html",
                value_col="청년_순유출률", dong_col="dong",
            )


def make_sankey(
    od_df: pd.DataFrame,
    output_path: Path | str,
    title: str = "성남 청년 이동 흐름",
    top_n_dest: int = 25,
    min_flow: int = 30,
) -> None:
    """동→외부 시군구 Sankey. plotly 사용.

    Args:
        od_df: ['origin_dong','dest_sido','dest_sgg','n'] 또는 호환
        top_n_dest: 도착지 시군구 상위 N개만 표시 (가독성)
        min_flow: 이 미만 흐름은 컷
    """
    import plotly.graph_objects as go

    df = od_df.copy()
    # 도착지 라벨: '경기 수원시 권선구' 형식 단축
    if "dest_sido" in df.columns and "dest_sgg" in df.columns:
        df["dest"] = df["dest_sido"].str.replace("특별자치도|특별자치시|특별시|광역시|도", "", regex=True).str.strip() + " " + df["dest_sgg"]
    elif "dest_sgg" in df.columns:
        df["dest"] = df["dest_sgg"]
    elif "dest_dong" in df.columns:
        df["dest"] = df["dest_dong"]

    # 상위 도착지만 유지
    top_dests = df.groupby("dest")["n"].sum().nlargest(top_n_dest).index
    df = df[df["dest"].isin(top_dests) & (df["n"] >= min_flow)]
    if df.empty:
        print(f"[건너뜀] Sankey: 흐름 부족 (min_flow={min_flow})")
        return

    origins = df["origin_dong"].unique().tolist()
    dests = df["dest"].unique().tolist()
    nodes = origins + dests
    node_idx = {n: i for i, n in enumerate(nodes)}

    # 색상: 분당구 동은 파랑, 수정구 빨강, 중원구 녹색, 외부 회색
    BUNDANG = {"분당동","수내1동","수내2동","수내3동","정자동","정자1동","정자2동","정자3동",
               "이매1동","이매2동","서현1동","서현2동","야탑1동","야탑2동","야탑3동",
               "금곡동","구미동","구미1동","판교동","삼평동","백현동","운중동"}
    SUJEONG = {"신흥1동","신흥2동","신흥3동","태평1동","태평2동","태평3동","태평4동",
               "수진1동","수진2동","단대동","산성동","양지동","복정동","위례동",
               "신촌동","고등동","시흥동"}
    JUNGWON = {"성남동","금광1동","금광2동","은행1동","은행2동","상대원1동","상대원2동",
               "상대원3동","중앙동","도촌동","여수동","하대원동"}
    def _color(n: str) -> str:
        if n in BUNDANG: return "rgba(31,119,180,0.85)"
        if n in SUJEONG: return "rgba(214,39,40,0.85)"
        if n in JUNGWON: return "rgba(44,160,44,0.85)"
        return "rgba(140,140,140,0.6)"

    fig = go.Figure(go.Sankey(
        node=dict(label=nodes, pad=10, thickness=14, color=[_color(n) for n in nodes]),
        link=dict(
            source=[node_idx[o] for o in df["origin_dong"]],
            target=[node_idx[d] for d in df["dest"]],
            value=df["n"].astype(float).tolist(),
            color="rgba(120,120,120,0.25)",
        )
    ))
    fig.update_layout(
        title_text=f"{title} (TOP {top_n_dest} 도착지, min={min_flow}명)",
        font=dict(family="Malgun Gothic, NanumGothic", size=11),
        height=900,
    )
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(output_path), include_plotlyjs="cdn")
    print(f"[저장] {output_path}")


def make_monthly_lines(
    monthly_df: pd.DataFrame,
    output_path: Path | str,
    group_col: str = "sgg",
    title: str = "월별 청년 순이동 추이",
) -> None:
    """월별 trend 라인차트."""
    import plotly.express as px
    df = monthly_df.copy()
    df["month"] = pd.to_datetime(df["statsYm"], format="%Y%m")
    fig = px.line(df, x="month", y="순이동", color=group_col, markers=True,
                  title=title, labels={"순이동": "청년 순이동 (전입-전출)", "month": "월"})
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(font=dict(family="Malgun Gothic, NanumGothic"), height=500,
                      hovermode="x unified")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(output_path), include_plotlyjs="cdn")
    print(f"[저장] {output_path}")


def make_top_dongs_monthly(monthly_dong_df: pd.DataFrame, output_path: Path | str) -> None:
    """유입 TOP/유출 TOP 동만 골라 시계열."""
    df = monthly_dong_df.copy()
    df["month"] = pd.to_datetime(df["statsYm"], format="%Y%m")
    annual = df.groupby("dong")["순이동"].sum().sort_values()
    spotlight = list(annual.head(5).index) + list(annual.tail(5).index)  # 유입 5 + 유출 5
    sub = df[df["dong"].isin(spotlight)].copy()

    import plotly.express as px
    fig = px.line(sub, x="month", y="순이동", color="dong", markers=True,
                  title="청년 순이동 — 핫스팟 동 (유입 TOP5 + 유출 TOP5)",
                  labels={"순이동": "청년 순이동", "month": "월"})
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_layout(font=dict(family="Malgun Gothic, NanumGothic"), height=600,
                      hovermode="x unified")
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(output_path), include_plotlyjs="cdn")
    print(f"[저장] {output_path}")


def build_all_visualizations() -> None:
    """모든 시각화 일괄 생성."""
    # 1단 Choropleth
    build_choropleth_from_processed()

    # 2단 Sankey (외부 흐름)
    od_out = PROCESSED / "od_youth_seongnam_dong_to_outside.csv"
    if od_out.exists():
        df = pd.read_csv(od_out)
        make_sankey(df, OUT_HTML / "02_sankey_outflow.html",
                    title="성남 청년 OUTFLOW: 동 → 외부 시군구")

    od_in = PROCESSED / "od_youth_seongnam_dong_inflow.csv"
    if od_in.exists():
        df = pd.read_csv(od_in)
        # 역방향: rename for sankey compatibility
        df2 = df.rename(columns={
            "origin_sido": "_dest_sido_x", "origin_sgg": "origin_dong",
            "dest_dong": "_dest"
        })
        df2["origin_dong"] = df["origin_sido"].str.replace("특별자치도|특별자치시|특별시|광역시|도","",regex=True).str.strip() + " " + df["origin_sgg"]
        df2["dest"] = df["dest_dong"]
        # 그냥 dest_dong을 도착지로 새 sankey
        import plotly.graph_objects as go
        sub = df2.nlargest(120, "n")
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
                color="rgba(31,119,180,0.3)",
            )
        ))
        fig.update_layout(title_text="성남 청년 INFLOW: 외부 시군구 → 동 (TOP 120 흐름)",
                          font=dict(family="Malgun Gothic, NanumGothic"), height=900)
        out = OUT_HTML / "02_sankey_inflow.html"
        fig.write_html(str(out), include_plotlyjs="cdn")
        print(f"[저장] {out}")

    # 시계열
    monthly_sgg = PROCESSED / "od_youth_monthly_sgg.csv"
    if monthly_sgg.exists():
        df = pd.read_csv(monthly_sgg)
        make_monthly_lines(df, OUT_HTML / "03_monthly_sgg.html", group_col="sgg",
                           title="성남 시군구별 월별 청년 순이동 (2024)")

    monthly_dong = PROCESSED / "od_youth_monthly_dong.csv"
    if monthly_dong.exists():
        df = pd.read_csv(monthly_dong)
        make_top_dongs_monthly(df, OUT_HTML / "03_monthly_dong_hotspots.html")


def main() -> None:
    build_all_visualizations()


if __name__ == "__main__":
    main()
