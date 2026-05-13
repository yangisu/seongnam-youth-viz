from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd

from common import PROCESSED, read_csv_smart


SEOUL_GANGNAM3 = {"강남구", "서초구", "송파구"}
GYEONGGI_NEAR = {"광주시", "하남시", "용인시 수지구", "용인시 기흥구", "수원시 영통구"}

AXIS_GROUP_ORDER = {"new_redevelopment": 0, "old_stagnant": 1, "mixed_other": 2}


def _cluster_from_dong(dong: str) -> str:
    if not dong:
        return ""
    m = re.match(r"^(.+?)[1-4]동?$", str(dong).strip())
    return f"{m.group(1)}동" if m else str(dong).strip()


def _destination_bucket(dest_sido: str, dest_sgg: str) -> str:
    sido = str(dest_sido).strip()
    sgg = str(dest_sgg).strip()
    if sido == "서울특별시" and sgg in SEOUL_GANGNAM3:
        return "seoul_gangnam3"
    if sido == "서울특별시":
        return "seoul_other"
    if sido == "경기도" and sgg in GYEONGGI_NEAR:
        return "gyeonggi_near_core"
    if sido == "경기도":
        return "gyeonggi_other"
    return "outside_capital_region"


def _require_columns(df: pd.DataFrame, required: list[str], name: str) -> None:
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"{name} is missing required columns: {missing}")


def _find_input_path(candidates: list[str]) -> Path:
    for name in candidates:
        p = PROCESSED / name
        if p.exists():
            return p
    for name in candidates:
        matched = sorted(PROCESSED.glob(name))
        if matched:
            return matched[0]
    raise FileNotFoundError(f"Cannot find input from candidates: {candidates}")


def _concentration_summary(df: pd.DataFrame, group_col: str, item_col: str, value_col: str) -> pd.DataFrame:
    g = df[[group_col, item_col, value_col]].copy()
    grouped = g.groupby([group_col, item_col], as_index=False)[value_col].sum()
    grouped = grouped[grouped[value_col] > 0].copy()
    total = grouped.groupby(group_col, as_index=False)[value_col].sum().rename(columns={value_col: "group_total"})
    grouped = grouped.merge(total, on=group_col, how="left")
    grouped["share"] = grouped[value_col] / grouped["group_total"]

    rows: list[dict[str, object]] = []
    for grp, sub in grouped.groupby(group_col):
        share = sub["share"].to_numpy(dtype=float)
        top = sub.sort_values("share", ascending=False).iloc[0]
        hhi = float(np.sum(np.square(share)))
        entropy = float(-np.sum(share * np.log(share)))
        rows.append(
            {
                group_col: grp,
                "group_total": float(sub["group_total"].iloc[0]),
                "category_count": int(len(sub)),
                "top_category": str(top[item_col]),
                "top_share": float(top["share"]),
                "hhi": hhi,
                "entropy": entropy,
                "effective_category_count": float(np.exp(entropy)),
            }
        )
    return pd.DataFrame(rows)


