from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from common import PROCESSED, read_csv_smart


def _require_columns(df: pd.DataFrame, required: list[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def _to_float(v: object) -> float:
    return float(v) if pd.notna(v) else float("nan")


def _confidence_from_strength(value: float, thresholds: tuple[float, float]) -> str:
    strong, medium = thresholds
    if pd.isna(value):
        return "low"
    if value >= strong:
        return "high"
    if value >= medium:
        return "medium"
    return "low"


def build_claim_chain() -> tuple[pd.DataFrame, dict[str, object]]:
    group = read_csv_smart(PROCESSED / "policy_newold_group_comparison_2024.csv")
    topic = read_csv_smart(PROCESSED / "policy_newold_topic_group_comparison_2024.csv")
    rel = read_csv_smart(PROCESSED / "stats_policy_relations_2024.csv")
    priority = read_csv_smart(PROCESSED / "policy_priority_matrix_2024.csv")

    _require_columns(
        group,
        [
            "axis_group",
            "axis_group_label",
            "complaints_per_1000_totalpop_weighted",
            "youth_outflow_rate_weighted",
            "complaint_count_sum",
            "cluster_count",
        ],
        "policy_newold_group_comparison_2024.csv",
    )
    _require_columns(
        topic,
        [
            "topic_group",
            "new_redevelopment_topic_share",
            "old_stagnant_topic_share",
            "share_diff_new_minus_old",
        ],
        "policy_newold_topic_group_comparison_2024.csv",
    )
    _require_columns(
        rel,
        ["x_variable", "y_variable", "spearman_r", "spearman_p", "n"],
        "stats_policy_relations_2024.csv",
    )
    _require_columns(
        priority,
        ["policy_tier", "dong_cluster", "priority_score"],
        "policy_priority_matrix_2024.csv",
    )

    new_row = group[group["axis_group"] == "new_redevelopment"]
    old_row = group[group["axis_group"] == "old_stagnant"]
    if new_row.empty or old_row.empty:
        raise ValueError("Both 'new_redevelopment' and 'old_stagnant' rows are required in group comparison data.")
    new_row = new_row.iloc[0]
    old_row = old_row.iloc[0]

    new_complaint = _to_float(new_row["complaints_per_1000_totalpop_weighted"])
    old_complaint = _to_float(old_row["complaints_per_1000_totalpop_weighted"])
    new_outflow = _to_float(new_row["youth_outflow_rate_weighted"])
    old_outflow = _to_float(old_row["youth_outflow_rate_weighted"])

    complaint_ratio = old_complaint / new_complaint if new_complaint > 0 else np.nan
    outflow_gap = old_outflow - new_outflow
    outflow_ratio = old_outflow / abs(new_outflow) if new_outflow != 0 else np.nan

    top_topic = topic.iloc[0]
    top_topic_name = str(top_topic["topic_group"])
    top_topic_gap = _to_float(top_topic["share_diff_new_minus_old"])

    rel_target = rel[(rel["x_variable"] == "negative_month_share") & (rel["y_variable"] == "youth_outflow_rate")]
    if rel_target.empty:
        raise ValueError("Required relation row for negative_month_share -> youth_outflow_rate is missing.")
    rel_target = rel_target.iloc[0]
    rel_r = _to_float(rel_target["spearman_r"])
    rel_p = _to_float(rel_target["spearman_p"])
    rel_n = int(rel_target["n"])

    tier_counts = priority["policy_tier"].value_counts()
    urgent_count = int(tier_counts.get("A_즉시개입", 0))
    total_cluster_count = int(priority["dong_cluster"].nunique())
    urgent_share = urgent_count / total_cluster_count if total_cluster_count > 0 else np.nan

    evidence_rows = [
        {
            "claim_id": "C1",
            "claim_text": "노후·정체 권역의 총인구 1천명당 민원강도는 신축·재정비 대비 높다.",
            "metric_name": "old_vs_new_complaint_intensity_ratio",
            "metric_value": complaint_ratio,
            "formula": "complaints_per_1000_totalpop_weighted(old_stagnant) / complaints_per_1000_totalpop_weighted(new_redevelopment)",
            "interpretation": "1보다 크면 노후·정체 권역 민원강도가 더 높다는 의미.",
            "limitation": "축 분류는 행정동 묶음 기반이며, 민원은 청년 한정 지표가 아니다.",
        },
        {
            "claim_id": "C2",
            "claim_text": "노후·정체 권역은 신축·재정비 대비 순유출 압력이 더 크다.",
            "metric_name": "old_minus_new_weighted_outflow_rate_pctp",
            "metric_value": outflow_gap,
            "formula": "youth_outflow_rate_weighted(old_stagnant) - youth_outflow_rate_weighted(new_redevelopment)",
            "interpretation": "값이 클수록 노후·정체 쪽 순유출 압력이 상대적으로 큼.",
            "limitation": "가중 순유출률은 집계 지표로, 개별 동의 이질성을 평균화한다.",
        },
        {
            "claim_id": "C3",
            "claim_text": "신축 vs 노후의 민원 구성 차이에서 핵심 격차 주제는 상위 1개 토픽으로 설명 가능하다.",
            "metric_name": "top_topic_share_gap_new_minus_old",
            "metric_value": top_topic_gap,
            "formula": "max_abs(share_diff_new_minus_old) from policy_newold_topic_group_comparison_2024",
            "interpretation": f"절대값이 클수록 양 축의 민원 포트폴리오 차이가 큼. 현재 상위 주제: {top_topic_name}.",
            "limitation": "토픽 분류 규칙 기반이라 문장 맥락 손실 가능성이 있다.",
        },
        {
            "claim_id": "C4",
            "claim_text": "월별 순유출 지속성(negative month share)과 연간 순유출률은 강한 양(+)의 연관을 보인다.",
            "metric_name": "spearman_r_negative_month_share_vs_outflow_rate",
            "metric_value": rel_r,
            "formula": "Spearman r(negative_month_share, youth_outflow_rate)",
            "interpretation": "1에 가까울수록 단조 증가 연관이 강함.",
            "limitation": f"상관은 인과를 보장하지 않으며 표본 수는 n={rel_n}, p={rel_p:.4g}.",
        },
        {
            "claim_id": "C5",
            "claim_text": "즉시개입(A) 권역 비율은 전체 정책 타겟 중 무시하기 어려운 규모다.",
            "metric_name": "urgent_tier_share",
            "metric_value": urgent_share,
            "formula": "count(policy_tier == 'A_즉시개입') / unique_cluster_count",
            "interpretation": "값이 클수록 단기 개입 필요 권역 비중이 높음.",
            "limitation": "등급은 분위수 기반 규칙이며 임계값 선택에 민감할 수 있다.",
        },
    ]
    evidence = pd.DataFrame(evidence_rows)
    evidence = evidence.sort_values("claim_id").reset_index(drop=True)
    evidence.to_csv(PROCESSED / "claim_chain_evidence_table.csv", index=False, encoding="utf-8-sig")

    confidence_items = [
        {"claim_id": "C1", "confidence": _confidence_from_strength(complaint_ratio, (1.5, 1.2))},
        {"claim_id": "C2", "confidence": _confidence_from_strength(outflow_gap, (4.0, 2.0))},
        {"claim_id": "C3", "confidence": _confidence_from_strength(abs(top_topic_gap), (0.02, 0.01))},
        {"claim_id": "C4", "confidence": _confidence_from_strength(abs(rel_r), (0.7, 0.4))},
        {"claim_id": "C5", "confidence": _confidence_from_strength(urgent_share, (0.30, 0.15))},
    ]
    score_map = {"high": 3, "medium": 2, "low": 1}
    mean_score = float(np.mean([score_map[item["confidence"]] for item in confidence_items]))
    overall_confidence = "high" if mean_score >= 2.6 else ("medium" if mean_score >= 1.8 else "low")

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_confidence": overall_confidence,
        "key_conclusions": [
            {
                "claim_id": "C1",
                "text": "노후·정체 권역의 민원강도는 신축·재정비 대비 높다.",
                "metric_name": "old_vs_new_complaint_intensity_ratio",
                "metric_value": complaint_ratio,
                "confidence": next(item["confidence"] for item in confidence_items if item["claim_id"] == "C1"),
            },
            {
                "claim_id": "C2",
                "text": "노후·정체 권역은 신축·재정비 대비 순유출 압력이 더 크다.",
                "metric_name": "old_minus_new_weighted_outflow_rate_pctp",
                "metric_value": outflow_gap,
                "confidence": next(item["confidence"] for item in confidence_items if item["claim_id"] == "C2"),
            },
            {
                "claim_id": "C4",
                "text": "월별 순유출 지속성과 연간 순유출률 사이에는 강한 양의 연관이 있다.",
                "metric_name": "spearman_r_negative_month_share_vs_outflow_rate",
                "metric_value": rel_r,
                "confidence": next(item["confidence"] for item in confidence_items if item["claim_id"] == "C4"),
            },
        ],
        "confidence_breakdown": confidence_items,
        "cautions": [
            "민원 데이터는 청년 집단 전용 지표가 아니므로 구조적 불편의 대리신호로 해석해야 한다.",
            "상관 분석은 인과 추론이 아니며 정책 실험/외생 변수 검증이 추가로 필요하다.",
            "축 분류 및 정책 등급 규칙은 임계값 변화에 따라 결과가 일부 달라질 수 있다.",
        ],
        "snapshot_metrics": {
            "old_vs_new_complaint_intensity_ratio": complaint_ratio,
            "old_minus_new_weighted_outflow_rate_pctp": outflow_gap,
            "urgent_tier_share": urgent_share,
            "old_weighted_outflow_rate": old_outflow,
            "new_weighted_outflow_rate": new_outflow,
            "old_over_abs_new_outflow_ratio": outflow_ratio,
            "top_topic_group_by_share_gap": top_topic_name,
            "top_topic_share_gap_new_minus_old": top_topic_gap,
            "spearman_r_negative_month_share_vs_outflow_rate": rel_r,
            "spearman_p_negative_month_share_vs_outflow_rate": rel_p,
            "urgent_cluster_count": urgent_count,
            "cluster_count": total_cluster_count,
        },
    }

    with (PROCESSED / "claim_chain_summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return evidence, summary


def main() -> None:
    evidence, summary = build_claim_chain()
    print(f"[done] claim_chain_evidence_table.csv: {len(evidence)} rows")
    print("[done] claim_chain_summary.json")
    print(f"[snapshot] overall_confidence={summary['overall_confidence']}")


if __name__ == "__main__":
    main()
