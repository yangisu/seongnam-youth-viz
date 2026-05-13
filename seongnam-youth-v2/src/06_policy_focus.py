from __future__ import annotations

import json
import re

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from common import PROCESSED

SEOUL_GANGNAM3 = {"강남구", "서초구", "송파구"}
GYEONGGI_CORE = {"용인시 수지구", "용인시 기흥구", "하남시", "광주시", "수원시 영통구"}
AXIS_NEW = {"신흥동", "삼평동", "고등동", "운중동", "위례동", "백현동", "판교동", "시흥동"}
AXIS_OLD = {"태평동", "수진동", "상대원동", "하대원동", "성남동", "금광동", "중앙동", "은행동", "수내동", "이매동", "정자동", "야탑동", "구미동", "분당동"}

AXIS_GROUP_LABEL = {
    "new_redevelopment": "신축·재정비",
    "old_stagnant": "노후·정체",
    "mixed_other": "혼합/전이",
}
AXIS_GROUP_ORDER = {"new_redevelopment": 0, "old_stagnant": 1, "mixed_other": 2}


def cluster_from_dong(dong: str) -> str:
    if not dong:
        return ""
    m = re.match(r"^(.+?)[1-4]동$", str(dong))
    return f"{m.group(1)}동" if m else str(dong)


def destination_bucket(dest_sido: str, dest_sgg: str) -> str:
    sido = str(dest_sido)
    sgg = str(dest_sgg)
    if sido == "서울특별시" and sgg in SEOUL_GANGNAM3:
        return "서울_강남3구"
    if sido == "서울특별시":
        return "서울_기타"
    if sido == "경기도" and sgg in GYEONGGI_CORE:
        return "경기_인접핵심"
    if sido == "경기도":
        return "경기_기타"
    return "수도권외"


def axis_group_from_cluster(cluster: str) -> str:
    c = str(cluster)
    if c in AXIS_NEW:
        return "new_redevelopment"
    if c in AXIS_OLD:
        return "old_stagnant"
    return "mixed_other"


