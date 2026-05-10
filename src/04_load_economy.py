"""성남시 벤처기업 + 가맹점/통신판매업 → 동별 경제활력 지표.

(카드10/기업4·5 폐기, data.go.kr 성남시 데이터로 대체)

산출:
  - venture_by_dong.csv  : dong, 벤처기업수
  - vendor_by_dong.csv   : dong, 가맹점수 (또는 통신판매업체수)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import DIR_VENDOR, DIR_VENTURE, PROCESSED, find_column, read_csv_smart  # noqa: E402

COL_ADDR = ["주소", "소재지", "도로명주소", "지번주소", "사업장주소", "ADDRESS"]
COL_DONG = ["행정동", "법정동", "동", "읍면동"]


_DONG_PAT = re.compile(r"([가-힣0-9]+동)")


def _extract_dong_from_addr(s: str) -> str | None:
    """주소 문자열에서 'XX동' 패턴 추출 (가장 마지막 매치를 행정동으로 가정)."""
    if not isinstance(s, str):
        return None
    matches = _DONG_PAT.findall(s)
    return matches[-1] if matches else None


def _count_by_dong(folder: Path, label: str) -> pd.DataFrame:
    files = sorted(folder.glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"{folder} 비어있음")
    rows = []
    for p in files:
        df = read_csv_smart(p)
        c_dong = find_column(df, COL_DONG)
        c_addr = find_column(df, COL_ADDR)
        if c_dong:
            dong = df[c_dong].astype(str).str.strip()
        elif c_addr:
            dong = df[c_addr].astype(str).map(_extract_dong_from_addr)
        else:
            print(f"[경고] {p.name}: 동/주소 컬럼 없음 → {list(df.columns)[:8]}")
            continue
        # 성남 한정 (주소가 있을 때만)
        if c_addr:
            mask = df[c_addr].astype(str).str.contains("성남", na=False)
            dong = dong[mask]
        rows.append(pd.DataFrame({"dong": dong}))
    if not rows:
        return pd.DataFrame(columns=["dong", label])
    all_d = pd.concat(rows, ignore_index=True).dropna()
    return all_d.groupby("dong").size().reset_index(name=label).sort_values(label, ascending=False)


def main() -> None:
    try:
        v = _count_by_dong(DIR_VENTURE, "벤처기업수")
        v.to_csv(PROCESSED / "venture_by_dong.csv", index=False, encoding="utf-8-sig")
        print(f"[완료] venture_by_dong.csv: {len(v)}동")
    except FileNotFoundError as e:
        print(f"[건너뜀] {e}")

    try:
        v = _count_by_dong(DIR_VENDOR, "가맹점수")
        v.to_csv(PROCESSED / "vendor_by_dong.csv", index=False, encoding="utf-8-sig")
        print(f"[완료] vendor_by_dong.csv: {len(v)}동")
    except FileNotFoundError as e:
        print(f"[건너뜀] {e}")


if __name__ == "__main__":
    main()
