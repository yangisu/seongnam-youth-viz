from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

from common import PROCESSED, SHARED_BY_REGION, SHARED_BY_TYPE, list_real_files

SPP_RE = re.compile(r"\((SPP-\d+-\d+)\)")
LAT_RE = re.compile(r"위도[:：]\s*([0-9.\-]+)")
LON_RE = re.compile(r"경도[:：]\s*([0-9.\-]+)")
GU_DONG_RE = re.compile(r"(분당구|수정구|중원구)\s*([가-힣0-9]+동)")


def clean_text(v: object) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() == "nan" else s


def cluster_from_dong(dong: str) -> str:
    if not dong:
        return ""
    m = re.match(r"^(.+?)[1-4]동$", dong)
    return f"{m.group(1)}동" if m else dong


def parse_date_col(series: pd.Series) -> pd.Series:
    s = series.map(clean_text).replace({"": None, "-": None})
    return pd.to_datetime(s, errors="coerce")


def extract_between(text: str, marker: str) -> str:
    i = text.find(marker)
    if i < 0:
        return ""
    return text[i + len(marker) :].splitlines()[0].strip()


def extract_detail_fields(detail: str) -> dict[str, str]:
    txt = clean_text(detail)
    institution = extract_between(txt, "[처리요청기관]:")
    route = extract_between(txt, "[민원 유입 경로]:")
    address = extract_between(txt, "[사고발생지역]")

    gu = ""
    legal_dong = ""
    m = GU_DONG_RE.search(address or txt)
    if m:
        gu = m.group(1)
        legal_dong = m.group(2)

    lat = ""
    lon = ""
    m_lat = LAT_RE.search(txt)
    m_lon = LON_RE.search(txt)
    if m_lat:
        lat = m_lat.group(1)
    if m_lon:
        lon = m_lon.group(1)

    return {
        "institution": institution,
        "inflow_route": route,
        "address": address,
        "gu": gu,
        "legal_dong": legal_dong,
        "lat": lat,
        "lon": lon,
    }


def classify_topic(title: str, detail: str) -> str:
    txt = f"{clean_text(title)} {clean_text(detail)}"
    rules = [
        ("불법광고물", ["불법광고", "불법 광고", "광고물", "현수막", "입간판", "전단지", "벽보", "광고풍선", "노점"]),
        ("시설노후_파손", ["노후", "파손", "균열", "누수", "침하", "내려앉", "고장", "망가", "시설물불량"]),
        ("생활환경_청결소음", ["소음", "악취", "쓰레기", "무단투기", "흡연", "해충", "오염", "먼지"]),
        ("공원녹지_관리", ["공원", "녹지", "가로수", "수목", "놀이터"]),
        ("불법주정차_횡단보도", ["횡단보도"]),
        ("불법주정차_소화전", ["소화전"]),
        ("불법주정차_교차로", ["교차로 모퉁이", "교차로"]),
        ("불법주정차_인도", ["인도 불법", "인도"]),
        ("불법주정차_버스정류소", ["버스정류소"]),
        ("불법주정차_어린이보호구역", ["어린이보호구역", "스쿨존"]),
        ("불법주정차_장애인구역", ["장애인 전용구역", "장애인전용구역"]),
        ("불법주정차_전기차충전구역", ["친환경차 충전구역", "전기차 충전"]),
        ("보행도로_안전", ["보도블록", "포트홀", "빙판", "제설", "볼라드", "차단봉", "보행", "도로 파손", "신호등", "가로등"]),
        ("교통시설_대중교통", ["지하철", "역 신설", "버스 노선", "정류소", "대중교통", "교통"]),
    ]
    for topic, keys in rules:
        for key in keys:
            if key in txt:
                return topic
    if "불법 주정차" in txt or "주정차" in txt:
        return "불법주정차_기타"
    return "생활불편_기타"


