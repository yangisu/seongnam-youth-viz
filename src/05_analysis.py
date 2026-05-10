"""4단 분석에 필요한 파생 지표 계산.

산출:
  - youth_outflow_ranked.csv : 동별 청년 순유출률 + 분위(quintile)
  - dong_keyword_matrix.csv  : 동×키워드 (건수×부정비율) 매트릭스
  - corr_outflow_economy.csv : 청년 순유출률 vs 매출/법인 변화율 상관
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED  # noqa: E402


def rank_outflow() -> pd.DataFrame:
    src = PROCESSED / "youth_migration_by_dong.csv"
    if not src.exists():
        raise FileNotFoundError(f"{src} 없음 — 01_load_population.py 먼저 실행")
    df = pd.read_csv(src)
    df["순유출률_분위"] = pd.qcut(df["청년_순유출률"], 5, labels=False, duplicates="drop") + 1
    out = PROCESSED / "youth_outflow_ranked.csv"
    df.to_csv(out, index=False, encoding="utf-8-sig")
    return df


def build_dong_keyword_matrix(top_n: int = 20) -> pd.DataFrame:
    src = PROCESSED / "complaint_keywords_by_dong.csv"
    if not src.exists():
        raise FileNotFoundError(f"{src} 없음 — 03_load_complaint.py 먼저 실행")
    df = pd.read_csv(src)
    # 가중치: 건수 × 부정비율 (부정 비율 결측은 0.5로)
    df["weight"] = df["count"] * df["neg_ratio"].fillna(0.5)
    # 전체 상위 키워드만 컬럼으로
    top_kw = (
        df.groupby("keyword")["count"].sum().nlargest(top_n).index.tolist()
    )
    sub = df[df["keyword"].isin(top_kw)]
    mat = sub.pivot_table(
        index="dong", columns="keyword", values="weight", aggfunc="sum"
    ).fillna(0)
    out = PROCESSED / "dong_keyword_matrix.csv"
    mat.to_csv(out, encoding="utf-8-sig")
    return mat


def correlate_outflow_economy() -> pd.DataFrame:
    out_src = PROCESSED / "youth_outflow_ranked.csv"
    if not out_src.exists():
        raise FileNotFoundError("youth_outflow_ranked.csv 없음")

    out = pd.read_csv(out_src)[["dong", "청년_순유출률"]]
    merged = out.copy()

    venture_src = PROCESSED / "venture_by_dong.csv"
    vendor_src = PROCESSED / "vendor_by_dong.csv"
    if venture_src.exists():
        merged = merged.merge(pd.read_csv(venture_src), on="dong", how="left")
    if vendor_src.exists():
        merged = merged.merge(pd.read_csv(vendor_src), on="dong", how="left")

    out_path = PROCESSED / "corr_outflow_economy.csv"
    merged.to_csv(out_path, index=False, encoding="utf-8-sig")
    num_cols = [c for c in merged.columns if c != "dong" and pd.api.types.is_numeric_dtype(merged[c])]
    if len(num_cols) >= 2:
        print("\n상관계수:")
        print(merged[num_cols].corr().to_string())
    return merged


def main() -> None:
    for fn in (rank_outflow, build_dong_keyword_matrix, correlate_outflow_economy):
        try:
            fn()
            print(f"[완료] {fn.__name__}")
        except FileNotFoundError as e:
            print(f"[건너뜀] {fn.__name__}: {e}")


if __name__ == "__main__":
    main()
