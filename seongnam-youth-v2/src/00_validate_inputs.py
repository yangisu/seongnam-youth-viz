from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from common import PROCESSED, SHARED_BY_REGION, SHARED_BY_TYPE, SHARED_PROCESSED, list_real_files


def _month_from_region_name(stem: str) -> str | None:
    parts = stem.split("_", 1)
    if len(parts) != 2:
        return None
    month = parts[0]
    if month.isdigit() and len(month) == 6:
        return month
    return None


def main() -> None:
    region_files = list_real_files(SHARED_BY_REGION, "*.xlsx")
    type_files = list_real_files(SHARED_BY_TYPE, "*.xlsx")

    months: list[str] = []
    dongs: list[str] = []
    for f in region_files:
        parts = f.stem.split("_", 1)
        if len(parts) != 2:
            continue
        m = _month_from_region_name(f.stem)
        if m:
            months.append(m)
        dongs.append(parts[1])

    seed_required = [
        "youth_population_by_dong.csv",
        "youth_migration_by_dong.csv",
        "youth_migration_by_sgg.csv",
        "od_youth_monthly_sgg.csv",
        "od_youth_monthly_dong.csv",
        "od_youth_seongnam_dong_to_outside.csv",
        "od_youth_seongnam_dong_inflow.csv",
        "od_youth_intra_seongnam_dong.csv",
        "od_youth_top_destinations.csv",
    ]

    missing_seed = [f for f in seed_required if not (SHARED_PROCESSED / f).exists()]

    report = {
        "shared_paths": {
            "data_by_region": str(SHARED_BY_REGION),
            "data_by_type": str(SHARED_BY_TYPE),
            "shared_processed": str(SHARED_PROCESSED),
        },
        "region_file_count": len(region_files),
        "type_file_count": len(type_files),
        "region_month_count": len(sorted(set(months))),
        "region_months": sorted(set(months)),
        "region_dong_count": len(sorted(set(dongs))),
        "seed_missing_files": missing_seed,
        "is_valid_for_v2": len(region_files) > 0 and len(type_files) > 0 and len(missing_seed) == 0,
    }

    out = PROCESSED / "input_validation_report.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"[done] {out}")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