def analyze_axis_destination_buckets(axis_map: pd.DataFrame, od_outside: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    od = od_outside.copy()
    od["dong_cluster"] = od["origin_dong"].map(_cluster_from_dong)
    od["destination_bucket"] = od.apply(lambda r: _destination_bucket(r["dest_sido"], r["dest_sgg"]), axis=1)

    merged = od.merge(axis_map[["dong_cluster", "axis_group", "axis_group_label", "axis_group_order"]], on="dong_cluster", how="inner")
    mix = merged.groupby(["axis_group", "axis_group_label", "axis_group_order", "destination_bucket"], as_index=False)["n"].sum()
    mix = mix.rename(columns={"n": "outflow_n"}).sort_values(["axis_group_order", "destination_bucket"]).reset_index(drop=True)
    total = mix.groupby(["axis_group", "axis_group_label", "axis_group_order"], as_index=False)["outflow_n"].sum()
    total = total.rename(columns={"outflow_n": "group_total_outflow"})
    mix = mix.merge(total, on=["axis_group", "axis_group_label", "axis_group_order"], how="left")
    mix["bucket_share"] = mix["outflow_n"] / mix["group_total_outflow"]

    summary = _concentration_summary(mix, "axis_group", "destination_bucket", "outflow_n")
    label_map = mix[["axis_group", "axis_group_label", "axis_group_order"]].drop_duplicates()
    summary = summary.merge(label_map, on="axis_group", how="left")
    summary["axis_group_order"] = summary["axis_group_order"].fillna(summary["axis_group"].map(AXIS_GROUP_ORDER)).astype(int)
    summary = summary.sort_values("axis_group_order").reset_index(drop=True)

    mix.to_csv(PROCESSED / "axis_destination_bucket_mix_by_group.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(PROCESSED / "axis_destination_bucket_concentration_by_group.csv", index=False, encoding="utf-8-sig")
    return mix, summary


def analyze_axis_topic_concentration(axis_map: pd.DataFrame, topic_group: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    merged = topic_group.merge(
        axis_map[["dong_cluster", "axis_group", "axis_group_label", "axis_group_order"]],
        on="dong_cluster",
        how="inner",
    )
    mix = merged.groupby(["axis_group", "axis_group_label", "axis_group_order", "topic_group"], as_index=False)["complaint_count"].sum()
    mix = mix.sort_values(["axis_group_order", "topic_group"]).reset_index(drop=True)
    total = mix.groupby(["axis_group", "axis_group_label", "axis_group_order"], as_index=False)["complaint_count"].sum()
    total = total.rename(columns={"complaint_count": "group_total_complaint"})
    mix = mix.merge(total, on=["axis_group", "axis_group_label", "axis_group_order"], how="left")
    mix["topic_share"] = mix["complaint_count"] / mix["group_total_complaint"]

    summary = _concentration_summary(mix, "axis_group", "topic_group", "complaint_count")
    label_map = mix[["axis_group", "axis_group_label", "axis_group_order"]].drop_duplicates()
    summary = summary.merge(label_map, on="axis_group", how="left")
    summary["axis_group_order"] = summary["axis_group_order"].fillna(summary["axis_group"].map(AXIS_GROUP_ORDER)).astype(int)
    summary = summary.sort_values("axis_group_order").reset_index(drop=True)

    mix.to_csv(PROCESSED / "axis_topic_mix_by_group.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(PROCESSED / "axis_topic_concentration_by_group.csv", index=False, encoding="utf-8-sig")
    return mix, summary


def main() -> None:
    axis_map_path = _find_input_path(["policy_newold_axis_mapping_by_cluster_2024.csv"])
    od_outside_path = _find_input_path(["od_youth_seongnam_dong_to_outside.csv"])
    topic_group_path = _find_input_path(["complaint_topic_group_by_cluster_2024.csv"])

    axis_map = read_csv_smart(axis_map_path)
    od_outside = read_csv_smart(od_outside_path)
    topic_group = read_csv_smart(topic_group_path)

    _require_columns(
        axis_map,
        ["dong_cluster", "axis_group", "axis_group_label", "axis_group_order"],
        axis_map_path.name,
    )
    _require_columns(od_outside, ["origin_dong", "dest_sido", "dest_sgg", "n"], od_outside_path.name)
    _require_columns(
        topic_group,
        ["dong_cluster", "topic_group", "complaint_count"],
        topic_group_path.name,
    )

    mix_dest, sum_dest = analyze_axis_destination_buckets(axis_map, od_outside)
    mix_topic, sum_topic = analyze_axis_topic_concentration(axis_map, topic_group)

    print("Axis additional analysis complete.")
    print(f"- destination rows: {len(mix_dest)} / summary rows: {len(sum_dest)}")
    print(f"- topic rows: {len(mix_topic)} / summary rows: {len(sum_topic)}")


if __name__ == "__main__":
    main()
