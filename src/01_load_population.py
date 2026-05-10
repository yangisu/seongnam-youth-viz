"""행안부 인구이동 API 응답 + 행정동 인구 → 성남 청년(20-34) 순유출률.

데이터 소스:
  1. data/raw/mois_population/*.csv : 동별 성·연령별 인구 (모집단)
  2. data/raw/mois_migration/sgg_*.csv : Phase A — 시군구 OD, 12개월, 17시도, 양방향
  3. data/raw/mois_migration/dong_*.csv : Phase B — 동 OD, 6개월, 서울+경기, 양방향 (옵션)

API 응답에 male{0..110}AgeNmprCnt + feml{0..110}AgeNmprCnt 가 직접 있어서
  청년(20-34) 합계를 정확히 계산 가능 (가중 추정 불필요).

산출:
  - youth_population_by_dong.csv     : 동별 청년/총인구 (모집단)
  - youth_migration_by_sgg.csv       : 성남 시군구별 청년 net 이동 (Phase A 기반)
  - youth_migration_by_dong.csv      : 성남 동별 청년 net + 순유출률 (Phase B 기반, 6개월)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    DIR_MOIS_MIG, DIR_MOIS_POP, PROCESSED, YOUTH_AGE_MAX, YOUTH_AGE_MIN,
    find_column, read_csv_smart,
)

YOUTH_MALE_COLS = [f"male{a}AgeNmprCnt" for a in range(YOUTH_AGE_MIN, YOUTH_AGE_MAX + 1)]
YOUTH_FEML_COLS = [f"feml{a}AgeNmprCnt" for a in range(YOUTH_AGE_MIN, YOUTH_AGE_MAX + 1)]
YOUTH_AGE_COLS = YOUTH_MALE_COLS + YOUTH_FEML_COLS


# ============================================================
#  (1) 모집단: 행정동 성·연령 인구 → 동별 청년/총인구
# ============================================================
def load_youth_population() -> pd.DataFrame:
    files = sorted(DIR_MOIS_POP.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"{DIR_MOIS_POP} 비어있음")

    dfs = []
    for p in files:
        df = read_csv_smart(p)
        col_sgg = find_column(df, ["시군구명", "시군구"])
        col_dong = find_column(df, ["읍면동명", "읍면동", "행정동명"])
        col_total = find_column(df, ["총인구수", "총인구", "계"])
        if not (col_sgg and col_dong):
            continue
        sub = df[df[col_sgg].astype(str).str.contains("성남", na=False)].copy()
        if sub.empty:
            continue

        # 한국식 1세별 컬럼: '0세인구', '20세인구', ... (혹은 '남20세' 등)
        age_pattern = re.compile(r"(?:남|여)?\s*(\d+)\s*세")
        youth_cols = []
        for c in sub.columns:
            m = age_pattern.search(str(c))
            if m and YOUTH_AGE_MIN <= int(m.group(1)) <= YOUTH_AGE_MAX:
                youth_cols.append(c)
        for c in youth_cols:
            sub[c] = pd.to_numeric(sub[c].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
        sub["청년_인구"] = sub[youth_cols].sum(axis=1)

        if col_total:
            sub["총인구"] = pd.to_numeric(sub[col_total].astype(str).str.replace(",", ""), errors="coerce").fillna(0)
        else:
            sub["총인구"] = pd.NA
        sub["dong"] = sub[col_dong].astype(str).str.strip()
        sub["sgg"] = sub[col_sgg].astype(str).str.strip()
        dfs.append(sub[["sgg", "dong", "청년_인구", "총인구"]])

    if not dfs:
        return pd.DataFrame()
    out = pd.concat(dfs).groupby(["sgg", "dong"], as_index=False).agg(
        청년_인구=("청년_인구", "max"),
        총인구=("총인구", "max"),
    )
    return out


# ============================================================
#  (2) Phase A — 시군구 OD: 성남 시군구별 청년 이동
# ============================================================
def _add_youth(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in YOUTH_AGE_COLS if c in df.columns]
    df["청년"] = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    return df


def load_phase_a() -> pd.DataFrame:
    """sgg_*.csv 통합 → 한 DF (성남 row만)."""
    files = sorted(DIR_MOIS_MIG.glob("sgg_*.csv"))
    if not files:
        raise FileNotFoundError("Phase A 파일 없음")
    parts = []
    for f in files:
        df = pd.read_csv(f)
        df = _add_youth(df)
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def youth_migration_sgg() -> pd.DataFrame:
    big = load_phase_a()
    sn_out = big[big["mvtSggNm"].astype(str).str.match(r"성남시\s\S+구$", na=False)]
    sn_in = big[big["mvinSggNm"].astype(str).str.match(r"성남시\s\S+구$", na=False)]
    out = sn_out.groupby("mvtSggNm", as_index=True)["청년"].sum().rename("청년_전출")
    inn = sn_in.groupby("mvinSggNm", as_index=True)["청년"].sum().rename("청년_전입")
    df = pd.concat([inn, out], axis=1).fillna(0)
    df["청년_순이동"] = df["청년_전입"] - df["청년_전출"]
    df["청년_순유출"] = -df["청년_순이동"]
    df.index.name = "sgg"
    return df.reset_index()


# ============================================================
#  (3) Phase B — 동 OD: 성남 동별 청년 이동 (6개월 부분)
# ============================================================
def load_phase_b() -> pd.DataFrame | None:
    files = sorted(DIR_MOIS_MIG.glob("dong_*.csv"))
    if not files:
        return None
    parts = []
    for f in files:
        df = pd.read_csv(f)
        df = _add_youth(df)
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def youth_migration_dong(pop: pd.DataFrame) -> pd.DataFrame | None:
    big = load_phase_b()
    if big is None or big.empty:
        return None
    sn_out = big[big["mvtSggNm"].astype(str).str.contains("성남시", na=False)]
    sn_in = big[big["mvinSggNm"].astype(str).str.contains("성남시", na=False)]
    out = sn_out.groupby("mvtDongNm", as_index=True)["청년"].sum().rename("청년_전출_6m")
    inn = sn_in.groupby("mvinDongNm", as_index=True)["청년"].sum().rename("청년_전입_6m")
    df = pd.concat([inn, out], axis=1).fillna(0)
    df["청년_순이동_6m"] = df["청년_전입_6m"] - df["청년_전출_6m"]
    df.index.name = "dong"
    df = df.reset_index()
    # 모집단 머지로 순유출률 계산
    df = df.merge(pop[["dong", "청년_인구"]], on="dong", how="left")
    df["청년_순유출률"] = -(df["청년_순이동_6m"] / df["청년_인구"]) * 100
    df["청년_전입"] = df["청년_전입_6m"]
    df["청년_전출"] = df["청년_전출_6m"]
    return df.sort_values("청년_순유출률", ascending=False).reset_index(drop=True)


def main() -> None:
    print("[1] 모집단 로드...")
    pop = load_youth_population()
    pop.to_csv(PROCESSED / "youth_population_by_dong.csv", index=False, encoding="utf-8-sig")
    print(f"  → {len(pop)}동, 청년인구 합 {int(pop['청년_인구'].sum()):,}, 총인구 합 {int(pop['총인구'].sum()):,}")

    print("\n[2] Phase A — 시군구 OD 통합...")
    sgg = youth_migration_sgg()
    sgg.to_csv(PROCESSED / "youth_migration_by_sgg.csv", index=False, encoding="utf-8-sig")
    print(sgg.to_string(index=False))

    print("\n[3] Phase B — 동 OD 통합 (6개월 부분커버)...")
    dong = youth_migration_dong(pop)
    if dong is None:
        print("  Phase B 파일 없음 — 동 단위 분석 스킵")
    else:
        dong.to_csv(PROCESSED / "youth_migration_by_dong.csv", index=False, encoding="utf-8-sig")
        print(f"  → {len(dong)}동")
        print("\n순유출률 TOP 10 (유출):")
        print(dong.head(10)[["dong","청년_전입","청년_전출","청년_순이동_6m","청년_인구","청년_순유출률"]].to_string(index=False))
        print("\n순유출률 BOTTOM 10 (유입):")
        print(dong.tail(10)[["dong","청년_전입","청년_전출","청년_순이동_6m","청년_인구","청년_순유출률"]].to_string(index=False))


if __name__ == "__main__":
    main()
