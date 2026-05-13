from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from common import PROCESSED, ROOT, SHARED_RAW, read_csv_smart


REPORT_DIR = ROOT / "docs"


@dataclass
class IterationBest:
    iteration: int
    stage: str
    feature: str
    spearman_r: float
    abs_spearman_r: float
    n: int


def cluster_from_dong(dong: str) -> str:
    value = str(dong).strip()
    for suffix in ("1동", "2동", "3동", "4동"):
        if value.endswith(suffix):
            return f"{value[:-2]}동"
    return value


def run_step(script_name: str) -> tuple[bool, str]:
    script_path = ROOT / "src" / script_name
    if not script_path.exists():
        return False, f"[skip] {script_name}: missing"

    proc = subprocess.run(
        [sys.executable, str(script_path)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    ok = proc.returncode == 0
    summary = f"[{'ok' if ok else 'fail'}] {script_name} (exit={proc.returncode})"
    if proc.stderr.strip():
        summary += f"\n[stderr]\n{proc.stderr.strip()}"
    return ok, summary


def auto_download_from_manifest(enabled: bool) -> list[str]:
    logs: list[str] = []
    manifest = SHARED_RAW / "AUTO_DOWNLOAD_MANIFEST.csv"
    if not manifest.exists():
        logs.append("[skip] AUTO_DOWNLOAD_MANIFEST.csv not found")
        return logs

    frame = read_csv_smart(manifest)
    required_cols = {"subdir", "url"}
    if not required_cols.issubset(frame.columns):
        logs.append("[skip] manifest must include columns: subdir,url")
        return logs
    if not enabled:
        logs.append("[skip] manifest found but --auto-download is off")
        return logs
    import requests

    raw_root = SHARED_RAW.resolve()
    for _, row in frame.iterrows():
        subdir = str(row.get("subdir", "")).strip()
        url = str(row.get("url", "")).strip()
        filename = str(row.get("filename", "")).strip()
        if not subdir or not url:
            logs.append("[warn] invalid manifest row: subdir/url empty")
            continue

        target_dir = (SHARED_RAW / subdir).resolve()
        if target_dir != raw_root and raw_root not in target_dir.parents:
            logs.append(f"[skip] unsafe subdir path: {subdir}")
            continue

        target_dir.mkdir(parents=True, exist_ok=True)
        if not filename:
            filename = url.split("?")[0].rstrip("/").split("/")[-1] or "downloaded_file"
        target = target_dir / filename

        if target.exists() and target.stat().st_size > 0:
            logs.append(f"[skip] already exists: {target}")
            continue

        try:
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            target.write_bytes(response.content)
            logs.append(f"[ok] downloaded: {target} ({len(response.content):,} bytes)")
        except Exception as exc:  # noqa: BLE001
            logs.append(f"[fail] {url} -> {target}: {exc}")
    return logs


def to_numeric(frame: pd.DataFrame, columns: Iterable[str]) -> None:
    for col in columns:
        if col in frame.columns:
            frame[col] = pd.to_numeric(frame[col], errors="coerce")


def build_feature_table() -> pd.DataFrame:
    base = read_csv_smart(PROCESSED / "complaint_mobility_join_2024.csv").copy()
    panel = read_csv_smart(PROCESSED / "cluster_month_panel_2024.csv").copy()
    priority = read_csv_smart(PROCESSED / "policy_priority_matrix_2024.csv").copy()
    destination = read_csv_smart(PROCESSED / "od_destination_profiles_by_dong.csv").copy()

    to_numeric(
        base,
        [
            "youth_outflow_rate",
            "complaints_per_1000_totalpop",
            "processing_days_median",
            "complaint_count",
            "processed_count",
            "youth_pop",
            "total_pop",
            "youth_in",
            "youth_out",
            "youth_net",
            "parking_count",
            "parking_share",
        ],
    )

    panel["negative_net_flag"] = pd.to_numeric(panel.get("negative_net_flag"), errors="coerce").fillna(0)
    to_numeric(panel, ["monthly_outflow_rate", "complaints_per_1000_totalpop_month", "processed_rate"])
    panel_stats = (
        panel.groupby("dong_cluster", as_index=False)
        .agg(
            negative_month_share=("negative_net_flag", "mean"),
            outflow_volatility=("monthly_outflow_rate", "std"),
            complaints_per_1000_month_mean=("complaints_per_1000_totalpop_month", "mean"),
            processed_rate_month_mean=("processed_rate", "mean"),
        )
        .fillna({"outflow_volatility": 0.0})
    )

    keep_priority = [
        "dong_cluster",
        "internal_moves_per_1000_youth",
    ]
    priority_sub = priority[[c for c in keep_priority if c in priority.columns]].copy()
    to_numeric(priority_sub, ["internal_moves_per_1000_youth"])

    destination["dong_cluster"] = destination["origin_dong"].map(cluster_from_dong)
    to_numeric(destination, ["top_bucket_share", "origin_total_outflow"])
    dest_stats = destination.groupby("dong_cluster", as_index=False).agg(
        top_bucket_share_mean=("top_bucket_share", "mean"),
        origin_total_outflow_mean=("origin_total_outflow", "mean"),
    )

    merged = (
        base.merge(panel_stats, on="dong_cluster", how="left")
        .merge(priority_sub, on="dong_cluster", how="left")
        .merge(dest_stats, on="dong_cluster", how="left")
    )
    return merged


def zscore(series: pd.Series) -> pd.Series:
    s = pd.to_numeric(series, errors="coerce")
    std = s.std(ddof=0)
    if std == 0 or np.isnan(std):
        return pd.Series(np.zeros(len(s)), index=s.index)
    return (s - s.mean()) / std


def safe_corr(x: pd.Series, y: pd.Series, min_samples: int) -> dict[str, float | int] | None:
    sub = pd.concat([x, y], axis=1).dropna()
    if len(sub) < min_samples:
        return None
    if sub.iloc[:, 0].std(ddof=0) == 0 or sub.iloc[:, 1].std(ddof=0) == 0:
        return None
    px = sub.iloc[:, 0].to_numpy(dtype=float)
    py = sub.iloc[:, 1].to_numpy(dtype=float)
    p = pearsonr(px, py)
    s = spearmanr(px, py, nan_policy="omit")
    return {
        "n": int(len(sub)),
        "pearson_r": float(p.statistic),
        "spearman_r": float(s.statistic),
    }


def collect_numeric_features(frame: pd.DataFrame, target: str, exclude: set[str], min_samples: int) -> list[str]:
    features: list[str] = []
    for col in frame.columns:
        if col == target or col in exclude:
            continue
        if not pd.api.types.is_numeric_dtype(frame[col]):
            continue
        sub = frame[[col, target]].dropna()
        if len(sub) < min_samples:
            continue
        if sub[col].std(ddof=0) == 0:
            continue
        features.append(col)
    return features


def evaluate_features(
    frame: pd.DataFrame,
    target: str,
    features: list[str],
    min_samples: int,
    iteration: int,
    stage: str,
) -> tuple[pd.DataFrame, IterationBest | None]:
    rows: list[dict[str, object]] = []
    for feature in features:
        c = safe_corr(frame[feature], frame[target], min_samples=min_samples)
        if c is None:
            continue
        rows.append(
            {
                "iteration": iteration,
                "stage": stage,
                "feature": feature,
                "n": c["n"],
                "pearson_r": c["pearson_r"],
                "spearman_r": c["spearman_r"],
                "abs_spearman_r": abs(float(c["spearman_r"])),
            }
        )

    if not rows:
        return pd.DataFrame(), None

    table = pd.DataFrame(rows).sort_values(["abs_spearman_r", "n"], ascending=[False, False]).reset_index(drop=True)
    top = table.iloc[0]
    best = IterationBest(
        iteration=iteration,
        stage=stage,
        feature=str(top["feature"]),
        spearman_r=float(top["spearman_r"]),
        abs_spearman_r=float(top["abs_spearman_r"]),
        n=int(top["n"]),
    )
    return table, best


def add_engineered_features(frame: pd.DataFrame, top_features: list[str]) -> pd.DataFrame:
    out = frame.copy()
    if not top_features:
        return out

    for name in top_features[:3]:
        if name not in out.columns:
            continue
        out[f"{name}__z"] = zscore(out[name])
        shifted = out[name].clip(lower=0)
        out[f"{name}__log1p"] = np.log1p(shifted)

    if len(top_features) >= 2:
        a, b = top_features[0], top_features[1]
        if a in out.columns and b in out.columns:
            out[f"{a}__x__{b}"] = out[a] * out[b]
            out[f"{a}__div__{b}"] = out[a] / (out[b].abs() + 1e-9)
    return out


def add_composite_feature(frame: pd.DataFrame, ranked: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if ranked.empty:
        return out

    top = ranked.head(5)
    denom = float(top["abs_spearman_r"].sum())
    if denom <= 0:
        return out

    score = pd.Series(np.zeros(len(out)), index=out.index, dtype=float)
    for _, row in top.iterrows():
        feature = str(row["feature"])
        weight = float(row["abs_spearman_r"]) / denom
        if feature in out.columns:
            score = score + weight * zscore(out[feature])
    out["composite_pressure_index"] = score
    return out


def quality_from_corr(abs_corr: float, threshold: float) -> str:
    if abs_corr >= threshold:
        return "strong"
    return "weak"


def build_visual_recommendations(ranked: pd.DataFrame, target: str) -> pd.DataFrame:
    recommendations: list[dict[str, str]] = []
    for _, row in ranked.head(8).iterrows():
        feature = str(row["feature"])
        if "composite" in feature:
            chart = "priority choropleth + rank bar"
            reason = "Composite index is suitable for area ranking and intervention tiers."
        elif "__x__" in feature or "__div__" in feature:
            chart = "scatter with trendline"
            reason = "Interaction feature should be interpreted as a bivariate relationship."
        elif "share" in feature or "rate" in feature:
            chart = "choropleth + slope chart"
            reason = "Rate/share features are readable on geographic and temporal comparisons."
        else:
            chart = "sorted bar chart"
            reason = "Single metric ranking is best communicated with ordered bars."
        recommendations.append(
            {
                "feature": feature,
                "target": target,
                "recommended_visual": chart,
                "reason": reason,
            }
        )
    return pd.DataFrame(recommendations)


def write_report(
    logs: list[str],
    ranked: pd.DataFrame,
    history: list[IterationBest],
    quality: str,
    threshold: float,
    recommendations: pd.DataFrame,
) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    out = REPORT_DIR / f"iterative_optimizer_report_{date.today().isoformat()}.md"

    lines: list[str] = [
        f"# Iterative Optimizer Report ({date.today().isoformat()})",
        "",
        "## Execution Log",
    ]
    lines.extend([f"- {line}" for line in logs] if logs else ["- (none)"])
    lines.extend(
        [
            "",
            "## Iteration Best History",
            "| iteration | stage | feature | spearman_r | abs_spearman_r | n |",
            "|---:|---|---|---:|---:|---:|",
        ]
    )
    for item in history:
        lines.append(
            f"| {item.iteration} | {item.stage} | {item.feature} | {item.spearman_r:.4f} | {item.abs_spearman_r:.4f} | {item.n} |"
        )

    top = ranked.head(12)
    best = top.iloc[0]
    lines.extend(
        [
            "",
            "## Best Signal",
            f"- feature: `{best['feature']}`",
            f"- spearman_r: `{best['spearman_r']:.4f}` (abs={best['abs_spearman_r']:.4f})",
            f"- threshold: `{threshold:.2f}`",
            f"- quality: **{quality}**",
            "",
            "## Top 12 Features",
            "| rank | iteration | stage | feature | spearman_r | abs_spearman_r | n |",
            "|---:|---:|---|---|---:|---:|---:|",
        ]
    )
    for i, row in top.reset_index(drop=True).iterrows():
        lines.append(
            f"| {i+1} | {int(row['iteration'])} | {row['stage']} | {row['feature']} | {row['spearman_r']:.4f} | {row['abs_spearman_r']:.4f} | {int(row['n'])} |"
        )

    lines.extend(
        [
            "",
            "## Visualization Recommendations",
            "| feature | visual | rationale |",
            "|---|---|---|",
        ]
    )
    for _, row in recommendations.iterrows():
        lines.append(f"| {row['feature']} | {row['recommended_visual']} | {row['reason']} |")

    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def run_iterative_search(threshold: float, max_iterations: int, min_samples: int) -> tuple[pd.DataFrame, list[IterationBest], str]:
    target = "youth_outflow_rate"
    exclude = {
        "dong_cluster",
        "policy_tier",
        "tier_reason",
        # Leakage controls: these directly define or trivially reconstruct outflow rate.
        "youth_in",
        "youth_out",
        "youth_net",
        "youth_pop",
        "total_pop",
        "avg_monthly_outflow_rate",
        "negative_month_share",
        "outflow_volatility",
        "monthly_outflow_volatility",
    }
    base = build_feature_table()

    all_rows: list[pd.DataFrame] = []
    history: list[IterationBest] = []
    ranked_prev = pd.DataFrame()
    top_features: list[str] = []
    previous_best = -1.0

    for iteration in range(1, max_iterations + 1):
        if iteration == 1:
            stage_name = "raw_features"
            work = base.copy()
        elif iteration == 2:
            stage_name = "engineered_features"
            work = add_engineered_features(base, top_features)
        else:
            stage_name = f"composite_iter_{iteration}"
            work = add_engineered_features(base, top_features)
            work = add_composite_feature(work, ranked_prev)

        features = collect_numeric_features(work, target=target, exclude=exclude, min_samples=min_samples)
        ranked, best = evaluate_features(
            work,
            target=target,
            features=features,
            min_samples=min_samples,
            iteration=iteration,
            stage=stage_name,
        )
        if ranked.empty or best is None:
            break

        all_rows.append(ranked)
        history.append(best)
        ranked_prev = ranked
        top_features = ranked.head(5)["feature"].astype(str).tolist()

        if best.abs_spearman_r >= threshold:
            break
        if best.abs_spearman_r <= previous_best + 1e-9:
            break
        previous_best = best.abs_spearman_r

    if not all_rows:
        raise RuntimeError("No valid feature correlation was computed.")

    combined = pd.concat(all_rows, ignore_index=True).sort_values(
        ["abs_spearman_r", "iteration"], ascending=[False, True]
    ).reset_index(drop=True)
    quality = quality_from_corr(float(combined.iloc[0]["abs_spearman_r"]), threshold=threshold)
    return combined, history, quality


def main() -> None:
    parser = argparse.ArgumentParser(description="Iterative optimizer for Seongnam public-data visualization")
    parser.add_argument("--auto-download", action="store_true", help="Download missing raw files from manifest")
    parser.add_argument("--refresh-pipeline", action="store_true", help="Run v2 pipeline steps before optimization")
    parser.add_argument("--threshold", type=float, default=0.35, help="Strong-correlation threshold (abs spearman)")
    parser.add_argument("--max-iterations", type=int, default=4, help="Maximum iteration count")
    parser.add_argument("--min-samples", type=int, default=10, help="Minimum valid pairs required per feature")
    args = parser.parse_args()

    logs: list[str] = []
    logs.extend(auto_download_from_manifest(enabled=args.auto_download))

    if args.refresh_pipeline:
        steps = [
            "00_validate_inputs.py",
            "01_load_population.py",
            "02_load_od.py",
            "03_load_complaint_2024.py",
            "05_analysis.py",
            "06_policy_focus.py",
            "07_build_site.py",
        ]
        for step in steps:
            ok, message = run_step(step)
            logs.append(message)
            if not ok:
                logs.append("[warn] pipeline step failed, continuing optimizer with existing processed files")

    ranked, history, quality = run_iterative_search(
        threshold=args.threshold,
        max_iterations=max(2, args.max_iterations),
        min_samples=max(5, args.min_samples),
    )

    ranked_path = PROCESSED / "iterative_feature_correlation_v2.csv"
    ranked.to_csv(ranked_path, index=False, encoding="utf-8-sig")
    logs.append(f"[ok] saved: {ranked_path}")

    recommendations = build_visual_recommendations(ranked, target="youth_outflow_rate")
    recommendation_path = PROCESSED / "iterative_visualization_recommendations_v2.csv"
    recommendations.to_csv(recommendation_path, index=False, encoding="utf-8-sig")
    logs.append(f"[ok] saved: {recommendation_path}")

    report_path = write_report(
        logs=logs,
        ranked=ranked,
        history=history,
        quality=quality,
        threshold=args.threshold,
        recommendations=recommendations,
    )

    summary = {
        "quality": quality,
        "threshold": args.threshold,
        "best_feature": str(ranked.iloc[0]["feature"]),
        "best_spearman_r": float(ranked.iloc[0]["spearman_r"]),
        "best_abs_spearman_r": float(ranked.iloc[0]["abs_spearman_r"]),
        "best_iteration": int(ranked.iloc[0]["iteration"]),
        "iterations_run": int(max(ranked["iteration"])),
        "evaluated_stages": sorted(ranked["stage"].astype(str).unique().tolist()),
        "report_path": str(report_path),
    }
    summary_path = PROCESSED / "iterative_optimizer_summary_v2.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
