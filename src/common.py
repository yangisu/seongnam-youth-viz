"""공통 유틸리티: 경로, 인코딩 자동 감지, 한글 폰트 설정, 청년 정의."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

# 프로젝트 루트 (src/common.py 기준 한 단계 위)
ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
PROCESSED = ROOT / "data" / "processed"
GEOJSON = ROOT / "data" / "geojson"
OUT_FIG = ROOT / "outputs" / "figures"
OUT_HTML = ROOT / "outputs" / "interactive"

for p in (PROCESSED, OUT_FIG, OUT_HTML):
    p.mkdir(parents=True, exist_ok=True)

# 청년 정의: 20-34세
YOUTH_AGE_MIN = 20
YOUTH_AGE_MAX = 34
YOUTH_BUCKETS = ["20-24", "25-29", "30-34"]

# 원본 데이터 하위 디렉토리 (data.go.kr 기반으로 재정의)
DIR_MOIS_MIG = RAW / "mois_migration"     # 행안부 지역별 인구이동 (전입·전출 행정동 페어)
DIR_MOIS_POP = RAW / "mois_population"    # 행안부 행정동 성·연령별 주민등록 인구
DIR_SEONGNAM_DONG = RAW / "seongnam_dong" # 성남시 동별 인구·세대 현황
DIR_COMPLAINT = RAW / "seongnam_complaint"
DIR_EPEOPLE = RAW / "epeople"
DIR_VENTURE = RAW / "venture"             # 성남시 벤처기업 현황
DIR_VENDOR = RAW / "vendor"               # 성남사랑상품권 가맹점 / 통신판매업

# 성남시 4개 구 → 동 분류 (분석용 grouping)
BUNDANG_PANGYO = {
    "분당구": ["서현1동", "서현2동", "이매1동", "이매2동", "야탑1동", "야탑2동", "야탑3동",
              "분당동", "수내1동", "수내2동", "수내3동", "정자동", "정자1동", "정자2동", "정자3동",
              "금곡동", "구미동", "구미1동", "판교동", "삼평동", "백현동", "운중동"],
}
WONDOSIM = {
    "수정구": ["신흥1동", "신흥2동", "신흥3동", "태평1동", "태평2동", "태평3동", "태평4동",
              "수진1동", "수진2동", "단대동", "산성동", "양지동", "복정동", "위례동",
              "신촌동", "고등동", "시흥동"],
    "중원구": ["성남동", "금광1동", "금광2동", "은행1동", "은행2동", "상대원1동", "상대원2동",
              "상대원3동", "중앙동", "도촌동", "여수동", "하대원동"],
}


def read_csv_smart(path: Path | str, **kwargs) -> pd.DataFrame:
    """인코딩(UTF-8/CP949/EUC-KR)과 구분자를 자동 시도하여 CSV를 읽는다."""
    path = Path(path)
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    last_err: Exception | None = None
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except (UnicodeDecodeError, UnicodeError) as e:
            last_err = e
            continue
    raise RuntimeError(f"CSV 인코딩 자동 감지 실패: {path}") from last_err


def find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    """후보 컬럼명 중 실제 존재하는 첫 번째를 반환. 부분일치도 허용."""
    cols = list(df.columns)
    cols_norm = {c.replace(" ", "").lower(): c for c in cols}
    for cand in candidates:
        key = cand.replace(" ", "").lower()
        if key in cols_norm:
            return cols_norm[key]
    for cand in candidates:
        key = cand.replace(" ", "").lower()
        for c_norm, c_orig in cols_norm.items():
            if key in c_norm:
                return c_orig
    return None


def setup_korean_font() -> str:
    """matplotlib 한글 폰트 설정. 사용된 폰트명을 반환."""
    import matplotlib.pyplot as plt
    from matplotlib import font_manager

    candidates = ["Malgun Gothic", "NanumGothic", "AppleGothic", "Noto Sans CJK KR"]
    available = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((c for c in candidates if c in available), "DejaVu Sans")
    plt.rcParams["font.family"] = chosen
    plt.rcParams["axes.unicode_minus"] = False
    return chosen