def topic_group_from_topic(topic: str) -> str:
    t = clean_text(topic)
    if t.startswith("불법주정차_"):
        return "불법주정차"
    if t == "불법광고물":
        return "불법광고물"
    if t == "시설노후_파손":
        return "시설노후/파손"
    if t == "보행도로_안전":
        return "보행/도로안전"
    if t == "생활환경_청결소음":
        return "생활환경"
    if t == "교통시설_대중교통":
        return "교통서비스"
    if t == "공원녹지_관리":
        return "공원/녹지"
    return "기타"


def load_type_events_2024() -> tuple[pd.DataFrame, dict[str, object]]:
    files = list_real_files(SHARED_BY_TYPE, "*.xlsx")
    if not files:
        raise FileNotFoundError(f"No xlsx files in {SHARED_BY_TYPE}")

    chunks: list[pd.DataFrame] = []
    stats: list[dict[str, object]] = []

    for path in files:
        raw = pd.read_excel(path)
        if raw.shape[1] < 6:
            continue
        sub = pd.DataFrame(
            {
                "raw_no": raw.iloc[:, 0],
                "title": raw.iloc[:, 1].map(clean_text),
                "registered_at": parse_date_col(raw.iloc[:, 2]),
                "processed_at": parse_date_col(raw.iloc[:, 3]),
                "type_raw": raw.iloc[:, 4].map(clean_text),
                "detail": raw.iloc[:, 5].map(clean_text),
                "source_file": path.name,
            }
        )
        sub = sub[sub["registered_at"].notna()].copy()
        sub["year"] = sub["registered_at"].dt.year
        sub = sub[sub["year"] == 2024].copy()
        if sub.empty:
            continue
        sub["month"] = sub["registered_at"].dt.strftime("%Y%m")
        chunks.append(sub)
        stats.append(
            {
                "file": path.name,
                "rows": int(len(sub)),
                "min_date": str(sub["registered_at"].min().date()),
                "max_date": str(sub["registered_at"].max().date()),
            }
        )

    if not chunks:
        raise RuntimeError("No 2024 complaint rows parsed from data_by_type")

    out = pd.concat(chunks, ignore_index=True)
    quality = {
        "type_files_total": len(files),
        "type_files_used": len(stats),
        "type_file_stats": stats,
    }
    return out, quality


