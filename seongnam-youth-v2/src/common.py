from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PARENT_ROOT = ROOT.parent

# Shared immutable source data (existing project datasets)
SHARED_ROOT = PARENT_ROOT
SHARED_RAW = SHARED_ROOT / "data" / "raw"
SHARED_PROCESSED = SHARED_ROOT / "data" / "processed"
SHARED_BY_REGION = SHARED_ROOT / "data_by_region"
SHARED_BY_TYPE = SHARED_ROOT / "data_by_type"

# v2 outputs
DATA = ROOT / "data"
PROCESSED = DATA / "processed"
GEOJSON = DATA / "geojson" / "seongnam_admdong.geojson"
OUTPUTS = ROOT / "outputs"

for d in [PROCESSED, OUTPUTS / "interactive", OUTPUTS / "site"]:
    d.mkdir(parents=True, exist_ok=True)

YOUTH_AGE_MIN = 20
YOUTH_AGE_MAX = 34


def list_real_files(path: Path, pattern: str = "*") -> list[Path]:
    files = [p for p in sorted(path.glob(pattern)) if p.is_file() and p.name != ".gitkeep"]
    return files


def read_csv_smart(path: Path, **kwargs) -> pd.DataFrame:
    encodings = ["utf-8-sig", "utf-8", "cp949", "euc-kr"]
    last_error: Exception | None = None
    for enc in encodings:
        try:
            return pd.read_csv(path, encoding=enc, **kwargs)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
    raise RuntimeError(f"Failed to read CSV with known encodings: {path}") from last_error


def find_column(df: pd.DataFrame, candidates: Iterable[str]) -> str | None:
    cols = list(df.columns)
    norm_map = {str(c).replace(" ", "").lower(): str(c) for c in cols}
    for cand in candidates:
        key = cand.replace(" ", "").lower()
        if key in norm_map:
            return norm_map[key]
    for cand in candidates:
        key = cand.replace(" ", "").lower()
        for col_norm, col_org in norm_map.items():
            if key in col_norm:
                return col_org
    return None
