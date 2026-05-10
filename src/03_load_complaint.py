"""민원 데이터 로드: data.seongnam.go.kr (동별 키워드) + bigdata.epeople.go.kr (분야별 시계열).

입력 (data/raw/seongnam_complaint/, data/raw/epeople/):
  - seongnam_complaint/*.csv : 동별 민원 키워드 + 감성비율
      예상 컬럼: 행정동, 키워드, 건수, 긍정비율, 부정비율
  - epeople/*.csv : 국민신문고 분야별 청년 민원
      예상 컬럼: 일자, 지역, 기관, 연령, 분야, 신청건수

출력 (data/processed/):
  - complaint_keywords_by_dong.csv
  - complaint_epeople_youth_timeseries.csv
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED, RAW, find_column, read_csv_smart  # noqa: E402

SEONGNAM_DIR = RAW / "seongnam_complaint"
EPEOPLE_DIR = RAW / "epeople"

# 성남시 민원 키워드 컬럼 후보
COL_DONG = ["행정동", "동", "읍면동"]
COL_KW = ["키워드", "단어", "토픽", "KEYWORD"]
COL_CNT = ["건수", "빈도", "출현수", "COUNT"]
COL_POS = ["긍정비율", "긍정", "POSITIVE"]
COL_NEG = ["부정비율", "부정", "NEGATIVE"]

# 국민신문고 컬럼 후보
COL_DATE = ["일자", "날짜", "신청일", "DATE", "YYYYMM"]
COL_REGION = ["지역", "시군구", "REGION"]
COL_AGE = ["연령", "연령대", "AGE"]
COL_FIELD = ["분야", "민원분야", "FIELD", "CATEGORY"]
COL_REQUEST = ["신청건수", "건수", "민원수", "COUNT"]


def load_seongnam_keywords() -> pd.DataFrame:
    files = sorted(SEONGNAM_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"{SEONGNAM_DIR}에 CSV 없음")
    rows = []
    for p in files:
        df = read_csv_smart(p)
        c_d = find_column(df, COL_DONG)
        c_k = find_column(df, COL_KW)
        c_c = find_column(df, COL_CNT)
        c_p = find_column(df, COL_POS)
        c_n = find_column(df, COL_NEG)
        if not all([c_d, c_k, c_c]):
            print(f"[경고] {p.name} 필수컬럼 부족: {list(df.columns)}")
            continue
        sub = pd.DataFrame({
            "dong": df[c_d],
            "keyword": df[c_k],
            "count": pd.to_numeric(df[c_c], errors="coerce").fillna(0),
            "pos_ratio": pd.to_numeric(df[c_p], errors="coerce") if c_p else 0.0,
            "neg_ratio": pd.to_numeric(df[c_n], errors="coerce") if c_n else 0.0,
        })
        rows.append(sub)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def load_epeople_youth() -> pd.DataFrame:
    files = sorted(EPEOPLE_DIR.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"{EPEOPLE_DIR}에 CSV 없음")
    rows = []
    for p in files:
        df = read_csv_smart(p)
        c_dt = find_column(df, COL_DATE)
        c_rg = find_column(df, COL_REGION)
        c_ag = find_column(df, COL_AGE)
        c_fd = find_column(df, COL_FIELD)
        c_rq = find_column(df, COL_REQUEST)
        if not all([c_dt, c_fd, c_rq]):
            print(f"[경고] {p.name} 필수컬럼 부족: {list(df.columns)}")
            continue
        sub = pd.DataFrame({
            "date": pd.to_datetime(df[c_dt], errors="coerce"),
            "region": df[c_rg] if c_rg else "성남시",
            "age": df[c_ag] if c_ag else None,
            "field": df[c_fd],
            "count": pd.to_numeric(df[c_rq], errors="coerce").fillna(0),
        })
        # 성남 + 청년만
        sub = sub[sub["region"].astype(str).str.contains("성남", na=False)]
        if c_ag:
            sub = sub[sub["age"].astype(str).str.contains("20|30", na=False)]
        rows.append(sub)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def main() -> None:
    try:
        kw = load_seongnam_keywords()
        kw.to_csv(PROCESSED / "complaint_keywords_by_dong.csv", index=False, encoding="utf-8-sig")
        print(f"[완료] complaint_keywords_by_dong.csv: {len(kw)}행")
    except FileNotFoundError as e:
        print(f"[건너뜀] {e}")

    try:
        ep = load_epeople_youth()
        ep.to_csv(PROCESSED / "complaint_epeople_youth_timeseries.csv", index=False, encoding="utf-8-sig")
        print(f"[완료] complaint_epeople_youth_timeseries.csv: {len(ep)}행")
    except FileNotFoundError as e:
        print(f"[건너뜀] {e}")


if __name__ == "__main__":
    main()
