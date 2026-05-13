from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from common import PROCESSED, ROOT

SITE_DIR = ROOT / "outputs" / "site"
SITE_DIR.mkdir(parents=True, exist_ok=True)
CHART_DATA_DIR = SITE_DIR / "chart_data"
CHART_DATA_DIR.mkdir(parents=True, exist_ok=True)
GEO_PATH = ROOT / "data" / "geojson" / "seongnam_admdong.geojson"

AXIS_NEW = {
    "신흥동",
    "위례동",
    "고등동",
    "운중동",
    "삼평동",
    "백현동",
    "판교동",
    "시흥동",
}
AXIS_OLD = {
    "태평동",
    "수진동",
    "상대원동",
    "은행동",
    "성남동",
    "금광동",
    "중앙동",
    "하대원동",
    "수내동",
    "이매동",
    "정자동",
    "야탑동",
    "구미동",
    "분당동",
}
AXIS_CONTEXT_EVIDENCE = [
    {
        "source": "Seongnam Youth Polarization _standalone_.html",
        "evidence_label": "유입 핫스팟 5",
        "evidence_text": "신축 / 재개발",
        "mapped_axis": "신축·재정비",
    },
    {
        "source": "Seongnam Youth Polarization _standalone_.html",
        "evidence_label": "유출 핫스팟 5",
        "evidence_text": "노후 / 분당 1세대",
        "mapped_axis": "노후·정체",
    },
]


def load_csv(name: str) -> pd.DataFrame:
    p = PROCESSED / name
    return pd.read_csv(p) if p.exists() else pd.DataFrame()


def load_json(name: str) -> dict:
    p = PROCESSED / name
    if not p.exists():
        return {}
    with p.open("r", encoding="utf-8") as f:
        return json.load(f)


def cluster_from_dong(d: str) -> str:
    if not d:
        return ""
    m = re.match(r"^(.+?)[1-4]동$", str(d))
    return f"{m.group(1)}동" if m else str(d)


def axis_type(cluster: str) -> str:
    if cluster in AXIS_NEW:
        return "신축·재정비"
    if cluster in AXIS_OLD:
        return "노후·정체"
    return "혼합/전이"


def build_geo_payload(dong_df: pd.DataFrame, pop_df: pd.DataFrame) -> dict:
    with GEO_PATH.open("r", encoding="utf-8") as f:
        geo = json.load(f)

    sgg_map = dict(zip(pop_df["dong"], pop_df["sgg"])) if not pop_df.empty else {}
    for feat in geo.get("features", []):
        nm = feat["properties"]["adm_nm"].split()[-1]
        feat["properties"]["dong"] = nm
        feat["properties"]["sgg_full"] = sgg_map.get(nm, "")
        cluster = cluster_from_dong(nm)
        feat["properties"]["dong_cluster"] = cluster
        feat["properties"]["axis_type"] = axis_type(cluster)

        row = dong_df[dong_df["dong"] == nm]
        if not row.empty:
            r = row.iloc[0]
            feat["properties"]["youth_pop"] = int(r["청년_인구"])
            feat["properties"]["youth_in"] = int(r["청년_전입"])
            feat["properties"]["youth_out"] = int(r["청년_전출"])
            feat["properties"]["net"] = int(r["청년_순이동_6m"])
            feat["properties"]["rate"] = float(round(r["청년_순유출률"], 2))
    return geo