def _require_columns(df: pd.DataFrame, required: list[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def build_destination_cluster_outputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    od = pd.read_csv(PROCESSED / "od_youth_seongnam_dong_to_outside.csv")
    od["destination_bucket"] = od.apply(lambda r: destination_bucket(r["dest_sido"], r["dest_sgg"]), axis=1)

    bucket = (
        od.groupby(["origin_dong", "destination_bucket"], as_index=False)["n"].sum()
        .sort_values(["origin_dong", "n"], ascending=[True, False])
    )
    total = bucket.groupby("origin_dong", as_index=False)["n"].sum().rename(columns={"n": "origin_total_outflow"})
    bucket = bucket.merge(total, on="origin_dong", how="left")
    bucket["bucket_share"] = bucket["n"] / bucket["origin_total_outflow"]

    profile = (
        bucket.sort_values(["origin_dong", "bucket_share"], ascending=[True, False])
        .drop_duplicates("origin_dong")
        [["origin_dong", "destination_bucket", "bucket_share", "origin_total_outflow"]]
        .rename(columns={"destination_bucket": "top_destination_bucket", "bucket_share": "top_bucket_share"})
    )

    bucket.to_csv(PROCESSED / "od_destination_clusters.csv", index=False, encoding="utf-8-sig")
    profile.to_csv(PROCESSED / "od_destination_profiles_by_dong.csv", index=False, encoding="utf-8-sig")
    return bucket, profile


def build_intra_cluster_views() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    intra = pd.read_csv(PROCESSED / "od_youth_intra_seongnam_dong.csv")
    intra["origin_cluster"] = intra["origin_dong"].map(cluster_from_dong)
    intra["dest_cluster"] = intra["dest_dong"].map(cluster_from_dong)

    flows = (
        intra.groupby(["origin_cluster", "dest_cluster"], as_index=False)["n"].sum().sort_values("n", ascending=False)
    )
    flows.to_csv(PROCESSED / "od_intra_cluster_flows_2024.csv", index=False, encoding="utf-8-sig")

    # Top inter-cluster pairs for readable table.
    top_pairs = flows[flows["origin_cluster"] != flows["dest_cluster"]].head(40).copy()
    top_pairs.to_csv(PROCESSED / "od_intra_cluster_top_pairs_2024.csv", index=False, encoding="utf-8-sig")

    # Top-12 cluster matrix for readable heatmap.
    cluster_weight = pd.concat(
        [
            flows.groupby("origin_cluster", as_index=False)["n"].sum().rename(columns={"origin_cluster": "dong_cluster"}),
            flows.groupby("dest_cluster", as_index=False)["n"].sum().rename(columns={"dest_cluster": "dong_cluster"}),
        ],
        ignore_index=True,
    ).groupby("dong_cluster", as_index=False)["n"].sum()
    top12 = cluster_weight.sort_values("n", ascending=False).head(12)["dong_cluster"].tolist()
    matrix = flows[flows["origin_cluster"].isin(top12) & flows["dest_cluster"].isin(top12)].copy()
    matrix.to_csv(PROCESSED / "od_intra_cluster_matrix_top12_2024.csv", index=False, encoding="utf-8-sig")
    return flows, top_pairs, matrix


def build_policy_priority_matrix() -> tuple[pd.DataFrame, dict[str, object], pd.DataFrame]:
    base = pd.read_csv(PROCESSED / "complaint_mobility_join_2024.csv")
    panel = pd.read_csv(PROCESSED / "cluster_month_panel_2024.csv")
    intra = pd.read_csv(PROCESSED / "od_intra_seongnam_dong.csv") if (PROCESSED / "od_intra_seongnam_dong.csv").exists() else pd.read_csv(PROCESSED / "od_youth_intra_seongnam_dong.csv")

    panel_metrics = (
        panel.groupby("dong_cluster", as_index=False)
        .agg(
            negative_month_share=("negative_net_flag", "mean"),
            avg_monthly_outflow_rate=("monthly_outflow_rate", "mean"),
            monthly_outflow_volatility=("monthly_outflow_rate", "std"),
            months_observed=("month", "nunique"),
        )
        .fillna({"monthly_outflow_volatility": 0.0})
    )

    intra["origin_cluster"] = intra["origin_dong"].map(cluster_from_dong)
    internal_moves = intra.groupby("origin_cluster", as_index=False)["n"].sum().rename(
        columns={"origin_cluster": "dong_cluster", "n": "internal_move_outflow_count"}
    )

    out = base.merge(panel_metrics, on="dong_cluster", how="left").merge(internal_moves, on="dong_cluster", how="left")
    out["internal_move_outflow_count"] = out["internal_move_outflow_count"].fillna(0)
    out["internal_moves_per_1000_youth"] = np.where(
        out["youth_pop"] > 0,
        out["internal_move_outflow_count"] / out["youth_pop"] * 1000.0,
        np.nan,
    )

    q_out = float(out["youth_outflow_rate"].quantile(0.70))
    q_neg = float(out["negative_month_share"].quantile(0.70))
    q_comp = float(out["complaints_per_1000_totalpop"].quantile(0.60))

    out["flag_high_outflow"] = out["youth_outflow_rate"] >= q_out
    out["flag_persistent_outflow"] = out["negative_month_share"] >= q_neg
    out["flag_high_friction"] = out["complaints_per_1000_totalpop"] >= q_comp
    out["flag_count"] = (
        out["flag_high_outflow"].astype(int)
        + out["flag_persistent_outflow"].astype(int)
        + out["flag_high_friction"].astype(int)
    )

    def tier_from_flags(n_flag: int) -> str:
        if n_flag == 3:
            return "A_즉시개입"
        if n_flag == 2:
            return "B_우선개입"
        if n_flag == 1:
            return "C_모니터링"
        return "D_유지"

    out["policy_tier"] = out["flag_count"].map(tier_from_flags)

    for col in [
        "youth_outflow_rate",
        "negative_month_share",
        "complaints_per_1000_totalpop",
        "internal_moves_per_1000_youth",
    ]:
        mean = out[col].mean()
        std = out[col].std(ddof=0)
        out[f"z_{col}"] = 0.0 if std == 0 else (out[col] - mean) / std

    out["priority_score"] = (
        0.45 * out["z_youth_outflow_rate"]
        + 0.25 * out["z_negative_month_share"]
        + 0.20 * out["z_complaints_per_1000_totalpop"]
        + 0.10 * out["z_internal_moves_per_1000_youth"]
    )

    def reason_text(r: pd.Series) -> str:
        reasons: list[str] = []
        if bool(r["flag_high_outflow"]):
            reasons.append("유출률 상위")
        if bool(r["flag_persistent_outflow"]):
            reasons.append("월별 순유출 지속")
        if bool(r["flag_high_friction"]):
            reasons.append("민원강도 높음")
        return ", ".join(reasons) if reasons else "위험 신호 낮음"

    out["tier_reason"] = out.apply(reason_text, axis=1)

    cols = [
        "dong_cluster",
        "policy_tier",
        "tier_reason",
        "priority_score",
        "youth_outflow_rate",
        "negative_month_share",
        "avg_monthly_outflow_rate",
        "monthly_outflow_volatility",
        "complaints_per_1000_totalpop",
        "internal_moves_per_1000_youth",
        "complaint_count",
        "youth_pop",
        "total_pop",
        "months_observed",
        "flag_high_outflow",
        "flag_persistent_outflow",
        "flag_high_friction",
    ]
    result = out[cols].sort_values(["policy_tier", "priority_score"], ascending=[True, False])
    result.to_csv(PROCESSED / "policy_priority_matrix_2024.csv", index=False, encoding="utf-8-sig")

    criteria = {
        "tier_rule": {
            "A_즉시개입": "세 가지 위험 플래그 모두 충족",
            "B_우선개입": "세 가지 중 두 개 충족",
            "C_모니터링": "세 가지 중 한 개 충족",
            "D_유지": "세 가지 모두 미충족",
        },
        "thresholds": {
            "youth_outflow_rate_q70": q_out,
            "negative_month_share_q70": q_neg,
            "complaints_per_1000_totalpop_q60": q_comp,
        },
        "variables": {
            "youth_outflow_rate": "6개월 누적 청년 순유출률(%)",
            "negative_month_share": "관측월 중 순유출(순이동<0) 발생 비중",
            "complaints_per_1000_totalpop": "연간 총인구 1천명당 민원 건수",
            "internal_moves_per_1000_youth": "청년 1천명당 성남 내부 동간 이동량",
        },
        "priority_score_weights": {
            "youth_outflow_rate": 0.45,
            "negative_month_share": 0.25,
            "complaints_per_1000_totalpop": 0.20,
            "internal_moves_per_1000_youth": 0.10,
        },
    }
    with (PROCESSED / "policy_tier_criteria_2024.json").open("w", encoding="utf-8") as f:
        json.dump(criteria, f, ensure_ascii=False, indent=2)

    rel_rows = []
    for var in [
        "negative_month_share",
        "complaints_per_1000_totalpop",
        "internal_moves_per_1000_youth",
        "monthly_outflow_volatility",
    ]:
        sub = out[[var, "youth_outflow_rate"]].dropna()
        if len(sub) < 5 or sub[var].nunique() < 2 or sub["youth_outflow_rate"].nunique() < 2:
            continue
        p = pearsonr(sub[var], sub["youth_outflow_rate"])
        s = spearmanr(sub[var], sub["youth_outflow_rate"], nan_policy="omit")
        rel_rows.append(
            {
                "x_variable": var,
                "y_variable": "youth_outflow_rate",
                "n": int(len(sub)),
                "pearson_r": float(p.statistic),
                "pearson_p": float(p.pvalue),
                "spearman_r": float(s.statistic),
                "spearman_p": float(s.pvalue),
            }
        )
    relations = pd.DataFrame(rel_rows).sort_values("spearman_p", ascending=True)
    relations.to_csv(PROCESSED / "stats_policy_relations_2024.csv", index=False, encoding="utf-8-sig")
    return result, criteria, relations


def build_newold_complaint_integration_outputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    base = pd.read_csv(PROCESSED / "complaint_mobility_join_2024.csv")
    _require_columns(
        base,
        [
            "dong_cluster",
            "youth_in",
            "youth_out",
            "youth_net",
            "youth_pop",
            "youth_outflow_rate",
            "total_pop",
            "complaint_count",
            "complaints_per_1000_totalpop",
        ],
        "complaint_mobility_join_2024.csv",
    )

    axis_map = base[
        [
            "dong_cluster",
            "youth_in",
            "youth_out",
            "youth_net",
            "youth_pop",
            "youth_outflow_rate",
            "total_pop",
            "complaint_count",
            "complaints_per_1000_totalpop",
        ]
    ].copy()
    axis_map["axis_group"] = axis_map["dong_cluster"].map(axis_group_from_cluster)
    axis_map["axis_group_label"] = axis_map["axis_group"].map(AXIS_GROUP_LABEL)
    axis_map["axis_group_order"] = axis_map["axis_group"].map(AXIS_GROUP_ORDER).astype(int)
    axis_map["outflow_rate_rank_desc"] = axis_map["youth_outflow_rate"].rank(ascending=False, method="dense").astype(int)
    axis_map["complaint_intensity_rank_desc"] = axis_map["complaints_per_1000_totalpop"].rank(
        ascending=False,
        method="dense",
    ).astype(int)
    axis_map = axis_map.sort_values(["axis_group_order", "dong_cluster"]).reset_index(drop=True)
    axis_map.to_csv(PROCESSED / "policy_newold_axis_mapping_by_cluster_2024.csv", index=False, encoding="utf-8-sig")

    summary_rows: list[dict[str, object]] = []
    for axis_group, g in axis_map.groupby("axis_group", sort=False):
        total_pop_sum = float(g["total_pop"].sum())
        youth_pop_sum = float(g["youth_pop"].sum())
        complaint_count_sum = float(g["complaint_count"].sum())
        youth_out_sum = float(g["youth_out"].sum())
        youth_in_sum = float(g["youth_in"].sum())
        summary_rows.append(
            {
                "axis_group": axis_group,
                "axis_group_label": AXIS_GROUP_LABEL[axis_group],
                "axis_group_order": AXIS_GROUP_ORDER[axis_group],
                "cluster_count": int(g["dong_cluster"].nunique()),
                "total_pop_sum": total_pop_sum,
                "youth_pop_sum": youth_pop_sum,
                "youth_in_sum": youth_in_sum,
                "youth_out_sum": youth_out_sum,
                "youth_net_sum": float(g["youth_net"].sum()),
                "complaint_count_sum": complaint_count_sum,
                "complaints_per_1000_totalpop_weighted": (
                    complaint_count_sum / total_pop_sum * 1000.0 if total_pop_sum > 0 else np.nan
                ),
                "youth_outflow_rate_weighted": ((youth_out_sum - youth_in_sum) / youth_pop_sum * 100.0 if youth_pop_sum > 0 else np.nan),
                "youth_outflow_rate_mean": float(g["youth_outflow_rate"].mean()),
                "youth_outflow_rate_median": float(g["youth_outflow_rate"].median()),
                "complaints_per_1000_totalpop_mean": float(g["complaints_per_1000_totalpop"].mean()),
                "complaints_per_1000_totalpop_median": float(g["complaints_per_1000_totalpop"].median()),
            }
        )
    group_summary = pd.DataFrame(summary_rows).sort_values(["axis_group_order", "axis_group"]).reset_index(drop=True)
    group_summary.to_csv(PROCESSED / "policy_newold_group_comparison_2024.csv", index=False, encoding="utf-8-sig")

    topic = pd.read_csv(PROCESSED / "complaint_topic_group_by_cluster_2024.csv")
    _require_columns(topic, ["dong_cluster", "topic_group", "complaint_count"], "complaint_topic_group_by_cluster_2024.csv")
    topic_axis = topic.merge(axis_map[["dong_cluster", "axis_group"]], on="dong_cluster", how="inner")
    topic_axis = topic_axis[topic_axis["axis_group"].isin(["new_redevelopment", "old_stagnant"])].copy()

    if topic_axis.empty:
        topic_compare = pd.DataFrame(
            columns=[
                "topic_group",
                "new_redevelopment_complaint_count",
                "new_redevelopment_topic_share",
                "old_stagnant_complaint_count",
                "old_stagnant_topic_share",
                "share_diff_new_minus_old",
                "count_diff_new_minus_old",
                "count_ratio_new_over_old",
            ]
        )
    else:
        topic_by_group = (
            topic_axis.groupby(["axis_group", "topic_group"], as_index=False)["complaint_count"]
            .sum()
            .sort_values(["axis_group", "topic_group"])
        )
        totals = topic_by_group.groupby("axis_group", as_index=False)["complaint_count"].sum().rename(
            columns={"complaint_count": "axis_group_total_complaints"}
        )
        topic_by_group = topic_by_group.merge(totals, on="axis_group", how="left")
        topic_by_group["topic_share"] = np.where(
            topic_by_group["axis_group_total_complaints"] > 0,
            topic_by_group["complaint_count"] / topic_by_group["axis_group_total_complaints"],
            np.nan,
        )

        pivot_count = topic_by_group.pivot(index="topic_group", columns="axis_group", values="complaint_count").fillna(0)
        pivot_share = topic_by_group.pivot(index="topic_group", columns="axis_group", values="topic_share").fillna(0.0)
        topic_compare = pd.DataFrame(
            {
                "topic_group": pivot_count.index,
                "new_redevelopment_complaint_count": pivot_count.get("new_redevelopment", pd.Series(0, index=pivot_count.index)).astype(int),
                "new_redevelopment_topic_share": pivot_share.get("new_redevelopment", pd.Series(0.0, index=pivot_share.index)).astype(float),
                "old_stagnant_complaint_count": pivot_count.get("old_stagnant", pd.Series(0, index=pivot_count.index)).astype(int),
                "old_stagnant_topic_share": pivot_share.get("old_stagnant", pd.Series(0.0, index=pivot_share.index)).astype(float),
            }
        ).reset_index(drop=True)
        topic_compare["share_diff_new_minus_old"] = (
            topic_compare["new_redevelopment_topic_share"] - topic_compare["old_stagnant_topic_share"]
        )
        topic_compare["count_diff_new_minus_old"] = (
            topic_compare["new_redevelopment_complaint_count"] - topic_compare["old_stagnant_complaint_count"]
        )
        topic_compare["count_ratio_new_over_old"] = np.where(
            topic_compare["old_stagnant_complaint_count"] > 0,
            topic_compare["new_redevelopment_complaint_count"] / topic_compare["old_stagnant_complaint_count"],
            np.nan,
        )
        topic_compare = topic_compare.sort_values(
            ["share_diff_new_minus_old", "topic_group"],
            key=lambda s: s.abs() if s.name == "share_diff_new_minus_old" else s,
            ascending=[False, True],
        ).reset_index(drop=True)

    topic_compare.to_csv(PROCESSED / "policy_newold_topic_group_comparison_2024.csv", index=False, encoding="utf-8-sig")
    return axis_map, group_summary, topic_compare


def main() -> None:
    bucket, profile = build_destination_cluster_outputs()
    flows, top_pairs, matrix = build_intra_cluster_views()
    priority, criteria, relations = build_policy_priority_matrix()
    axis_map, group_summary, topic_compare = build_newold_complaint_integration_outputs()

    tier_counts = priority["policy_tier"].value_counts().to_dict()
    urgent = priority[priority["policy_tier"] == "A_즉시개입"]["dong_cluster"].tolist()
    summary = {
        "destination_cluster_rows": int(len(bucket)),
        "destination_profile_rows": int(len(profile)),
        "intra_cluster_flow_rows": int(len(flows)),
        "intra_cluster_top_pairs_rows": int(len(top_pairs)),
        "intra_cluster_matrix_top12_rows": int(len(matrix)),
        "priority_rows": int(len(priority)),
        "policy_relation_rows": int(len(relations)),
        "newold_axis_map_rows": int(len(axis_map)),
        "newold_group_summary_rows": int(len(group_summary)),
        "newold_topic_comparison_rows": int(len(topic_compare)),
        "tier_counts": tier_counts,
        "urgent_clusters": urgent,
        "criteria_file": "policy_tier_criteria_2024.json",
    }
    with (PROCESSED / "policy_focus_summary_2024.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"[done] od_destination_clusters.csv: {len(bucket)} rows")
    print(f"[done] od_destination_profiles_by_dong.csv: {len(profile)} rows")
    print(f"[done] od_intra_cluster_flows_2024.csv: {len(flows)} rows")
    print(f"[done] od_intra_cluster_top_pairs_2024.csv: {len(top_pairs)} rows")
    print(f"[done] od_intra_cluster_matrix_top12_2024.csv: {len(matrix)} rows")
    print(f"[done] policy_priority_matrix_2024.csv: {len(priority)} rows")
    print(f"[done] policy_tier_criteria_2024.json")
    print(f"[done] stats_policy_relations_2024.csv: {len(relations)} rows")
    print(f"[done] policy_newold_axis_mapping_by_cluster_2024.csv: {len(axis_map)} rows")
    print(f"[done] policy_newold_group_comparison_2024.csv: {len(group_summary)} rows")
    print(f"[done] policy_newold_topic_group_comparison_2024.csv: {len(topic_compare)} rows")


if __name__ == "__main__":
    main()
