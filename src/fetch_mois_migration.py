"""행안부 인구이동 API (data.go.kr 15108093) → CSV 저장. Production 버전.

Endpoint: https://apis.data.go.kr/1741000/ppltnDataStus/selectPpltnDataStus
필수: serviceKey, mvtAdmmCd, mvinAdmmCd, srchFrYm, srchToYm
선택: lv (1=시도/2=시군구/3=읍면동/4=단일시도), type, numOfRows≤100, pageNo

API 동작 (probe로 확인):
  - lv=3 + 성남 시군구 코드(예: 4113500000) → 411 prefix 매칭, 성남 전체 49개 동의
    동→동 흐름을 한 번에 반환 (대상 시도 와일드카드 4100000000 등)
  - lv=2 + 시군구 코드 → 시군구 단위 집계 (단, 성남 분당/수정/중원 구분 사라짐 = "성남시")
  - 응답 필드: statsYm, mvt/mvinCtpvNm, mvt/mvinSggNm, mvt/mvinDongNm,
              mvt/mvinAdmmCd, totNmprCnt, male/femlNmprCnt, male{0..110}AgeNmprCnt, feml{0..110}AgeNmprCnt

전략 (일일 10K 한도):
  Phase A — 시군구 OD (Sankey용): 17시도 × 12월 × 2방향, lv=2 ≈ 408 calls
  Phase B — 동 단위 (1단 Choropleth용): 경기(41)+서울(11) × 6개월 × 2방향, lv=3 ≈ 720 calls

산출:
  data/raw/mois_migration/sgg_<dir>_<sido>_<yyyymm>.csv  (Phase A)
  data/raw/mois_migration/dong_<dir>_<sido>_<yyyymm>.csv (Phase B)

이미 저장된 파일은 스킵 (resume 지원).
사용:
  python src/fetch_mois_migration.py --probe       # 단일 호출 테스트
  python src/fetch_mois_migration.py --phase-a     # 시군구 OD만
  python src/fetch_mois_migration.py --phase-b     # 동 단위만
  python src/fetch_mois_migration.py --all         # 둘 다
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DIR_MOIS_MIG  # noqa: E402

# .env 자동 로드
_env = Path(__file__).resolve().parent.parent / ".env"
if _env.exists():
    for line in _env.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

SERVICE_KEY = os.environ.get("DATA_GO_KR_KEY")
ENDPOINT = "https://apis.data.go.kr/1741000/ppltnDataStus/selectPpltnDataStus"

# 성남 시군구 코드 (어느 것을 써도 lv=3에서 성남시 전체 매칭됨)
SEONGNAM_SGG_CODE = "4113500000"   # 분당구 (성남시 prefix=411)

# 17개 시도 코드 (10자리, 시군구 자리 모두 0)
SIDO_CODES = {
    "11": "서울특별시",
    "26": "부산광역시",
    "27": "대구광역시",
    "28": "인천광역시",
    "29": "광주광역시",
    "30": "대전광역시",
    "31": "울산광역시",
    "36": "세종특별자치시",
    "41": "경기도",
    "43": "충청북도",
    "44": "충청남도",
    "46": "전라남도",
    "47": "경상북도",
    "48": "경상남도",
    "50": "제주특별자치도",
    "51": "강원특별자치도",
    "52": "전북특별자치도",
}
SIDO_FULL = {k: f"{k}00000000" for k in SIDO_CODES}

# 분석 대상 기간: 2024년 12개월 (가장 최근 완전한 1년)
ANALYSIS_YEAR = 2024
PHASE_A_MONTHS = [(ANALYSIS_YEAR, m) for m in range(1, 13)]
# Phase B는 비용 큰 lv=3 → 상위 시도 + 6개월만
PHASE_B_SIDOS = list(SIDO_CODES.keys())   # 전체 17 시도
PHASE_B_MONTHS = [(ANALYSIS_YEAR, m) for m in range(1, 13)]  # 12개월

# 공용
NUM_ROWS = 100
SLEEP = 0.15


def _ym(y: int, m: int) -> str:
    return f"{y}{m:02d}"


def _fetch_one(params: dict, retries: int = 2) -> tuple[list[dict], dict]:
    """한 번 호출 → (items, head)."""
    for attempt in range(retries + 1):
        try:
            r = requests.get(ENDPOINT, params=params, timeout=45)
        except requests.RequestException as e:
            if attempt < retries:
                time.sleep(1 + attempt)
                continue
            raise
        try:
            d = r.json()
        except ValueError:
            return [], {"resultMsg": f"NON_JSON: {r.text[:80]}"}
        head = d.get("Response", {}).get("head", {})
        items = d.get("Response", {}).get("items") or {}
        item = items.get("item") if isinstance(items, dict) else None
        if isinstance(item, dict):
            item = [item]
        return (item or []), head


def fetch_window(
    mvt_cd: str,
    mvin_cd: str,
    yyyymm: str,
    lv: str,
) -> pd.DataFrame:
    """단일 (origin, dest, month, lv) 페이징 전체 수집 → DataFrame."""
    if not SERVICE_KEY:
        raise RuntimeError("DATA_GO_KR_KEY 환경변수 비어있음")
    rows: list[dict] = []
    page = 1
    while True:
        params = {
            "serviceKey": SERVICE_KEY,
            "mvtAdmmCd": mvt_cd,
            "mvinAdmmCd": mvin_cd,
            "srchFrYm": yyyymm,
            "srchToYm": yyyymm,
            "lv": lv,
            "type": "json",
            "numOfRows": NUM_ROWS,
            "pageNo": page,
        }
        items, head = _fetch_one(params)
        msg = head.get("resultMsg", "?")
        if msg == "NODATA_ERROR":
            return pd.DataFrame()
        if msg != "NORMAL_SERVICE":
            print(f"      ! page={page} msg={msg}")
            break
        rows.extend(items)
        total = int(head.get("totalCount", 0) or 0)
        if page * NUM_ROWS >= total:
            break
        page += 1
        time.sleep(SLEEP)
    return pd.DataFrame(rows)


def _save(df: pd.DataFrame, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False, encoding="utf-8-sig")


def phase_a() -> None:
    """시군구 단위 OD: 성남 ↔ 17 시도 × 12 month."""
    print(f"\n=== Phase A (lv=2 시군구 OD, 17시도 × 12월 × 2방향) ===")
    n_total = 0
    for y, m in PHASE_A_MONTHS:
        ym = _ym(y, m)
        for sido_code, sido_nm in SIDO_CODES.items():
            sido_cd = SIDO_FULL[sido_code]
            for direction, mvt, mvin in [
                ("out", SEONGNAM_SGG_CODE, sido_cd),  # 성남 → 시도
                ("in", sido_cd, SEONGNAM_SGG_CODE),   # 시도 → 성남
            ]:
                out = DIR_MOIS_MIG / f"sgg_{direction}_{sido_code}_{ym}.csv"
                if out.exists():
                    continue
                df = fetch_window(mvt, mvin, ym, lv="2")
                if not df.empty:
                    _save(df, out)
                    print(f"  [{ym} {direction} {sido_nm}] {len(df)}행 → {out.name}")
                    n_total += len(df)
                time.sleep(SLEEP)
    print(f"\nPhase A 완료. 총 {n_total}행")


def phase_b() -> None:
    """동 단위 OD: 성남 동 ↔ (서울+경기) 동/시군구 × 6 month."""
    print(f"\n=== Phase B (lv=3 동 단위, 서울+경기 × 6월 × 2방향) ===")
    n_total = 0
    for y, m in PHASE_B_MONTHS:
        ym = _ym(y, m)
        for sido_code in PHASE_B_SIDOS:
            sido_nm = SIDO_CODES[sido_code]
            sido_cd = SIDO_FULL[sido_code]
            for direction, mvt, mvin in [
                ("out", SEONGNAM_SGG_CODE, sido_cd),
                ("in", sido_cd, SEONGNAM_SGG_CODE),
            ]:
                out = DIR_MOIS_MIG / f"dong_{direction}_{sido_code}_{ym}.csv"
                if out.exists():
                    continue
                df = fetch_window(mvt, mvin, ym, lv="3")
                if not df.empty:
                    _save(df, out)
                    print(f"  [{ym} {direction} {sido_nm}] {len(df)}행 → {out.name}")
                    n_total += len(df)
                time.sleep(SLEEP)
    print(f"\nPhase B 완료. 총 {n_total}행")


def probe() -> None:
    """단일 호출 sanity check."""
    print(f"[PROBE] 분당구 → 경기 lv=2, 2024-06")
    df = fetch_window(SEONGNAM_SGG_CODE, SIDO_FULL["41"], "202406", lv="2")
    print(f"  결과: {len(df)}행, 컬럼 수={len(df.columns)}")
    if not df.empty:
        keep = [c for c in ["statsYm","mvtCtpvNm","mvtSggNm","mvtDongNm","mvinCtpvNm","mvinSggNm","mvinDongNm","totNmprCnt"] if c in df.columns]
        print(df[keep].head(5).to_string(index=False))


def main() -> None:
    if "--probe" in sys.argv:
        probe(); return
    if "--phase-a" in sys.argv:
        phase_a(); return
    if "--phase-b" in sys.argv:
        phase_b(); return
    if "--all" in sys.argv:
        phase_a(); phase_b(); return
    print(__doc__)


if __name__ == "__main__":
    main()
