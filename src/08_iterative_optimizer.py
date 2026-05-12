"""반복형 공공데이터 분석 오케스트레이터.

목표:
1) (선택) 누락된 원천 데이터를 자동 다운로드
2) 기존 정제/분석 스크립트(01~05) 실행
3) 상관이 약하면 피처 엔지니어링 + 외부요인 결합 후 재평가
4) 결과 보고서와 피처 상관 테이블 저장

사용 예시:
  python src/08_iterative_optimizer.py
  python src/08_iterative_optimizer.py --auto-download --threshold 0.30 --max-iterations 4
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import PROCESSED, RAW  # noqa: E402


ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / "reports"


def read_csv_auto(path: Path) -> pd.DataFrame:
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            return pd.read_csv(path, encoding=enc)
        except Exception:  # noqa: BLE001
            continue
    raise RuntimeError(f"CSV 로드 실패: {path}")


def to_numeric(df: pd.DataFrame, columns: Iterable[str]) -> None:
    for c in columns:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")


def safe_corr(x: pd.Series, y: pd.Series) -> float | None:
    sub = pd.concat([x, y], axis=1).dropna()
    if len(sub) < 5:
        return None
    if sub.iloc[:, 0].std(ddof=0) == 0 or sub.iloc[:, 1].std(ddof=0) == 0:
        return None
    return float(sub.iloc[:, 0].corr(sub.iloc[:, 1]))


def run_step(script_name: str) -> tuple[bool, str]:
    script_path = ROOT / "src" / script_name
    if not script_path.exists():
        return False, f"[skip] {script_name}: 파일 없음"
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        check=False,
    )
    ok = proc.returncode == 0
    msg = f"[{'ok' if ok else 'fail'}] {script_name} (exit={proc.returncode})"
    if proc.stdout.strip():
        msg += f"\n{proc.stdout.strip()}"
    if proc.stderr.strip():
        msg += f"\n[stderr]\n{proc.stderr.strip()}"
    return ok, msg


def auto_download_from_manifest(enabled: bool) -> list[str]:
    logs: list[str] = []
    manifest = RAW / "AUTO_DOWNLOAD_MANIFEST.csv"
    if not manifest.exists():
        logs.append("[skip] AUTO_DOWNLOAD_MANIFEST.csv 없음 (자동 다운로드 미실행)")
        return logs

    df = read_csv_auto(manifest)
    required_cols = {"subdir", "url"}
    if not required_cols.issubset(set(df.columns)):
        logs.append("[skip] manifest 필수 컬럼 부족: subdir,url")
        return logs

    if not enabled:
        logs.append("[skip] manifest 감지됨. --auto-download 옵션이 없어 다운로드는 건너뜀")
        return logs

    import requests

    for _, row in df.iterrows():
        subdir = str(row.get("subdir", "")).strip()
        url = str(row.get("url", "")).strip()
        filename = str(row.get("filename", "")).strip()
        if not subdir or not url:
            logs.append("[warn] manifest 행 누락: subdir/url")
            continue
        target_dir = RAW / subdir
        target_dir.mkdir(parents=True, exist_ok=True)
        if not filename:
            filename = url.split("?")[0].rstrip("/").split("/")[-1] or "downloaded_file"
        target = target_dir / filename

        if target.exists() and target.stat().st_size > 0:
            logs.append(f"[skip] already exists: {target.relative_to(ROOT)}")
            continue

        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            target.write_bytes(resp.content)
            logs.append(f"[ok] downloaded: {target.relative_to(ROOT)} ({len(resp.content):,} bytes)")
        except Exception as exc:  # noqa: BLE001
            logs.append(f"[fail] download {url} -> {target.relative_to(ROOT)}: {exc}")
    return logs


@dataclass
class IterationResult:
    iteration: int
    stage: str
    best_feature: str
    corr: float
    abs_corr: float
    note: str


def load_core_table() -> tuple[pd.DataFrame, str, str]:
    """반복분석의 기준 테이블을 선택한다.

    우선순위:
      1) complaint_mobility_join_2024.csv (생활권 원인 분석)
      2) youth_migration_by_dong.csv      (동 단위 이동만 분석)
    """
    complaint = PROCESSED / "complaint_mobility_join_2024.csv"
    youth = PROCESSED / "youth_migration_by_dong.csv"

    if complaint.exists():
        df = read_csv_auto(complaint)
        to_numeric(
            df,
            [
                "youth_outflow_rate",
                "complaints_per_1000_youth",
                "parking_share",
                "processing_days_median",
                "complaint_count",
                "processed_count",
                "youth_pop",
                "youth_in",
                "youth_out",
                "youth_net",
            ],
        )
        return df, "dong_cluster", "youth_outflow_rate"

    if youth.exists():
        df = read_csv_auto(youth)
        to_numeric(df, ["청년_순유출률", "청년_전입", "청년_전출", "청년_인구"])
        return df, "dong", "청년_순유출률"

    raise FileNotFoundError("분석용 processed 데이터가 없습니다.")


def add_monthly_variability_features(df: pd.DataFrame, key_col: str) -> pd.DataFrame:
    monthly_path = PROCESSED / "complaint_by_cluster_month_2024.csv"
    if not monthly_path.exists() or key_col != "dong_cluster":
        return df
    monthly = read_csv_auto(monthly_path)
    to_numeric(monthly, ["complaint_count", "processed_count", "parking_count"])
    g = monthly.groupby("dong_cluster", as_index=False).agg(
        complaint_mean=("complaint_count", "mean"),
        complaint_std=("complaint_count", "std"),
        processed_mean=("processed_count", "mean"),
        parking_mean=("parking_count", "mean"),
    )
    g["complaint_cv"] = np.where(g["complaint_mean"] > 0, g["complaint_std"] / g["complaint_mean"], np.nan)
    return df.merge(g, on="dong_cluster", how="left")


def _cluster_from_dong_name(dong: str) -> str:
    s = str(dong).strip()
    if s.endswith("1동") or s.endswith("2동") or s.endswith("3동") or s.endswith("4동"):
        return s[:-2] + "동"
    return s


def add_economy_features(df: pd.DataFrame, key_col: str) -> pd.DataFrame:
    eco_path = PROCESSED / "corr_outflow_economy.csv"
    if not eco_path.exists():
        return df
    eco = read_csv_auto(eco_path)
    if "dong" not in eco.columns:
        return df

    numeric_cols = [c for c in eco.columns if c != "dong" and pd.api.types.is_numeric_dtype(eco[c])]
    if not numeric_cols:
        return df

    eco = eco.copy()
    eco["dong_cluster"] = eco["dong"].map(_cluster_from_dong_name)
    agg = eco.groupby("dong_cluster", as_index=False)[numeric_cols].mean()

    if key_col == "dong_cluster":
        return df.merge(agg, on="dong_cluster", how="left")
    if key_col == "dong":
        return df.merge(eco.drop(columns=["dong_cluster"]), on="dong", how="left")
    return df


def collect_candidates(df: pd.DataFrame, target_col: str, exclude: set[str]) -> list[str]:
    out: list[str] = []
    for c in df.columns:
        if c in exclude or c == target_col:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            out.append(c)
    return out


def evaluate_features(df: pd.DataFrame, target_col: str, features: list[str], stage: str, iteration: int) -> tuple[list[dict], IterationResult | None]:
    rows: list[dict] = []
    best: IterationResult | None = None
    for f in features:
        corr = safe_corr(df[f], df[target_col])
        if corr is None or math.isnan(corr):
            continue
        abs_corr = abs(corr)
        rows.append(
            {
                "iteration": iteration,
                "stage": stage,
                "feature": f,
                "corr": corr,
                "abs_corr": abs_corr,
                "n": int(pd.concat([df[f], df[target_col]], axis=1).dropna().shape[0]),
            }
        )
        if best is None or abs_corr > best.abs_corr:
            best = IterationResult(iteration, stage, f, corr, abs_corr, "")
    return rows, best


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if "complaints_per_1000_youth" in out.columns:
        out["log_complaints_per_1000"] = np.log1p(out["complaints_per_1000_youth"].clip(lower=0))
    if "parking_share" in out.columns and "complaints_per_1000_youth" in out.columns:
        out["parking_pressure"] = out["parking_share"] * out["complaints_per_1000_youth"]
    if "processing_days_median" in out.columns and "complaints_per_1000_youth" in out.columns:
        out["delay_pressure"] = out["processing_days_median"] * out["complaints_per_1000_youth"]
    if "processed_count" in out.columns and "complaint_count" in out.columns:
        out["processed_rate"] = np.where(out["complaint_count"] > 0, out["processed_count"] / out["complaint_count"], np.nan)
    if "youth_pop" in out.columns and "complaint_count" in out.columns:
        out["complaint_density"] = np.where(out["youth_pop"] > 0, out["complaint_count"] / out["youth_pop"], np.nan)
    if "complaint_cv" in out.columns and "complaints_per_1000_youth" in out.columns:
        out["volatility_pressure"] = out["complaint_cv"] * out["complaints_per_1000_youth"]
    return out


def run_iterative_search(threshold: float, max_iterations: int) -> tuple[pd.DataFrame, list[IterationResult], str]:
    base, key_col, target_col = load_core_table()
    work = add_monthly_variability_features(base, key_col)
    work = add_economy_features(work, key_col)

    # 목표변수 구성요소(누수 피처) 제외: 상관 과대평가 방지
    leakage = {
        "youth_in",
        "youth_out",
        "youth_net",
        "청년_전입",
        "청년_전출",
        "청년_순이동_6m",
        "청년_전입_6m",
        "청년_전출_6m",
        "청년_순유출률",
        "youth_outflow_rate",
    }
    exclude = {key_col, *leakage}
    all_rows: list[dict] = []
    best_history: list[IterationResult] = []

    stage = "raw_features"
    candidates = collect_candidates(work, target_col=target_col, exclude=exclude)
    rows, best = evaluate_features(work, target_col, candidates, stage=stage, iteration=1)
    all_rows.extend(rows)
    if best:
        best.note = "기본 피처"
        best_history.append(best)

    current = engineer_features(work)
    for it in range(2, max_iterations + 1):
        stage = f"engineered_iter_{it}"
        candidates = collect_candidates(current, target_col=target_col, exclude=exclude)
        rows, best_iter = evaluate_features(current, target_col, candidates, stage=stage, iteration=it)
        all_rows.extend(rows)
        if best_iter:
            best_iter.note = "엔지니어링 피처 재탐색"
            best_history.append(best_iter)
        # 개선 없이 반복되는 경우 추가 생성 중단
        if len(best_history) >= 2 and best_history[-1].abs_corr <= best_history[-2].abs_corr + 1e-9:
            break

    if not all_rows:
        raise RuntimeError("상관계수 계산 가능한 피처가 없습니다.")

    result_df = pd.DataFrame(all_rows).sort_values(["abs_corr", "iteration"], ascending=[False, True]).reset_index(drop=True)
    best_global = result_df.iloc[0]
    n_unique_features = result_df["feature"].nunique()
    if n_unique_features < 3:
        quality = "insufficient_data"
    else:
        quality = "strong" if best_global["abs_corr"] >= threshold else "weak"

    return result_df, best_history, quality


def write_report(
    correlations: pd.DataFrame,
    best_history: list[IterationResult],
    quality: str,
    threshold: float,
    logs: list[str],
) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    today = date.today().isoformat()
    out = REPORTS / f"iterative_optimizer_report_{today}.md"

    top10 = correlations.head(10)
    best = top10.iloc[0]

    lines: list[str] = [
        f"# 반복형 분석 리포트 ({today})",
        "",
        "## 실행 로그",
    ]
    lines.extend([f"- {line}" for line in logs] if logs else ["- (로그 없음)"])
    lines.extend(
        [
            "",
            "## 최적 피처 결과",
            f"- 목표변수 대비 최고 절대상관: `{best['feature']}` (corr={best['corr']:.4f}, abs={best['abs_corr']:.4f})",
            f"- 판정 기준(threshold): {threshold:.2f}",
            f"- 품질 판정: **{quality}**",
            "",
            "## 반복 단계별 최고 피처",
        ]
    )
    if best_history:
        for b in best_history:
            lines.append(f"- iter {b.iteration} / {b.stage}: `{b.best_feature}` (corr={b.corr:.4f}, abs={b.abs_corr:.4f})")
    else:
        lines.append("- 기록 없음")

    lines.extend(
        [
            "",
            "## TOP 10 상관 피처",
            "| rank | iteration | stage | feature | corr | abs_corr | n |",
            "|---|---:|---|---|---:|---:|---:|",
        ]
    )
    for i, row in top10.reset_index(drop=True).iterrows():
        lines.append(
            f"| {i+1} | {int(row['iteration'])} | {row['stage']} | {row['feature']} | {row['corr']:.4f} | {row['abs_corr']:.4f} | {int(row['n'])} |"
        )

    lines.extend(
        [
            "",
            "## 재계획 규칙",
            f"- 최고 절대상관이 `{threshold:.2f}` 미만이면 약한 상관으로 간주하고 추가 데이터 결합을 권장.",
            "- 우선 결합 후보: 벤처/가맹점의 행정동 주소 데이터, 임대료/주택가격, 대중교통 접근성, 일자리 지표.",
        ]
    )

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="반복형 공공데이터 분석 오케스트레이터")
    parser.add_argument("--auto-download", action="store_true", help="AUTO_DOWNLOAD_MANIFEST.csv 기반 자동 다운로드")
    parser.add_argument("--threshold", type=float, default=0.30, help="상관 강도 기준값(abs corr)")
    parser.add_argument("--max-iterations", type=int, default=4, help="최대 반복 횟수")
    parser.add_argument("--skip-pipeline", action="store_true", help="01~05 기존 파이프라인 실행을 생략")
    args = parser.parse_args()

    logs: list[str] = []

    # 0) 자동 다운로드(선택)
    logs.extend(auto_download_from_manifest(enabled=args.auto_download))

    # 1) 기존 파이프라인 실행
    if args.skip_pipeline:
        logs.append("[skip] --skip-pipeline 옵션으로 01~05 실행 생략")
    else:
        for step in ["01_load_population.py", "02_load_od.py", "03_load_complaint.py", "04_load_economy.py", "05_analysis.py"]:
            ok, msg = run_step(step)
            logs.append(msg)
            if not ok:
                # 일부 스텝 실패해도 다음 단계 계속 진행 (누락 데이터 상황 대응)
                continue

    # 2) 반복형 상관 탐색
    correlations, history, quality = run_iterative_search(
        threshold=args.threshold,
        max_iterations=max(2, args.max_iterations),
    )

    correlations_path = PROCESSED / "iterative_feature_correlation.csv"
    correlations.to_csv(correlations_path, index=False, encoding="utf-8-sig")
    logs.append(f"[ok] saved: {correlations_path.relative_to(ROOT)}")

    report_path = write_report(correlations, history, quality, args.threshold, logs)
    print(f"[완료] {report_path}")

    summary = {
        "quality": quality,
        "best_feature": correlations.iloc[0]["feature"],
        "best_abs_corr": float(correlations.iloc[0]["abs_corr"]),
        "threshold": args.threshold,
    }
    (PROCESSED / "iterative_optimizer_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
