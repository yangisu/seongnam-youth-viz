from __future__ import annotations

import shutil

from common import PROCESSED, SHARED_PROCESSED


FILES = [
    "youth_population_by_dong.csv",
    "youth_migration_by_dong.csv",
    "youth_migration_by_sgg.csv",
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

    print(f"[done] population/migration baseline copied: {copied} files")


if __name__ == "__main__":
    main()
