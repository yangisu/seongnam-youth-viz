"""행안부 인구이동 API CSV 통합 → 청년 OD 매트릭스.

산출 (data/processed/):
  - od_youth_seongnam_dong_to_outside.csv : 성남 동 → 전국 시군구 (Phase B)
  - od_youth_seongnam_dong_inflow.csv     : 전국 시군구 → 성남 동
  - od_youth_intra_seongnam_dong.csv      : 성남 내부 동 ↔ 동
  - od_youth_monthly.csv                  : 월별 시군구 net (Phase A) 시계열용
  - od_youth_top_destinations.csv         : 동별 청년 유출 상위 시군구 TOP 5
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DIR_MOIS_MIG, PROCESSED, YOUTH_AGE_MAX, YOUTH_AGE_MIN  # noqa: E402

YOUTH_COLS = (
    [f"male{a}AgeNmprCnt" for a in range(YOUTH_AGE_MIN, YOUTH_AGE_MAX + 1)]
    + [f"feml{a}AgeNmprCnt" for a in range(YOUTH_AGE_MIN, YOUTH_AGE_MAX + 1)]
)


def _load(pattern: str) -> pd.DataFrame:
    files = sorted(DIR_MOIS_MIG.glob(pattern))
    if not files:
        return pd.DataFrame()
    parts = [pd.read_csv(f) for f in files]
    df = pd.concat(parts, ignore_index=True)
    cols = [c for c in YOUTH_COLS if c in df.columns]
    df["청년"] = df[cols].apply(pd.to_numeric, errors="coerce").fillna(0).sum(axis=1)
    return df


def build_dong_od() -> dict[str, pd.DataFrame]:
    big = _load("dong_*.csv")
    if big.empty:
        return {}

    sn_out = big[big["mvtSggNm"].astype(str).str.contains("성남시", na=False)].copy()
    sn_in = big[big["mvinSggNm"].astype(str).str.contains("성남시", na=False)].copy()

    # 성남 내부 vs 외부
    intra_mask_out = sn_out["mvinSggNm"].astype(str).str.contains("성남시", na=False)
    intra = sn_out[intra_mask_out].copy()

    # 외부 흐름
    out_to_outside = sn_out[~intra_mask_out].copy()
    in_from_outside = sn_in[~sn_in["mvtSggNm"].astype(str).str.contains("성남시", na=False)].copy()

    # 1) 성남 동 → 외부 시군구 (월 합산)
    od_out = (
        out_to_outside.groupby(
            ["mvtDongNm", "mvinCtpvNm", "mvinSggNm"], as_index=False
        )["청년"].sum()
        .rename(columns={"mvtDongNm": "origin_dong",
                         "mvinCtpvNm": "dest_sido",
                         "mvinSggNm": "dest_sgg",
                         "청년": "n"})
        .sort_values("n", ascending=False)
    )

    # 2) 외부 시군구 → 성남 동
    od_in = (
        in_from_outside.groupby(
            ["mvtCtpvNm", "mvtSggNm", "mvinDongNm"], as_index=False
        )["청년"].sum()
        .rename(columns={"mvtCtpvNm": "origin_sido",
                         "mvtSggNm": "origin_sgg",
                         "mvinDongNm": "dest_dong",
                         "청년": "n"})
        .sort_values("n", ascending=False)
    )

    # 3) 성남 내부 동→동
    od_intra = (
        intra.groupby(["mvtDongNm", "mvinDongNm"], as_index=False)["청년"].sum()
        .rename(columns={"mvtDongNm": "origin_dong",
                         "mvinDongNm": "dest_dong",
                         "청년": "n"})
        .sort_values("n", ascending=False)
    )

    # 4) 동별 TOP 5 외부 목적지 (Sankey 단순화용)
    top5 = (
        od_out.assign(rk=od_out.groupby("origin_dong")["n"].rank(method="first", ascending=False))
        .query("rk <= 5")
        .drop(columns=["rk"])
    )

    return {
        "od_youth_seongnam_dong_to_outside.csv": od_out,
        "od_youth_seongnam_dong_inflow.csv": od_in,
        "od_youth_intra_seongnam_dong.csv": od_intra,
        "od_youth_top_destinations.csv": top5,
    }


def build_monthly_sgg() -> pd.DataFrame:
    """Phase A 월별 시군구 net 시계열."""
    big = _load("sgg_*.csv")
    if big.empty:
        return pd.DataFrame()
    sn_out = big[big["mvtSggNm"].astype(str).str.match(r"성남시\s\S+구$", na=False)].copy()
    sn_in = big[big["mvinSggNm"].astype(str).str.match(r"성남시\s\S+구$", na=False)].copy()
    out_m = sn_out.groupby(["statsYm", "mvtSggNm"], as_index=False)["청년"].sum().rename(
        columns={"mvtSggNm": "sgg", "청년": "전출"})
    in_m = sn_in.groupby(["statsYm", "mvinSggNm"], as_index=False)["청년"].sum().rename(
        columns={"mvinSggNm": "sgg", "청년": "전입"})
    df = out_m.merge(in_m, on=["statsYm", "sgg"], how="outer").fillna(0)
    df["순이동"] = df["전입"] - df["전출"]
    df["statsYm"] = df["statsYm"].astype(str)
    return df.sort_values(["sgg", "statsYm"])


def build_monthly_dong() -> pd.DataFrame:
    """Phase B 월별 동 net 시계열 (신흥2동 같은 핫 동 trend용)."""
    big = _load("dong_*.csv")
    if big.empty:
        return pd.DataFrame()
    sn_out = big[big["mvtSggNm"].astype(str).str.contains("성남시", na=False)].copy()
    sn_in = big[big["mvinSggNm"].astype(str).str.contains("성남시", na=False)].copy()
    out_m = sn_out.groupby(["statsYm", "mvtDongNm"], as_index=False)["청년"].sum().rename(
        columns={"mvtDongNm": "dong", "청년": "전출"})
    in_m = sn_in.groupby(["statsYm", "mvinDongNm"], as_index=False)["청년"].sum().rename(
        columns={"mvinDongNm": "dong", "청년": "전입"})
    df = out_m.merge(in_m, on=["statsYm", "dong"], how="outer").fillna(0)
    df["순이동"] = df["전입"] - df["전출"]
    df["statsYm"] = df["statsYm"].astype(str)
    return df.sort_values(["dong", "statsYm"])


def main() -> None:
    od = build_dong_od()
    for fname, df in od.items():
        df.to_csv(PROCESSED / fname, index=False, encoding="utf-8-sig")
        print(f"[저장] {fname}: {len(df)}행")

    msgg = build_monthly_sgg()
    msgg.to_csv(PROCESSED / "od_youth_monthly_sgg.csv", index=False, encoding="utf-8-sig")
    print(f"[저장] od_youth_monthly_sgg.csv: {len(msgg)}행")

    mdong = build_monthly_dong()
    mdong.to_csv(PROCESSED / "od_youth_monthly_dong.csv", index=False, encoding="utf-8-sig")
    print(f"[저장] od_youth_monthly_dong.csv: {len(mdong)}행")

    if not od:
        print("[정보] dong_*.csv 없음 — Phase B 미실행 시 OD 생성 못함")


if __name__ == "__main__":
    main()