def build_axis_complaint_findings(priority: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if priority.empty:
        return pd.DataFrame(), pd.DataFrame()

    axis_rows = priority.copy()
    axis_rows["axis_type"] = axis_rows["dong_cluster"].map(lambda x: axis_type(str(x)))
    for col in [
        "complaints_per_1000_totalpop",
        "youth_outflow_rate",
        "negative_month_share",
    ]:
        axis_rows[col] = pd.to_numeric(axis_rows[col], errors="coerce")
    axis_rows["negative_month_share_pct"] = axis_rows["negative_month_share"] * 100.0
    axis_rows["is_ab_tier"] = axis_rows["policy_tier"].isin(["A_즉시개입", "B_우선개입"])

    axis_points = axis_rows[
        [
            "dong_cluster",
            "axis_type",
            "policy_tier",
            "complaints_per_1000_totalpop",
            "youth_outflow_rate",
            "negative_month_share_pct",
            "is_ab_tier",
        ]
    ].copy()

    axis_summary = (
        axis_points.groupby("axis_type", dropna=False)
        .agg(
            cluster_count=("dong_cluster", "nunique"),
            mean_complaints_per_1000=("complaints_per_1000_totalpop", "mean"),
            median_complaints_per_1000=("complaints_per_1000_totalpop", "median"),
            mean_outflow_rate=("youth_outflow_rate", "mean"),
            mean_negative_month_share_pct=("negative_month_share_pct", "mean"),
            ab_tier_share_pct=("is_ab_tier", lambda s: float(s.mean()) * 100.0 if len(s) else 0.0),
        )
        .reset_index()
    )
    axis_order = pd.Categorical(
        axis_summary["axis_type"],
        categories=["신축·재정비", "노후·정체", "혼합/전이"],
        ordered=True,
    )
    axis_summary = axis_summary.assign(_axis_order=axis_order).sort_values("_axis_order").drop(columns="_axis_order")
    return axis_points, axis_summary


def build_iterative_loop_progress(iterative_corr: pd.DataFrame) -> pd.DataFrame:
    if iterative_corr.empty:
        return pd.DataFrame()

    corr = iterative_corr.copy()
    corr["iteration"] = pd.to_numeric(corr["iteration"], errors="coerce")
    corr["abs_spearman_r"] = pd.to_numeric(corr["abs_spearman_r"], errors="coerce")
    corr["spearman_r"] = pd.to_numeric(corr["spearman_r"], errors="coerce")
    corr["n"] = pd.to_numeric(corr["n"], errors="coerce")
    corr = corr.dropna(subset=["iteration", "abs_spearman_r"])
    if corr.empty:
        return pd.DataFrame()
    corr["iteration"] = corr["iteration"].astype(int)

    best_by_iter = corr.sort_values(
        ["iteration", "abs_spearman_r"],
        ascending=[True, False],
    ).drop_duplicates("iteration")
    tested_by_iter = corr.groupby("iteration", as_index=False).agg(features_tested=("feature", "nunique"))
    progress = tested_by_iter.merge(
        best_by_iter[["iteration", "feature", "stage", "n", "spearman_r", "abs_spearman_r"]],
        on="iteration",
        how="left",
    ).sort_values("iteration")
    progress["delta_from_prev"] = progress["abs_spearman_r"].diff()
    return progress.rename(
        columns={
            "feature": "best_feature",
            "stage": "best_stage",
            "n": "sample_n",
            "spearman_r": "best_spearman_r",
            "abs_spearman_r": "best_abs_spearman_r",
        }
    )


def build_payload() -> tuple[dict, dict[str, pd.DataFrame]]:
    youth_dong = load_csv("youth_migration_by_dong.csv")
    youth_sgg = load_csv("youth_migration_by_sgg.csv")
    pop = load_csv("youth_population_by_dong.csv")

    monthly_city = load_csv("monthly_city_series_2024.csv")
    cluster_month = load_csv("cluster_month_panel_2024.csv")
    monthly_assoc = load_csv("stats_monthly_association_2024.csv")
    horizon_assoc = load_csv("stats_horizon_association_2024.csv")
    horizon_points = load_csv("horizon_association_points_2024.csv")
    monthly_lag_cluster = load_csv("stats_monthly_lag_by_cluster_2024.csv")

    od_intra = load_csv("od_youth_intra_seongnam_dong.csv")
    od_intra_pairs = load_csv("od_intra_cluster_top_pairs_2024.csv")
    od_intra_matrix = load_csv("od_intra_cluster_matrix_top12_2024.csv")

    tests = load_csv("stats_outflow_complaint_tests_2024.csv")
    policy_relations = load_csv("stats_policy_relations_2024.csv")
    models = load_csv("stats_outflow_models_2024.csv")
    sensitivity = load_csv("stats_outflow_sensitivity_2024.csv")
    priority = load_csv("policy_priority_matrix_2024.csv")
    policy_newold_axis_map = load_csv("policy_newold_axis_mapping_by_cluster_2024.csv")
    policy_newold_group_comp = load_csv("policy_newold_group_comparison_2024.csv")
    policy_newold_topic_comp = load_csv("policy_newold_topic_group_comparison_2024.csv")
    outflow_rank = load_csv("youth_outflow_ranked.csv")
    quality = load_json("complaint_parse_quality_2024.json")
    criteria = load_json("policy_tier_criteria_2024.json")
    policy_summary = load_json("policy_focus_summary_2024.json")
    analysis_summary = load_json("analysis_summary_v2.json")
    iterative_summary = load_json("iterative_optimizer_summary_v2.json")
    iterative_corr = load_csv("iterative_feature_correlation_v2.csv")
    iterative_reco = load_csv("iterative_visualization_recommendations_v2.csv")
    axis_findings, axis_summary = build_axis_complaint_findings(priority)
    iterative_loop_progress = build_iterative_loop_progress(iterative_corr)
    axis_context_evidence = pd.DataFrame(AXIS_CONTEXT_EVIDENCE)

    if not policy_newold_axis_map.empty:
        axis_from_policy = policy_newold_axis_map.copy()
        axis_from_policy["axis_type"] = axis_from_policy.get("axis_group_label", axis_from_policy.get("axis_group", "혼합/전이"))
        for col in ["complaints_per_1000_totalpop", "youth_outflow_rate"]:
            axis_from_policy[col] = pd.to_numeric(axis_from_policy[col], errors="coerce")
        if not priority.empty and "policy_tier" in priority.columns:
            axis_from_policy = axis_from_policy.merge(
                priority[["dong_cluster", "policy_tier"]],
                on="dong_cluster",
                how="left",
            )
        if "policy_tier" not in axis_from_policy.columns:
            axis_from_policy["policy_tier"] = ""
        axis_from_policy["is_ab_tier"] = axis_from_policy["policy_tier"].isin(["A_즉시개입", "B_우선개입"])
        axis_findings = axis_from_policy[
            [
                "dong_cluster",
                "axis_type",
                "policy_tier",
                "complaints_per_1000_totalpop",
                "youth_outflow_rate",
                "is_ab_tier",
            ]
        ]

    if not policy_newold_group_comp.empty:
        axis_summary_from_policy = policy_newold_group_comp.copy()
        axis_summary_from_policy["axis_type"] = axis_summary_from_policy.get(
            "axis_group_label", axis_summary_from_policy.get("axis_group", "혼합/전이")
        )
        rename_map = {
            "complaints_per_1000_totalpop_mean": "mean_complaints_per_1000",
            "youth_outflow_rate_mean": "mean_outflow_rate",
            "cluster_count": "cluster_count",
        }
        axis_summary_from_policy = axis_summary_from_policy.rename(columns=rename_map)
        for col in ["cluster_count", "mean_complaints_per_1000", "mean_outflow_rate", "axis_group_order"]:
            if col in axis_summary_from_policy.columns:
                axis_summary_from_policy[col] = pd.to_numeric(axis_summary_from_policy[col], errors="coerce")
        axis_summary = axis_summary_from_policy[
            [c for c in ["axis_type", "cluster_count", "mean_complaints_per_1000", "mean_outflow_rate", "axis_group_order"] if c in axis_summary_from_policy.columns]
        ].copy()
        if "axis_group_order" in axis_summary.columns:
            axis_summary = axis_summary.sort_values("axis_group_order").drop(columns=["axis_group_order"])
        if not axis_findings.empty and "is_ab_tier" in axis_findings.columns:
            ab_share = (
                axis_findings.groupby("axis_type", dropna=False)["is_ab_tier"]
                .mean()
                .reset_index()
                .rename(columns={"is_ab_tier": "ab_tier_share_pct"})
            )
            ab_share["ab_tier_share_pct"] = ab_share["ab_tier_share_pct"] * 100.0
            axis_summary = axis_summary.merge(ab_share, on="axis_type", how="left")

    lag_points = pd.DataFrame()
    if not cluster_month.empty:
        tmp = cluster_month.sort_values(["dong_cluster", "month"]).copy()
        tmp["outflow_next"] = tmp.groupby("dong_cluster")["monthly_outflow_rate"].shift(-1)
        lag_points = tmp[
            [
                "dong_cluster",
                "month",
                "complaints_per_1000_totalpop_month",
                "outflow_next",
                "complaint_count",
            ]
        ].dropna()

    geo = build_geo_payload(youth_dong, pop)
    payload = {
        "geo": geo,
        "dong": youth_dong.to_dict(orient="records"),
        "sgg": youth_sgg.to_dict(orient="records"),
        "od_intra": od_intra.to_dict(orient="records"),
        "od_intra_pairs": od_intra_pairs.to_dict(orient="records"),
        "od_intra_matrix": od_intra_matrix.to_dict(orient="records"),
        "monthly_city": monthly_city.to_dict(orient="records"),
        "cluster_month": cluster_month.to_dict(orient="records"),
        "monthly_assoc": monthly_assoc.to_dict(orient="records"),
        "horizon_assoc": horizon_assoc.to_dict(orient="records"),
        "horizon_points": horizon_points.to_dict(orient="records"),
        "monthly_lag_cluster": monthly_lag_cluster.to_dict(orient="records"),
        "monthly_lag_points": lag_points.to_dict(orient="records"),
        "priority": priority.to_dict(orient="records"),
        "policy_newold_axis_map": policy_newold_axis_map.to_dict(orient="records"),
        "policy_newold_group_comp": policy_newold_group_comp.to_dict(orient="records"),
        "policy_newold_topic_comp": policy_newold_topic_comp.to_dict(orient="records"),
        "tests": tests.to_dict(orient="records"),
        "policy_relations": policy_relations.to_dict(orient="records"),
        "models": models.to_dict(orient="records"),
        "sensitivity": sensitivity.to_dict(orient="records"),
        "outflow_rank": outflow_rank.to_dict(orient="records"),
        "quality": quality,
        "criteria": criteria,
        "policy_summary": policy_summary,
        "analysis_summary": analysis_summary,
        "iterative_summary": iterative_summary,
        "iterative_corr": iterative_corr.to_dict(orient="records"),
        "iterative_reco": iterative_reco.to_dict(orient="records"),
        "axis_findings": axis_findings.to_dict(orient="records"),
        "axis_summary": axis_summary.to_dict(orient="records"),
        "axis_context_evidence": axis_context_evidence.to_dict(orient="records"),
        "iterative_loop_progress": iterative_loop_progress.to_dict(orient="records"),
        "summary": {
            "total_in": int(youth_sgg["청년_전입"].sum()) if not youth_sgg.empty else 0,
            "total_out": int(youth_sgg["청년_전출"].sum()) if not youth_sgg.empty else 0,
            "dong_count": int(len(youth_dong)),
            "youth_pop": int(pop["청년_인구"].sum()) if not pop.empty else 0,
        },
    }

    frames = {
        "chapter1_dong_metrics.csv": youth_dong,
        "chapter2_intra_cluster_pairs.csv": od_intra_pairs,
        "chapter2_intra_cluster_matrix_top12.csv": od_intra_matrix,
        "chapter3_monthly_city.csv": monthly_city,
        "chapter3_monthly_lag_points.csv": lag_points,
        "chapter3_monthly_assoc.csv": monthly_assoc,
        "chapter3_horizon_assoc.csv": horizon_assoc,
        "chapter3_horizon_points.csv": horizon_points,
        "chapter4_priority_matrix.csv": priority,
        "chapter4_policy_newold_axis_mapping.csv": policy_newold_axis_map,
        "chapter4_policy_newold_group_comparison.csv": policy_newold_group_comp,
        "chapter4_policy_newold_topic_group_comparison.csv": policy_newold_topic_comp,
        "chapter4_axis_complaint_findings.csv": axis_findings,
        "chapter4_axis_complaint_summary.csv": axis_summary,
        "chapter4_axis_context_evidence.csv": axis_context_evidence,
        "chapter4_cross_section_tests.csv": tests,
        "chapter4_policy_relations.csv": policy_relations,
        "chapter4_models.csv": models,
        "chapter4_sensitivity.csv": sensitivity,
        "chapter5_iterative_feature_correlation.csv": iterative_corr,
        "chapter5_iterative_loop_progress.csv": iterative_loop_progress,
        "chapter5_iterative_visualization_recommendations.csv": iterative_reco,
    }
    return payload, frames


def export_chart_data(frames: dict[str, pd.DataFrame]) -> None:
    for name, df in frames.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            df.to_csv(CHART_DATA_DIR / name, index=False, encoding="utf-8-sig")


def write_traceability_doc() -> None:
    content = """# Analysis Traceability (v2)

## Chapter 1 (WHAT: 동별 순유출 지형)
- What was analyzed:
  - Which dongs are net youth outflow hotspots vs net inflow zones.
- Data used:
  - `youth_migration_by_dong.csv`
  - `youth_population_by_dong.csv`
  - `seongnam_admdong.geojson`
- Processing:
  - `youth_outflow_rate = (youth_out - youth_in) / youth_pop * 100`
  - map join by dong name and metric attachment to each polygon.
- What result means:
  - Higher positive outflow-rate dongs indicate stronger youth retention pressure.
- Site outputs:
  - Choropleth + dong detail panel.
  - `outputs/site/chart_data/chapter1_dong_metrics.csv`

## Chapter 2 (WHERE: 성남 내부 재배치 경로)
- What was analyzed:
  - Where youth moves inside Seongnam (origin cluster -> destination cluster).
- Data used:
  - `od_youth_intra_seongnam_dong.csv`
- Processing:
  - Dong OD flows aggregated to cluster matrix.
  - Largest corridors extracted for rank view.
- What result means:
  - High-volume origin->destination pairs identify dominant in-city relocation channels.
- Site outputs:
  - Intra-cluster heatmap + top corridor table.
  - `outputs/site/chart_data/chapter2_intra_cluster_matrix_top12.csv`
  - `outputs/site/chart_data/chapter2_intra_cluster_pairs.csv`

## Chapter 3 (WHEN: 월별 민원-이동 연관)
- What was analyzed:
  - Whether complaint pressure co-moves with youth outflow over time.
- Data used:
  - `od_youth_monthly_dong.csv`
  - `complaint_by_cluster_month_2024.csv`
  - `youth_population_by_dong.csv`
- Processing:
  - Monthly city rollup (`youth_net`, `complaint_count`).
  - Horizon windows (3/6/12 months) and association tests (Spearman/Pearson/OLS).
- What result means:
  - Sign and strength of coefficients show whether complaint pressure and outflow pressure move together.
- Site outputs:
  - Monthly dual-axis trend + horizon scatter + association table.
  - `outputs/site/chart_data/chapter3_monthly_city.csv`
  - `outputs/site/chart_data/chapter3_monthly_lag_points.csv`
  - `outputs/site/chart_data/chapter3_monthly_assoc.csv`
  - `outputs/site/chart_data/chapter3_horizon_assoc.csv`
  - `outputs/site/chart_data/chapter3_horizon_points.csv`

## Chapter 4 (EVIDENCE: 정책 우선순위 + 신축/노후 민원축)
- What was analyzed:
  - Intervention tiers (A/B/C/D) and axis differences (`신축·재정비` vs `노후·정체`) in complaint/outflow patterns.
- Data used:
  - `complaint_mobility_join_2024.csv`
  - `cluster_month_panel_2024.csv`
  - `od_youth_intra_seongnam_dong.csv`
  - `policy_priority_matrix_2024.csv`
  - `policy_newold_axis_mapping_by_cluster_2024.csv`
  - `policy_newold_group_comparison_2024.csv`
  - `policy_newold_topic_group_comparison_2024.csv`
  - `Seongnam Youth Polarization _standalone_.html` (axis-definition context labels)
- Processing:
  - High-outflow / persistent-outflow / high-complaint flags and weighted priority scoring.
  - Axis typing by cluster (`신축·재정비`, `노후·정체`, `혼합/전이`) and grouped complaint/outflow summaries.
- What result means:
  - Tiers identify urgency of intervention.
  - Axis comparison clarifies whether complaint burden and outflow pressure are concentrated by urban-structure type.
- Site outputs:
  - Tier criteria, priority, risk charts + axis complaint visual and axis summary table.
  - `outputs/site/chart_data/chapter4_priority_matrix.csv`
  - `outputs/site/chart_data/chapter4_policy_newold_axis_mapping.csv`
  - `outputs/site/chart_data/chapter4_policy_newold_group_comparison.csv`
  - `outputs/site/chart_data/chapter4_policy_newold_topic_group_comparison.csv`
  - `outputs/site/chart_data/chapter4_axis_complaint_findings.csv`
  - `outputs/site/chart_data/chapter4_axis_complaint_summary.csv`
  - `outputs/site/chart_data/chapter4_axis_context_evidence.csv`
  - `outputs/site/chart_data/chapter4_cross_section_tests.csv`
  - `outputs/site/chart_data/chapter4_policy_relations.csv`
  - `outputs/site/chart_data/chapter4_models.csv`
  - `outputs/site/chart_data/chapter4_sensitivity.csv`

## Chapter 5 (ITERATIVE LOOP: 반복형 신호 강화)
- What was analyzed:
  - How much engineered features improve association compared to raw features.
- Data used:
  - `iterative_feature_correlation_v2.csv`
  - `iterative_optimizer_summary_v2.json`
  - `iterative_visualization_recommendations_v2.csv`
  - `policy_priority_matrix_2024.csv` (for interaction scatter points)
- Processing:
  - Iteration-wise best absolute Spearman extraction.
  - Raw -> engineered/interactions loop progression tracking.
- What result means:
  - Improvement by iteration validates whether repeated feature engineering materially increases explanatory signal.
- Site outputs:
  - Loop progress chart + loop table + top-signal chart + interaction scatter + visualization recommendations.
  - `outputs/site/chart_data/chapter5_iterative_feature_correlation.csv`
  - `outputs/site/chart_data/chapter5_iterative_loop_progress.csv`
  - `outputs/site/chart_data/chapter5_iterative_visualization_recommendations.csv`
"""
    (ROOT / "docs" / "ANALYSIS_TRACEABILITY.md").write_text(content, encoding="utf-8")


def build_html() -> str:
    return """<!DOCTYPE html>
<html lang=\"ko\">
<head>
<meta charset=\"UTF-8\" />
<meta name=\"viewport\" content=\"width=device-width,initial-scale=1.0\" />
<title>성남 청년 이동·생활마찰 분석 (V2)</title>
<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\" />
<link href=\"https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css\" rel=\"stylesheet\" />
<link rel=\"stylesheet\" href=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.css\"/>
<script src=\"https://cdn.tailwindcss.com\"></script>
<script src=\"https://unpkg.com/leaflet@1.9.4/dist/leaflet.js\"></script>
<script src=\"https://cdn.plot.ly/plotly-2.35.2.min.js\"></script>
<script src=\"./data.js\"></script>
<style>
:root {
  --bg:#0a0a0f; --bg-soft:#11121a; --card:#161824; --border:#252837;
  --text:#f4f4f8; --dim:#8a8c9d; --out:#f97316; --in:#38bdf8; --gold:#facc15;
}
html,body{background:var(--bg);color:var(--text);font-family:'Pretendard Variable',Pretendard,sans-serif}
.grain{background-image:radial-gradient(at 20% 10%,rgba(249,115,22,.10) 0%,transparent 40%),radial-gradient(at 80% 90%,rgba(56,189,248,.10) 0%,transparent 40%),radial-gradient(at 50% 50%,rgba(250,204,21,.04) 0%,transparent 60%)}
.card{background:var(--card);border:1px solid var(--border);border-radius:18px}
.section-num{display:inline-block;font-size:11px;letter-spacing:.3em;color:var(--dim);padding-bottom:4px;border-bottom:1px solid var(--border)}
.punchline{background:linear-gradient(120deg,#f97316 0%,#facc15 50%,#38bdf8 100%);-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent}
.leaflet-container{background:var(--bg-soft);border-radius:14px}
.leaflet-tooltip{background:var(--card);color:var(--text);border:1px solid var(--border);font-size:12px}
.axis-note{font-size:12px;color:#a1a1aa;border-left:3px solid #374151;padding-left:10px}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{border-bottom:1px solid #252837;padding:8px 10px;text-align:left}
th{color:#a1a1aa;font-weight:600}
</style>
</head>
<body class=\"grain\">
<header class=\"max-w-7xl mx-auto px-6 pt-10 pb-6\">
  <div class=\"section-num mb-3\">SEONGNAM YOUTH POLARIZATION · V2</div>
  <h1 class=\"text-4xl md:text-6xl font-black tracking-tight leading-[1.05] mb-4\">어디서 빠지고,<br><span class=\"punchline\">어디서 다시 재배치되는가</span></h1>
  <p class=\"text-lg text-zinc-400 max-w-4xl\">지도-이동-월별연관-정책근거를 분리해서, 각 단계의 데이터·지표·해석 기준을 명시했습니다.</p>
</header>

<section class=\"max-w-7xl mx-auto px-6 py-4\">
  <div class=\"section-num mb-2\">CHAPTER 00 · TRACEABILITY</div>
  <h2 class=\"text-3xl font-bold mb-2\">분석 추적성 매트릭스 (무엇/데이터/처리/의미)</h2>
  <div class=\"card p-4 mb-8\">
    <div class=\"axis-note mb-3\">각 분석별로 무엇을 봤는지, 어떤 데이터를 썼는지, 어떻게 가공했는지, 결과가 정책적으로 무엇을 뜻하는지까지 한 줄로 연결합니다.</div>
    <table id=\"tbl-method-trace\"></table>
  </div>
</section>

<section class=\"max-w-7xl mx-auto px-6 py-4\">
  <div class=\"section-num mb-2\">CHAPTER 01 · WHAT</div>
  <h2 class=\"text-3xl font-bold mb-2\">동별 청년 순유출률 지도</h2>
  <div class=\"grid lg:grid-cols-3 gap-6\">
    <div class=\"lg:col-span-2 card p-3\">
      <div id=\"map\" style=\"height:540px\"></div>
      <div class=\"axis-note mt-3\">색상 단위: 청년 순유출률(%). 빨강=순유출, 파랑=순유입. 우측 TOP5는 성남 내부 동→동 도착지입니다.</div>
    </div>
    <div class=\"card p-5\">
      <div class=\"text-xs text-zinc-500 mb-1\">선택된 행정동</div>
      <div id=\"dong-name\" class=\"text-5xl font-black mb-1\">-</div>
      <div id=\"dong-sgg\" class=\"text-zinc-400 mb-6\">-</div>
      <div class=\"text-xs text-zinc-500 mb-1\">청년 순유출률</div>
      <div id=\"dong-rate\" class=\"text-6xl font-black mb-6\">-</div>
      <div class=\"grid grid-cols-3 gap-2 text-center mb-5\">
        <div><div class=\"text-zinc-500 text-[11px]\">전입(명)</div><div id=\"dong-in\" class=\"text-sky-400 font-bold\">-</div></div>
        <div><div class=\"text-zinc-500 text-[11px]\">전출(명)</div><div id=\"dong-out\" class=\"text-orange-400 font-bold\">-</div></div>
        <div><div class=\"text-zinc-500 text-[11px]\">청년 인구(명)</div><div id=\"dong-pop\" class=\"font-bold\">-</div></div>
      </div>
      <div class=\"text-xs text-zinc-500 mb-2\">성남 내부 주요 도착지 TOP5</div>
      <ul id=\"dong-top-dest\" class=\"space-y-1 text-sm\"></ul>
    </div>
  </div>
</section>

<section class=\"max-w-7xl mx-auto px-6 py-12\">
  <div class=\"section-num mb-2\">CHAPTER 02 · WHERE</div>
  <h2 class=\"text-3xl font-bold mb-2\">성남 내부 재배치 구조</h2>
  <div class=\"grid lg:grid-cols-2 gap-6\">
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">생활권 간 이동 히트맵 (상위 12개 생활권)</div>
      <div class=\"axis-note mb-2\">X축: 도착 생활권, Y축: 출발 생활권, 색상: 이동 인원(명). 값이 클수록 이동 집중.</div>
      <div id=\"heat-intra\" style=\"height:430px\"></div>
    </div>
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">상위 생활권 이동쌍 TOP 20</div>
      <div class=\"axis-note mb-2\">성남 내부에서 실제로 이동량이 큰 출발→도착 조합입니다.</div>
      <table id=\"tbl-pairs\"></table>
    </div>
  </div>
</section>

<section class=\"max-w-7xl mx-auto px-6 py-12\">
  <div class=\"section-num mb-2\">CHAPTER 03 · WHEN</div>
  <h2 class=\"text-3xl font-bold mb-2\">월별 이동 압력과 민원 신호 연관</h2>
  <div class=\"grid lg:grid-cols-2 gap-6\">
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">월별 순이동(막대) vs 민원건수(선)</div>
      <div class=\"axis-note mb-2\">X축: 월, 왼쪽 Y축: 순이동(명), 오른쪽 Y축: 민원건수. 순이동이 음수면 순유출.</div>
      <div id=\"chart-monthly\" style=\"height:360px\"></div>
    </div>
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">민원강도와 순유출률의 3/6/12개월 창 연관</div>
      <div class=\"axis-note mb-2\">X축: 민원강도(window 평균), Y축: 순유출률(window 평균). 색상/모양은 기간창(3·6·12개월)을 의미합니다.</div>
      <div id=\"chart-lag\" style=\"height:360px\"></div>
      <div id=\"lag-summary\" class=\"mt-3 text-sm text-zinc-300\"></div>
    </div>
  </div>
  <div class=\"card p-4 mt-6\">
    <div class=\"text-sm text-zinc-300 mb-2\">기간창별 연관 검정 결과 요약</div>
    <table id=\"tbl-monthly-assoc\"></table>
  </div>
</section>

<section class=\"max-w-7xl mx-auto px-6 py-12\">
  <div class=\"section-num mb-2\">CHAPTER 04 · EVIDENCE</div>
  <h2 class=\"text-3xl font-bold mb-2\">개입 등급 기준과 통계 근거</h2>
  <div class=\"grid lg:grid-cols-2 gap-6\">
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">개입 등급(A/B/C/D) 기준</div>
      <div class=\"axis-note mb-3\">A: 고유출·지속유출·고민원 3개 플래그 동시 충족. B: 2개, C: 1개, D: 0개.</div>
      <table id=\"tbl-criteria\"></table>
    </div>
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">A/B 등급 우선 생활권</div>
      <table id=\"tbl-priority\"></table>
    </div>
  </div>
  <div class=\"grid lg:grid-cols-2 gap-6 mt-6\">
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">개입 등급 분포</div>
      <div id=\"chart-tier-bar\" style=\"height:280px\"></div>
    </div>
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">개입 등급 위험도 맵</div>
      <div class=\"axis-note mb-2\">X축: 6개월 순유출률(%), Y축: 순유출 월 비중(%), 점 크기: 민원강도, 색상: 개입등급</div>
      <div id=\"chart-tier-risk\" style=\"height:320px\"></div>
    </div>
  </div>
  <div class=\"grid lg:grid-cols-2 gap-6 mt-6\">
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">신축 vs 노후 × 민원강도 분포</div>
      <div class=\"axis-note mb-2\">그룹: `신축·재정비` / `노후·정체` / `혼합·전이`. 값이 높을수록 총인구 1천명당 민원강도가 높습니다.</div>
      <div id=\"chart-axis-complaint\" style=\"height:320px\"></div>
    </div>
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">신축 vs 노후 × 민원/유출 요약 테이블</div>
      <table id=\"tbl-axis-findings\"></table>
    </div>
  </div>
  <div class=\"card p-4 mt-6\">
    <div class=\"text-sm text-zinc-300 mb-2\">신축/노후 축 정의 근거 (첨부 파일 반영)</div>
    <div class=\"axis-note mb-2\">축 정의는 첨부된 standalone 결과의 핵심 라벨(유입 핫스팟/유출 핫스팟)을 기준으로 현재 민원 분석에 매핑했습니다.</div>
    <table id=\"tbl-axis-context\"></table>
  </div>
  <div class=\"card p-4 mt-6\">
    <div class=\"text-sm text-zinc-300 mb-2\">해석 결론</div>
    <div id=\"chapter4-conclusion\" class=\"text-sm leading-7 text-zinc-300\"></div>
  </div>
  <div class=\"grid lg:grid-cols-3 gap-6 mt-6\">
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">핵심 변수 연관검정</div>
      <table id=\"tbl-tests\"></table>
    </div>
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">민감도 분석</div>
      <table id=\"tbl-sens\"></table>
    </div>
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">지표 정의</div>
      <table id=\"tbl-vars\"></table>
    </div>
  </div>
</section>

<section class=\"max-w-7xl mx-auto px-6 py-12\">
  <div class=\"section-num mb-2\">CHAPTER 05 · ITERATIVE LOOP</div>
  <h2 class=\"text-3xl font-bold mb-2\">반복형 분석 루프 최적화 결과</h2>
  <div class=\"grid lg:grid-cols-2 gap-6\">
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">루프 요약</div>
      <table id=\"tbl-iterative-summary\"></table>
    </div>
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">반복 단계별 성능 추이</div>
      <div class=\"axis-note mb-2\">반복(iteration)이 증가할 때 최고 절대 Spearman 신호가 실제로 강화되는지 추적합니다.</div>
      <div id=\"chart-iter-loop\" style=\"height:320px\"></div>
    </div>
  </div>
  <div class=\"grid lg:grid-cols-2 gap-6 mt-6\">
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">TOP 신호(절대 Spearman)</div>
      <div class=\"axis-note mb-2\">상관이 약하면 피처 엔지니어링/상호작용 결합으로 재평가한 결과를 단계별로 비교합니다.</div>
      <div id=\"chart-iter-top\" style=\"height:320px\"></div>
    </div>
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">반복 루프 상세 로그</div>
      <table id=\"tbl-iter-loop\"></table>
    </div>
  </div>
  <div class=\"grid lg:grid-cols-2 gap-6 mt-6\">
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">최적 상호작용 피처 산점도</div>
      <div class=\"axis-note mb-2\">`A__x__B` 형태의 최적 결합 피처를 원천 피처로 분해해 관계를 직관적으로 확인합니다.</div>
      <div id=\"chart-iter-interaction\" style=\"height:320px\"></div>
    </div>
    <div class=\"card p-4\">
      <div class=\"text-sm text-zinc-300 mb-2\">시각화 솔루션 권고안</div>
      <table id=\"tbl-iter-reco\"></table>
    </div>
  </div>
</section>

<script>
const D = window.SN_DATA || {};
const fmt = n => (n==null||Number.isNaN(Number(n))?'—':Number(n).toLocaleString('ko-KR'));
const pct = n => (n==null||Number.isNaN(Number(n))?'—':(Number(n)>=0?'+':'') + Number(n).toFixed(2) + '%');
const n2 = n => (n==null||Number.isNaN(Number(n))?'—':Number(n).toFixed(2));
function tableHtml(headers, rows){
  return '<thead><tr>'+headers.map(h=>`<th>${h}</th>`).join('')+'</tr></thead><tbody>'+
    rows.map(r=>'<tr>'+r.map(v=>`<td>${v}</td>`).join('')+'</tr>').join('')+'</tbody>';
}

const byRate = [...(D.dong||[])].sort((a,b)=>a['청년_순유출률']-b['청년_순유출률']);

const methodTrace = [
  ['CH1 WHAT', '동별 청년 순유출 hotspot 식별', 'youth_migration + youth_population + geojson', '(전출-전입)/청년인구*100 + 폴리곤 결합', '순유출 고위험 동을 1차 선별'],
  ['CH2 WHERE', '성남 내부 재배치 경로 식별', 'od_youth_intra_seongnam_dong', '동 OD -> 생활권 행렬 + 상위 경로 추출', '내부 이동 집중 통로 파악'],
  ['CH3 WHEN', '민원 압력-순유출 동행 여부', 'monthly OD + monthly complaints', '월집계 + 3/6/12개월 창 연관검정', '연관 강도/방향 확인'],
  ['CH4 EVIDENCE', '개입등급 + 신축/노후 민원축 비교', 'priority + policy_newold_axis/group/topic', '플래그 규칙/점수화 + 축 그룹 집계', '정책 우선순위와 구조축 차이 해석'],
  ['CH5 ITERATIVE', '반복형 피처엔지니어링 효과', 'iterative correlations/recommendations', 'iteration별 최고 신호 추적 + 상호작용 분해', '재평가 루프로 신호 강화 확인'],
];
document.getElementById('tbl-method-trace').innerHTML = tableHtml(
  ['분석', '무엇을 분석', '어떤 데이터', '어떻게 처리', '결과 의미'],
  methodTrace
);

// CH1 map
const map = L.map('map', { zoomControl: true, attributionControl: false }).setView([37.42, 127.13], 12);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png', {subdomains:'abcd', maxZoom:19}).addTo(map);
const rates = (D.geo?.features||[]).map(f=>f.properties.rate).filter(v=>v!=null);
const vmax = Math.max(...rates.map(v=>Math.abs(v)), 1);
const colorFor = v => {
  if(v==null) return '#444';
  const t=Math.max(-1,Math.min(1,v/vmax));
  if(t>0){const a=t; return `rgb(${Math.round(127*a + 22*(1-a))},${Math.round(29*a + 24*(1-a))},${Math.round(29*a + 36*(1-a))})`;}
  const a=-t; return `rgb(${Math.round(30*a + 22*(1-a))},${Math.round(58*a + 24*(1-a))},${Math.round(138*a + 36*(1-a))})`;
};
let lockedDong=null;
const layer = L.geoJSON(D.geo, {
  style:f=>({color:'#0a0a0f',weight:0.8,fillColor:colorFor(f.properties.rate),fillOpacity:0.92}),
  onEachFeature:(f,l)=>{
    l.bindTooltip(`<b>${f.properties.dong}</b> (${f.properties.sgg_full||''})<br>순유출률: <b>${pct(f.properties.rate)}</b><br>청년 인구: ${fmt(f.properties.youth_pop)}명`,{sticky:true});
    l.on('mouseover',e=>{ if(!lockedDong) showDong(f.properties); e.target.setStyle({weight:2.5,color:'#facc15'});});
    l.on('mouseout',e=>{ if(!lockedDong) e.target.setStyle({weight:0.8,color:'#0a0a0f'});});
    l.on('click',()=>{ lockedDong=(lockedDong===f.properties.dong)?null:f.properties.dong; showDong(f.properties); });
  }
}).addTo(map);
map.fitBounds(layer.getBounds(), {padding:[10,10]});

function showDong(p){
  document.getElementById('dong-name').textContent = p.dong + (lockedDong===p.dong?' (고정)':'');
  document.getElementById('dong-sgg').textContent = p.sgg_full || '';
  const rateEl = document.getElementById('dong-rate');
  rateEl.textContent = pct(p.rate);
  rateEl.className = 'text-6xl font-black mb-6 ' + ((p.rate||0)>0 ? 'text-orange-400' : 'text-sky-400');
  document.getElementById('dong-in').textContent = fmt(p.youth_in);
  document.getElementById('dong-out').textContent = fmt(p.youth_out);
  document.getElementById('dong-pop').textContent = fmt(p.youth_pop);

  const intraTop = (D.od_intra||[])
    .filter(o=>o.origin_dong===p.dong)
    .sort((a,b)=>b.n-a.n)
    .slice(0,5);
  document.getElementById('dong-top-dest').innerHTML = intraTop.length===0
    ? '<li class="text-zinc-600">데이터 없음</li>'
    : intraTop.map(o=>`<li class="flex justify-between"><span>${o.dest_dong}</span><span class="text-zinc-500">${fmt(o.n)}명</span></li>`).join('');
}

// CH2 heatmap
const m = D.od_intra_matrix || [];
const oLabels = [...new Set(m.map(r=>r.origin_cluster))];
const dLabels = [...new Set(m.map(r=>r.dest_cluster))];
const z = oLabels.map(o => dLabels.map(d => {
  const r = m.find(x => x.origin_cluster===o && x.dest_cluster===d);
  return r ? Number(r.n) : 0;
}));
Plotly.newPlot('heat-intra', [{
  type:'heatmap',
  x:dLabels, y:oLabels, z,
  colorscale:'YlOrRd',
  hovertemplate:'출발 %{y}<br>도착 %{x}<br>이동 %{z}명<extra></extra>'
}], {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Pretendard',color:'#f4f4f8',size:10},
  xaxis:{tickangle:-30}, yaxis:{autorange:'reversed'},
  margin:{l:90,r:12,t:12,b:80}
},{displayModeBar:false});

const pairs = (D.od_intra_pairs||[]).slice(0,20);
document.getElementById('tbl-pairs').innerHTML = tableHtml(
  ['순위','출발','도착','이동(명)'],
  pairs.map((r,i)=>[i+1, r.origin_cluster, r.dest_cluster, fmt(r.n)])
);

// CH3 monthly
const city = (D.monthly_city||[]).slice().sort((a,b)=>String(a.month).localeCompare(String(b.month)));
const monthLab = city.map(r=>String(r.month).slice(0,4)+'-'+String(r.month).slice(4));
Plotly.newPlot('chart-monthly', [
  {type:'bar', x:monthLab, y:city.map(r=>Number(r.youth_net)), name:'순이동(명)', marker:{color:city.map(r=>Number(r.youth_net)>=0?'rgba(56,189,248,0.75)':'rgba(249,115,22,0.75)')}, yaxis:'y1'},
  {type:'scatter', mode:'lines+markers', x:monthLab, y:city.map(r=>Number(r.complaint_count)), name:'민원건수', line:{color:'#facc15',width:2}, marker:{size:6}, yaxis:'y2'}
], {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Pretendard',color:'#f4f4f8',size:10},
  xaxis:{gridcolor:'#252837'},
  yaxis:{title:'순이동(명)',gridcolor:'#252837',zerolinecolor:'#666'},
  yaxis2:{title:'민원건수',overlaying:'y',side:'right',showgrid:false},
  legend:{orientation:'h',y:1.1},
  margin:{l:60,r:60,t:10,b:50},
  shapes:[{type:'line',x0:0,x1:1,y0:0,y1:0,xref:'paper',line:{color:'#666',dash:'dash',width:1}}]
},{displayModeBar:false});

const horizonPoints = D.horizon_points || [];
const horizonAssoc = D.horizon_assoc || [];
const hStyles = {
  3: {name:'3개월', color:'rgba(249,115,22,0.72)', symbol:'circle'},
  6: {name:'6개월', color:'rgba(56,189,248,0.72)', symbol:'diamond'},
  12: {name:'12개월', color:'rgba(168,85,247,0.72)', symbol:'square'}
};
const lagTraces = [3,6,12].map(h=>{
  const sub = horizonPoints.filter(r=>Number(r.horizon_months)===h);
  const style = hStyles[h];
  return {
    type:'scatter', mode:'markers', name:style.name,
    x:sub.map(r=>Number(r.complaint_window)),
    y:sub.map(r=>Number(r.outflow_window)),
    text:sub.map(r=>`${r.dong_cluster} (${String(r.end_month).slice(0,4)}-${String(r.end_month).slice(4)})`),
    marker:{
      size:sub.map(()=>8),
      color:style.color,
      symbol:style.symbol,
      line:{width:1,color:'#0a0a0f'}
    },
    hovertemplate:'%{text}<br>민원강도(window): %{x:.2f}<br>순유출률(window): %{y:.2f}%<extra></extra>'
  };
}).filter(t=>t.x.length>0);
Plotly.newPlot('chart-lag', lagTraces, {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Pretendard',color:'#f4f4f8',size:10},
  xaxis:{title:'민원강도(총인구 1천명당, window 평균)',gridcolor:'#252837'},
  yaxis:{title:'청년 순유출률(window 평균, %)',gridcolor:'#252837'},
  margin:{l:60,r:10,t:10,b:50},
  legend:{orientation:'h',y:1.1}
},{displayModeBar:false});

const h3 = horizonAssoc.find(r=>Number(r.horizon_months)===3);
const h6 = horizonAssoc.find(r=>Number(r.horizon_months)===6);
const h12 = horizonAssoc.find(r=>Number(r.horizon_months)===12);
function hText(row){
  if (!row || row.status!=='ok') return '데이터 부족';
  const s = Math.abs(Number(row.spearman_r||0));
  const level = s>=0.3 ? '중간 이상' : (s>=0.1 ? '약함' : '매우 약함');
  return `${level} (r=${n2(row.spearman_r)}, p=${n2(row.spearman_p)}, n=${fmt(row.n)})`;
}
document.getElementById('lag-summary').innerHTML =
  `<b>핵심 해석:</b> 3개월=${hText(h3)} / 6개월=${hText(h6)} / 12개월=${hText(h12)}.`;

const assoc = (D.horizon_assoc||[]).map(r=>[
  `${fmt(r.horizon_months)}개월`,
  fmt(r.n),
  r.status==='ok' ? n2(r.spearman_r) : '—',
  r.status==='ok' ? n2(r.slope) : '—',
  r.status==='ok' ? n2(r.r2) : '—',
  r.status==='ok' ? '분석 가능' : '데이터 부족'
]);
document.getElementById('tbl-monthly-assoc').innerHTML = tableHtml(
  ['기간창','표본수','Spearman r','기울기','R²','상태'],
  assoc
);

// CH4 evidence
const c = D.criteria || {};
const th = c.thresholds || {};
document.getElementById('tbl-criteria').innerHTML = tableHtml(
  ['항목','기준값'],
  [
    ['고유출 플래그', `유출률 >= ${n2(th.youth_outflow_rate_q70)}% (70분위)`],
    ['지속유출 플래그', `순유출 월비중 >= ${n2((th.negative_month_share_q70||0)*100)}% (70분위)`],
    ['고민원 플래그', `민원강도 >= ${n2(th.complaints_per_1000_totalpop_q60)} (60분위)`],
    ['A/B/C/D 규칙', '플래그 3/2/1/0개 충족']
  ]
);

const pri = (D.priority||[]).filter(r=>['A_즉시개입','B_우선개입'].includes(r.policy_tier)).slice(0,15);
document.getElementById('tbl-priority').innerHTML = tableHtml(
  ['생활권','등급','근거','유출률(%)','순유출월비중'],
  pri.map(r=>[r.dong_cluster, r.policy_tier, r.tier_reason, n2(r.youth_outflow_rate), n2(Number(r.negative_month_share)*100)+'%'])
);

const allPri = D.priority || [];
const tierOrder = ['A_즉시개입','B_우선개입','C_모니터링','D_유지'];
const tierColor = {'A_즉시개입':'#f97316','B_우선개입':'#f59e0b','C_모니터링':'#38bdf8','D_유지':'#64748b'};
const tierCounts = tierOrder.map(t => allPri.filter(r=>r.policy_tier===t).length);
Plotly.newPlot('chart-tier-bar', [{
  type:'bar',
  x:tierOrder, y:tierCounts,
  marker:{color:tierOrder.map(t=>tierColor[t])},
  text:tierCounts.map(v=>String(v)), textposition:'outside',
  hovertemplate:'%{x}<br>%{y}개 생활권<extra></extra>'
}], {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Pretendard',color:'#f4f4f8',size:10},
  xaxis:{gridcolor:'#252837'}, yaxis:{title:'생활권 수',gridcolor:'#252837',dtick:1},
  margin:{l:55,r:10,t:20,b:40}
},{displayModeBar:false});

Plotly.newPlot('chart-tier-risk', tierOrder.map(t=>{
  const s = allPri.filter(r=>r.policy_tier===t);
  return {
    type:'scatter', mode:'markers', name:t,
    x:s.map(r=>Number(r.youth_outflow_rate)),
    y:s.map(r=>Number(r.negative_month_share)*100),
    text:s.map(r=>r.dong_cluster),
    marker:{color:tierColor[t], size:s.map(r=>Math.max(9, Number(r.complaints_per_1000_totalpop)*1.5)), line:{width:1,color:'#0a0a0f'}},
    hovertemplate:'%{text}<br>유출률 %{x:.2f}%<br>순유출월비중 %{y:.1f}%<extra></extra>'
  };
}), {
  paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
  font:{family:'Pretendard',color:'#f4f4f8',size:10},
  xaxis:{title:'청년 순유출률(%)',gridcolor:'#252837'},
  yaxis:{title:'순유출 월 비중(%)',gridcolor:'#252837'},
  margin:{l:60,r:10,t:10,b:50},
  shapes:[
    {type:'line',x0:Number(th.youth_outflow_rate_q70||0),x1:Number(th.youth_outflow_rate_q70||0),y0:0,y1:1,yref:'paper',line:{color:'#f59e0b',dash:'dot',width:1}},
    {type:'line',x0:0,x1:1,xref:'paper',y0:Number(th.negative_month_share_q70||0)*100,y1:Number(th.negative_month_share_q70||0)*100,line:{color:'#f59e0b',dash:'dot',width:1}}
  ],
  legend:{orientation:'h',y:-0.2}
},{displayModeBar:false});

const axisOrder = ['신축·재정비', '노후·정체', '혼합/전이'];
const axisColor = {'신축·재정비':'#38bdf8','노후·정체':'#f97316','혼합/전이':'#94a3b8'};
const axisRows = (D.axis_findings || []).slice();
const axisSummary = (D.axis_summary || []).slice();
const axisChartTraces = axisOrder.map(label => {
  const vals = axisRows
    .filter(r => String(r.axis_type) === label)
    .map(r => Number(r.complaints_per_1000_totalpop))
    .filter(v => Number.isFinite(v));
  return {
    type:'box',
    name:label,
    y:vals,
    boxpoints:'all',
    jitter:0.35,
    pointpos:0,
    marker:{size:6,color:axisColor[label] || '#94a3b8',opacity:0.75},
    line:{color:axisColor[label] || '#94a3b8'},
    hovertemplate:`${label}<br>민원강도 %{y:.2f}<extra></extra>`
  };
}).filter(t => t.y.length > 0);
if (axisChartTraces.length){
  Plotly.newPlot('chart-axis-complaint', axisChartTraces, {
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'Pretendard',color:'#f4f4f8',size:10},
    xaxis:{gridcolor:'#252837'},
    yaxis:{title:'민원강도(총인구 1천명당)',gridcolor:'#252837'},
    margin:{l:60,r:10,t:10,b:40},
    showlegend:false
  }, {displayModeBar:false});
}
document.getElementById('tbl-axis-findings').innerHTML = tableHtml(
  ['축 그룹','생활권 수','평균 민원강도','평균 유출률(%)','A/B 비중(%)'],
  axisSummary.map(r=>[
    String(r.axis_type || '-'),
    fmt(r.cluster_count),
    n2(r.mean_complaints_per_1000),
    n2(r.mean_outflow_rate),
    n2(r.ab_tier_share_pct)
  ])
);
const axisContext = D.axis_context_evidence || [];
document.getElementById('tbl-axis-context').innerHTML = tableHtml(
  ['출처', '근거 라벨', '근거 문구', '분석 매핑 축'],
  axisContext.map(r=>[
    String(r.source || '-'),
    String(r.evidence_label || '-'),
    String(r.evidence_text || '-'),
    String(r.mapped_axis || '-')
  ])
);

const topA = allPri.filter(r=>r.policy_tier==='A_즉시개입').slice(0,5).map(r=>r.dong_cluster);
const strongest = (D.policy_relations||[])[0];
document.getElementById('chapter4-conclusion').innerHTML = [
  `개입 등급 분포는 <b>A ${tierCounts[0]}개, B ${tierCounts[1]}개, C ${tierCounts[2]}개, D ${tierCounts[3]}개</b>입니다.`,
  axisSummary.length ? `축 비교에서 민원강도 평균이 가장 높은 그룹은 <b>${axisSummary.slice().sort((a,b)=>Number(b.mean_complaints_per_1000)-Number(a.mean_complaints_per_1000))[0].axis_type}</b>입니다.` : '',
  topA.length ? `즉시개입(A) 우선 생활권은 <b>${topA.join(', ')}</b>입니다.` : '즉시개입(A) 생활권은 없습니다.',
  strongest ? `정책지표 중 유출률과 가장 강한 연관은 <b>${strongest.x_variable}</b> (Spearman r=${n2(strongest.spearman_r)}, p=${n2(strongest.spearman_p)})입니다.` : ''
].filter(Boolean).join('<br>');

const rel = (D.policy_relations||[]).slice(0,8);
if (rel.length){
  document.getElementById('tbl-tests').innerHTML = tableHtml(
    ['X 변수','Y 변수','Spearman r','p값'],
    rel.map(r=>[r.x_variable, r.y_variable, n2(r.spearman_r), n2(r.spearman_p)])
  );
} else {
  const tests = (D.tests||[]).slice(0,8);
  document.getElementById('tbl-tests').innerHTML = tableHtml(
    ['변수','Spearman r','p값','95% CI'],
    tests.map(r=>[r.variable, n2(r.spearman_r), n2(r.spearman_p), `${n2(r.spearman_ci_low)} ~ ${n2(r.spearman_ci_high)}`])
  );
}

const sens = D.sensitivity || [];
document.getElementById('tbl-sens').innerHTML = tableHtml(
  ['시나리오','TOP10 중복률','최대','최소'],
  sens.map(r=>[r.scenario, n2(Number(r.top10_overlap_with_base)*100)+'%', n2(r.max_rate), n2(r.min_rate)])
);

const vars = c.variables || {};
document.getElementById('tbl-vars').innerHTML = tableHtml(
  ['변수','의미'],
  Object.entries(vars).map(([k,v])=>[k,v])
);

// CH5 iterative loop
const iterSummary = D.iterative_summary || {};
const iterCorr = (D.iterative_corr || []).slice();
const iterReco = (D.iterative_reco || []).slice();
const iterLoop = (D.iterative_loop_progress || []).slice().sort((a,b)=>Number(a.iteration)-Number(b.iteration));

document.getElementById('tbl-iterative-summary').innerHTML = tableHtml(
  ['항목', '값'],
  [
    ['품질 판정', String(iterSummary.quality || '-')],
    ['목표 임계치', iterSummary.threshold == null ? '-' : n2(iterSummary.threshold)],
    ['반복 횟수', iterSummary.iterations_run == null ? '-' : fmt(iterSummary.iterations_run)],
    ['최종 최적 피처', String(iterSummary.best_feature || '-')],
    ['최고 절대 Spearman', iterSummary.best_abs_spearman_r == null ? '-' : n2(iterSummary.best_abs_spearman_r)],
  ]
);

if (iterLoop.length){
  Plotly.newPlot('chart-iter-loop', [{
    type:'scatter',
    mode:'lines+markers',
    x:iterLoop.map(r=>`Iter ${fmt(r.iteration)}`),
    y:iterLoop.map(r=>Number(r.best_abs_spearman_r)),
    marker:{size:9,color:'#facc15'},
    line:{width:3,color:'#f97316'},
    text:iterLoop.map(r=>String(r.best_feature || '-')),
    hovertemplate:'%{x}<br>best abs r=%{y:.3f}<br>feature=%{text}<extra></extra>'
  }], {
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'Pretendard',color:'#f4f4f8',size:10},
    xaxis:{gridcolor:'#252837'},
    yaxis:{title:'best abs(Spearman r)',gridcolor:'#252837'},
    margin:{l:60,r:10,t:10,b:45},
    shapes: iterSummary.threshold == null ? [] : [{
      type:'line', x0:0, x1:1, xref:'paper',
      y0:Number(iterSummary.threshold), y1:Number(iterSummary.threshold),
      line:{color:'#38bdf8',dash:'dash',width:1}
    }]
  }, {displayModeBar:false});
}

document.getElementById('tbl-iter-loop').innerHTML = tableHtml(
  ['반복', '최고 피처', '최고 abs r', '이전 대비 Δ', '검토 피처수'],
  iterLoop.map(r=>[
    fmt(r.iteration),
    String(r.best_feature || '-'),
    n2(r.best_abs_spearman_r),
    r.delta_from_prev == null || Number.isNaN(Number(r.delta_from_prev))
      ? '-'
      : (Number(r.delta_from_prev) >= 0 ? '+' : '') + n2(r.delta_from_prev),
    fmt(r.features_tested),
  ])
);

const iterTop = iterCorr
  .sort((a,b)=>Number(b.abs_spearman_r||0)-Number(a.abs_spearman_r||0))
  .slice(0,10);
if (iterTop.length){
  Plotly.newPlot('chart-iter-top', [{
    type:'bar',
    x:iterTop.map(r=>String(r.feature)),
    y:iterTop.map(r=>Number(r.abs_spearman_r)),
    marker:{color:iterTop.map(r=>String(r.stage).includes('engineered') ? '#f97316' : '#38bdf8')},
    customdata:iterTop.map(r=>[r.stage, r.iteration, r.n, r.spearman_r]),
    hovertemplate:'%{x}<br>abs_r=%{y:.3f}<br>stage=%{customdata[0]}<br>iter=%{customdata[1]}<br>n=%{customdata[2]}<br>r=%{customdata[3]:.3f}<extra></extra>'
  }],{
    paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
    font:{family:'Pretendard',color:'#f4f4f8',size:10},
    xaxis:{tickangle:-35,gridcolor:'#252837'},
    yaxis:{title:'abs(Spearman r)',gridcolor:'#252837'},
    margin:{l:55,r:10,t:10,b:120}
  },{displayModeBar:false});
}

const bestInteraction = iterCorr.find(r=>String(r.feature||'').includes('__x__'));
if (bestInteraction){
  const parts = String(bestInteraction.feature).split('__x__');
  const left = parts[0];
  const right = parts[1];
  const points = (D.priority||[])
    .filter(r => Number.isFinite(Number(r[left])) && Number.isFinite(Number(r[right])) && Number.isFinite(Number(r.youth_outflow_rate)));
  if (points.length){
    Plotly.newPlot('chart-iter-interaction', [{
      type:'scatter',
      mode:'markers',
      x:points.map(r=>Number(r[left])),
      y:points.map(r=>Number(r[right])),
      text:points.map(r=>String(r.dong_cluster||'')),
      marker:{
        size:points.map(r=>Math.max(8, Math.abs(Number(r.youth_outflow_rate))*2)),
        color:points.map(r=>Number(r.youth_outflow_rate)),
        colorscale:'YlOrRd',
        showscale:true,
        colorbar:{title:'outflow'}
      },
      hovertemplate:'%{text}<br>'+left+': %{x:.3f}<br>'+right+': %{y:.3f}<extra></extra>'
    }],{
      paper_bgcolor:'rgba(0,0,0,0)', plot_bgcolor:'rgba(0,0,0,0)',
      font:{family:'Pretendard',color:'#f4f4f8',size:10},
      xaxis:{title:left,gridcolor:'#252837'},
      yaxis:{title:right,gridcolor:'#252837'},
      margin:{l:60,r:20,t:10,b:55}
    },{displayModeBar:false});
  }
}

document.getElementById('tbl-iter-reco').innerHTML = tableHtml(
  ['feature', 'recommended visual', 'reason'],
  iterReco.slice(0,8).map(r=>[String(r.feature||'-'), String(r.recommended_visual||'-'), String(r.reason||'-')])
);

if (byRate.length){
  const target = byRate[byRate.length-1].dong;
  const feat = (D.geo?.features||[]).find(f=>f.properties.dong===target);
  if (feat) showDong(feat.properties);
}
</script>
</body>
</html>
"""


def main() -> None:
    payload, frames = build_payload()
    export_chart_data(frames)
    write_traceability_doc()

    out_js = SITE_DIR / "data.js"
    out_html = SITE_DIR / "index.html"

    with out_js.open("w", encoding="utf-8") as f:
        f.write("window.SN_DATA = ")
        json.dump(payload, f, ensure_ascii=False)
        f.write(";")

    out_html.write_text(build_html(), encoding="utf-8")
    print(f"[done] {out_js}")
    print(f"[done] {out_html}")
    print(f"[done] chart_data exported: {CHART_DATA_DIR}")
    print(f"[done] traceability doc: {ROOT / 'docs' / 'ANALYSIS_TRACEABILITY.md'}")


if __name__ == "__main__":
    main()
