from __future__ import annotations

import shutil

from common import PROCESSED, SHARED_PROCESSED


FILES = [
    "od_youth_monthly_sgg.csv",
    "od_youth_monthly_dong.csv",
    "od_youth_seongnam_dong_to_outside.csv",
    "od_youth_seongnam_dong_inflow.csv",
    "od_youth_intra_seongnam_dong.csv",
    "od_youth_top_destinations.csv",
]


def main() -> None:
    copied = 0
    for name in FILES:
        src = SHARED_PROCESSED / name
        dst = PROCESSED / name
        if not src.exists():
            raise FileNotFoundError(f"Missing source file: {src}")
        shutil.copy2(src, dst)
        copied += 1
        print(f"[copied] {name}")

    print(f"[done] OD baseline copied: {copied} files")


if __name__ == "__main__":
    main()