def enrich_events(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["complaint_id"] = out["title"].str.extract(SPP_RE, expand=False).fillna("")
    out["title_norm"] = out["title"].str.replace(r"^.*?\)\s*", "", regex=True).str.replace(r"\*.*$", "", regex=True).str.strip()

    details = out["detail"].map(extract_detail_fields).apply(pd.Series)
    out = pd.concat([out, details], axis=1)
    out["dong_cluster"] = out["legal_dong"].map(cluster_from_dong)
    out["topic"] = out.apply(lambda r: classify_topic(r["title_norm"], r["detail"]), axis=1)
    out["topic_group"] = out["topic"].map(topic_group_from_topic)

    out["processing_days"] = (out["processed_at"] - out["registered_at"]).dt.days
    out["is_processed"] = out["processed_at"].notna()
    out["is_seongnam_address"] = out["address"].str.contains("성남시", na=False)

    fallback = out["month"] + "|" + out["title_norm"] + "|" + out["address"] + "|" + out["source_file"]
    out["event_key"] = out["complaint_id"].where(out["complaint_id"] != "", fallback)
    out = out.drop_duplicates(subset=["event_key"]).copy()
    return out


def build_region_coverage() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    files = list_real_files(SHARED_BY_REGION, "*.xlsx")
    for path in files:
        parts = path.stem.split("_", 1)
        if len(parts) != 2:
            continue
        month, dong = parts
        if not (month.startswith("2024") and len(month) == 6 and month.isdigit()):
            continue
        rows.append({"month": month, "requested_dong": dong, "file": path.name, "dong_cluster": cluster_from_dong(dong)})
    return pd.DataFrame(rows)


def build_monthly_metrics(events: pd.DataFrame) -> pd.DataFrame:
    out = (
        events[events["dong_cluster"] != ""]
        .groupby(["month", "dong_cluster"], as_index=False)
        .agg(
            complaint_count=("event_key", "count"),
            processed_count=("is_processed", "sum"),
            processing_days_median=("processing_days", "median"),
            parking_count=("topic", lambda s: int(s.astype(str).str.startswith("불법주정차").sum())),
        )
    )
    out["parking_share"] = out["parking_count"] / out["complaint_count"]
    return out


def build_topic_metrics(events: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        events[events["dong_cluster"] != ""]
        .groupby(["dong_cluster", "topic"], as_index=False)
        .agg(complaint_count=("event_key", "count"))
    )
    total = grouped.groupby("dong_cluster", as_index=False)["complaint_count"].sum().rename(columns={"complaint_count": "dong_total"})
    out = grouped.merge(total, on="dong_cluster", how="left")
    out["topic_share"] = out["complaint_count"] / out["dong_total"]
    return out


def build_topic_group_metrics(events: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        events[events["dong_cluster"] != ""]
        .groupby(["dong_cluster", "topic_group"], as_index=False)
        .agg(complaint_count=("event_key", "count"))
    )
    total = grouped.groupby("dong_cluster", as_index=False)["complaint_count"].sum().rename(columns={"complaint_count": "dong_total"})
    out = grouped.merge(total, on="dong_cluster", how="left")
    out["topic_share"] = out["complaint_count"] / out["dong_total"]
    return out


def build_topic_group_month_metrics(events: pd.DataFrame) -> pd.DataFrame:
    grouped = (
        events[events["dong_cluster"] != ""]
        .groupby(["month", "dong_cluster", "topic_group"], as_index=False)
        .agg(complaint_count=("event_key", "count"))
    )
    total = grouped.groupby(["month", "dong_cluster"], as_index=False)["complaint_count"].sum().rename(
        columns={"complaint_count": "month_cluster_total"}
    )
    out = grouped.merge(total, on=["month", "dong_cluster"], how="left")
    out["topic_share"] = out["complaint_count"] / out["month_cluster_total"]
    return out


def build_mobility_join(events: pd.DataFrame) -> pd.DataFrame:
    mig = pd.read_csv(PROCESSED / "youth_migration_by_dong.csv")
    pop = pd.read_csv(PROCESSED / "youth_population_by_dong.csv")

    mig["dong_cluster"] = mig["dong"].astype(str).map(cluster_from_dong)
    mig_cluster = (
        mig.groupby("dong_cluster", as_index=False)
        .agg(
            youth_in=("청년_전입", "sum"),
            youth_out=("청년_전출", "sum"),
            youth_net=("청년_순이동_6m", "sum"),
            youth_pop=("청년_인구", "sum"),
        )
    )
    mig_cluster["youth_outflow_rate"] = (mig_cluster["youth_out"] - mig_cluster["youth_in"]) / mig_cluster["youth_pop"] * 100.0

    pop["dong_cluster"] = pop["dong"].astype(str).map(cluster_from_dong)
    pop_cluster = pop.groupby("dong_cluster", as_index=False).agg(total_pop=("총인구", "sum"), youth_pop_from_popfile=("청년_인구", "sum"))

    comp = (
        events[events["dong_cluster"] != ""]
        .groupby("dong_cluster", as_index=False)
        .agg(
            complaint_count=("event_key", "count"),
            processed_count=("is_processed", "sum"),
            processing_days_median=("processing_days", "median"),
            parking_count=("topic", lambda s: int(s.astype(str).str.startswith("불법주정차").sum())),
        )
    )
    comp["parking_share"] = comp["parking_count"] / comp["complaint_count"]

    merged = mig_cluster.merge(pop_cluster, on="dong_cluster", how="left").merge(comp, on="dong_cluster", how="left")
    for c in ["complaint_count", "processed_count", "parking_count"]:
        merged[c] = merged[c].fillna(0).astype(int)
    merged["parking_share"] = merged["parking_share"].fillna(0.0)

    # Keep legacy metric for backward compatibility, add corrected denominator metric.
    merged["complaints_per_1000_youth_legacy"] = merged["complaint_count"] / merged["youth_pop"] * 1000.0
    merged["complaints_per_1000_totalpop"] = merged["complaint_count"] / merged["total_pop"] * 1000.0
    merged["denominator_note"] = "official_metric=total_pop, legacy_metric=youth_pop"

    return merged.sort_values("youth_outflow_rate", ascending=False)


def build_quality_report(events: pd.DataFrame, type_quality: dict[str, object], region_coverage: pd.DataFrame) -> dict[str, object]:
    quality = {
        **type_quality,
        "events_total": int(len(events)),
        "id_extracted_ratio": float((events["complaint_id"] != "").mean()),
        "address_extracted_ratio": float((events["address"] != "").mean()),
        "dong_extracted_ratio": float((events["legal_dong"] != "").mean()),
        "cluster_ratio": float((events["dong_cluster"] != "").mean()),
        "processed_ratio": float(events["is_processed"].mean()),
        "seongnam_address_ratio": float(events["is_seongnam_address"].mean()),
        "monthly_counts": events["month"].value_counts().sort_index().to_dict(),
        "topic_top20": events["topic"].value_counts().head(20).to_dict(),
        "topic_group_counts": events["topic_group"].value_counts().to_dict(),
        "region_files_2024": int(len(region_coverage)),
        "region_months": sorted(region_coverage["month"].unique().tolist()) if not region_coverage.empty else [],
        "region_unique_requested_dongs": int(region_coverage["requested_dong"].nunique()) if not region_coverage.empty else 0,
        "interpretation_guardrail": "complaint data is treated as contextual friction signal, not youth-only causal evidence",
    }
    return quality


def main() -> None:
    events_raw, type_quality = load_type_events_2024()
    events = enrich_events(events_raw)
    monthly = build_monthly_metrics(events)
    topic = build_topic_metrics(events)
    topic_group = build_topic_group_metrics(events)
    topic_group_month = build_topic_group_month_metrics(events)
    mobility = build_mobility_join(events)
    coverage = build_region_coverage()
    quality = build_quality_report(events, type_quality, coverage)

    events.to_csv(PROCESSED / "complaint_events_2024.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(PROCESSED / "complaint_by_cluster_month_2024.csv", index=False, encoding="utf-8-sig")
    topic.to_csv(PROCESSED / "complaint_topic_by_cluster_2024.csv", index=False, encoding="utf-8-sig")
    topic_group.to_csv(PROCESSED / "complaint_topic_group_by_cluster_2024.csv", index=False, encoding="utf-8-sig")
    topic_group_month.to_csv(PROCESSED / "complaint_topic_group_by_cluster_month_2024.csv", index=False, encoding="utf-8-sig")
    mobility.to_csv(PROCESSED / "complaint_mobility_join_2024.csv", index=False, encoding="utf-8-sig")
    if not coverage.empty:
        coverage.to_csv(PROCESSED / "complaint_region_file_coverage_2024.csv", index=False, encoding="utf-8-sig")
    with (PROCESSED / "complaint_parse_quality_2024.json").open("w", encoding="utf-8") as f:
        json.dump(quality, f, ensure_ascii=False, indent=2)

    print(f"[done] complaint_events_2024.csv: {len(events)} rows")
    print(f"[done] complaint_by_cluster_month_2024.csv: {len(monthly)} rows")
    print(f"[done] complaint_topic_by_cluster_2024.csv: {len(topic)} rows")
    print(f"[done] complaint_topic_group_by_cluster_2024.csv: {len(topic_group)} rows")
    print(f"[done] complaint_topic_group_by_cluster_month_2024.csv: {len(topic_group_month)} rows")
    print(f"[done] complaint_mobility_join_2024.csv: {len(mobility)} rows")


if __name__ == "__main__":
    main()
