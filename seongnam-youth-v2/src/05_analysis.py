from __future__ import annotations

import json
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import pearsonr, spearmanr

from common import PROCESSED

RNG = np.random.default_rng(42)


@dataclass
class CorrResult:
    variable: str
    n: int
    pearson_r: float
    pearson_p: float
    spearman_r: float
    spearman_p: float
    spearman_ci_low: float
    spearman_ci_high: float


def cluster_from_dong(dong: str) -> str:
    if not dong:
        return ""
    m = re.match(r"^(.+?)[1-4]동$", str(dong))
    return f"{m.group(1)}동" if m else str(dong)


def _bootstrap_spearman(x: np.ndarray, y: np.ndarray, n_boot: int = 1000) -> tuple[float, float]:
    n = len(x)
    if n < 5:
        return (float("nan"), float("nan"))
    vals = []
    idx = np.arange(n)
    for _ in range(n_boot):
        sample_idx = RNG.choice(idx, size=n, replace=True)
        rx = x[sample_idx]
        ry = y[sample_idx]
        r = spearmanr(rx, ry, nan_policy="omit").statistic
        if not np.isnan(r):
            vals.append(float(r))
    if len(vals) < 10:
        return (float("nan"), float("nan"))
    return (float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5)))


def _safe_corr(x: pd.Series, y: pd.Series) -> dict[str, float]:
    sub = pd.concat([x, y], axis=1).dropna()
    if len(sub) < 5:
        return {
            "n": int(len(sub)),
            "pearson_r": float("nan"),
            "pearson_p": float("nan"),
            "spearman_r": float("nan"),
            "spearman_p": float("nan"),
        }
    p = pearsonr(sub.iloc[:, 0], sub.iloc[:, 1])
    s = spearmanr(sub.iloc[:, 0], sub.iloc[:, 1], nan_policy="omit")
    return {
        "n": int(len(sub)),
        "pearson_r": float(p.statistic),
        "pearson_p": float(p.pvalue),
        "spearman_r": float(s.statistic),
        "spearman_p": float(s.pvalue),
    }


def rank_outflow() -> pd.DataFrame:
    df = pd.read_csv(PROCESSED / "youth_migration_by_dong.csv")
    df["순유출률_분위"] = pd.qcut(df["청년_순유출률"], 5, labels=False, duplicates="drop") + 1
    df.to_csv(PROCESSED / "youth_outflow_ranked.csv", index=False, encoding="utf-8-sig")
    return df


def build_cluster_month_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    od_m = pd.read_csv(PROCESSED / "od_youth_monthly_dong.csv")
    comp_m = pd.read_csv(PROCESSED / "complaint_by_cluster_month_2024.csv")
    pop = pd.read_csv(PROCESSED / "youth_population_by_dong.csv")
    join = pd.read_csv(PROCESSED / "complaint_mobility_join_2024.csv")

    od_m = od_m.copy()
    od_m["dong_cluster"] = od_m["dong"].map(cluster_from_dong)
    od_c = (
        od_m.groupby(["statsYm", "dong_cluster"], as_index=False)
        .agg(youth_in=("전입", "sum"), youth_out=("전출", "sum"), youth_net=("순이동", "sum"))
        .rename(columns={"statsYm": "month"})
    )

    pop = pop.copy()
    pop["dong_cluster"] = pop["dong"].map(cluster_from_dong)
    pop_c = pop.groupby("dong_cluster", as_index=False).agg(youth_pop=("청년_인구", "sum"), total_pop=("총인구", "sum"))

    panel = od_c.merge(pop_c, on="dong_cluster", how="left")
    panel["monthly_outflow_rate"] = (panel["youth_out"] - panel["youth_in"]) / panel["youth_pop"] * 100.0
    panel["month"] = panel["month"].astype(str)
    panel["month_dt"] = pd.to_datetime(panel["month"] + "01", format="%Y%m%d")

    comp_m = comp_m.copy()
    comp_m["month"] = comp_m["month"].astype(str)
    panel = panel.merge(
        comp_m[
            [
                "month",
                "dong_cluster",
                "complaint_count",
                "processed_count",
                "processing_days_median",
                "parking_count",
                "parking_share",
            ]
        ],
        on=["month", "dong_cluster"],
        how="left",
    )
    panel[["complaint_count", "processed_count", "parking_count"]] = panel[
        ["complaint_count", "processed_count", "parking_count"]
    ].fillna(0)
    panel["processing_days_median"] = panel["processing_days_median"].fillna(np.nan)
    panel["parking_share"] = panel["parking_share"].fillna(np.nan)
    panel["processed_rate"] = np.where(panel["complaint_count"] > 0, panel["processed_count"] / panel["complaint_count"], np.nan)
    panel["complaints_per_1000_totalpop_month"] = np.where(
        panel["total_pop"] > 0,
        panel["complaint_count"] / panel["total_pop"] * 1000.0,
        np.nan,
    )
    panel["negative_net_flag"] = (panel["youth_net"] < 0).astype(int)

    city = (
        panel.groupby("month", as_index=False)
        .agg(
            youth_in=("youth_in", "sum"),
            youth_out=("youth_out", "sum"),
            youth_net=("youth_net", "sum"),
            complaint_count=("complaint_count", "sum"),
            mean_outflow_rate=("monthly_outflow_rate", "mean"),
            mean_complaints_per_1000=("complaints_per_1000_totalpop_month", "mean"),
        )
        .sort_values("month")
    )
    city.to_csv(PROCESSED / "monthly_city_series_2024.csv", index=False, encoding="utf-8-sig")

    panel = panel.sort_values(["dong_cluster", "month"]).reset_index(drop=True)
    panel.to_csv(PROCESSED / "cluster_month_panel_2024.csv", index=False, encoding="utf-8-sig")
    return panel, city


def monthly_association_tests(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    p = panel.copy().sort_values(["dong_cluster", "month"])
    p["outflow_next"] = p.groupby("dong_cluster")["monthly_outflow_rate"].shift(-1)
    p["complaint_next"] = p.groupby("dong_cluster")["complaints_per_1000_totalpop_month"].shift(-1)

    rows: list[dict[str, object]] = []

    def add_row(name: str, x_col: str, y_col: str, mode: str) -> None:
        sub = p[[x_col, y_col, "dong_cluster", "month"]].dropna()
        if len(sub) < 5:
            return
        c = _safe_corr(sub[x_col], sub[y_col])
        fit = sm.OLS(sub[y_col], sm.add_constant(sub[[x_col]])).fit()
        rows.append(
            {
                "analysis": name,
                "mode": mode,
                "x": x_col,
                "y": y_col,
                "n": int(len(sub)),
                "pearson_r": c["pearson_r"],
                "pearson_p": c["pearson_p"],
                "spearman_r": c["spearman_r"],
                "spearman_p": c["spearman_p"],
                "slope": float(fit.params[x_col]),
                "slope_p": float(fit.pvalues[x_col]),
                "r2": float(fit.rsquared),
            }
        )

    add_row(
        "same_month_complaint_to_outflow",
        "complaints_per_1000_totalpop_month",
        "monthly_outflow_rate",
        "cross_section_pool",
    )
    add_row(
        "lag1_complaint_to_next_outflow",
        "complaints_per_1000_totalpop_month",
        "outflow_next",
        "lag_pool",
    )
    add_row(
        "lag1_outflow_to_next_complaint",
        "monthly_outflow_rate",
        "complaint_next",
        "lag_pool",
    )

    # Within-cluster (demeaned) relation to reduce cluster fixed heterogeneity.
    w = p[["dong_cluster", "monthly_outflow_rate", "complaints_per_1000_totalpop_month"]].dropna().copy()
    w["x_dm"] = w["complaints_per_1000_totalpop_month"] - w.groupby("dong_cluster")["complaints_per_1000_totalpop_month"].transform("mean")
    w["y_dm"] = w["monthly_outflow_rate"] - w.groupby("dong_cluster")["monthly_outflow_rate"].transform("mean")
    w = w.dropna(subset=["x_dm", "y_dm"])
    if len(w) >= 5:
        c = _safe_corr(w["x_dm"], w["y_dm"])
        fit = sm.OLS(w["y_dm"], sm.add_constant(w[["x_dm"]])).fit()
        rows.append(
            {
                "analysis": "within_cluster_same_month",
                "mode": "demeaned",
                "x": "complaints_per_1000_totalpop_month_demeaned",
                "y": "monthly_outflow_rate_demeaned",
                "n": int(len(w)),
                "pearson_r": c["pearson_r"],
                "pearson_p": c["pearson_p"],
                "spearman_r": c["spearman_r"],
                "spearman_p": c["spearman_p"],
                "slope": float(fit.params["x_dm"]),
                "slope_p": float(fit.pvalues["x_dm"]),
                "r2": float(fit.rsquared),
            }
        )

    summary = pd.DataFrame(rows)
    summary.to_csv(PROCESSED / "stats_monthly_association_2024.csv", index=False, encoding="utf-8-sig")

    # Cluster-level lag relation for interpretability.
    lag_rows = []
    for cluster, g in p.groupby("dong_cluster"):
        sub = g[["complaints_per_1000_totalpop_month", "outflow_next"]].dropna()
        if len(sub) < 4:
            continue
        if sub["complaints_per_1000_totalpop_month"].nunique() < 2 or sub["outflow_next"].nunique() < 2:
            continue
        s = spearmanr(sub["complaints_per_1000_totalpop_month"], sub["outflow_next"], nan_policy="omit")
        lag_rows.append(
            {
                "dong_cluster": cluster,
                "n": int(len(sub)),
                "spearman_r": float(s.statistic),
                "spearman_p": float(s.pvalue),
            }
        )
    lag_df = pd.DataFrame(lag_rows).sort_values("spearman_r", ascending=False)
    lag_df.to_csv(PROCESSED / "stats_monthly_lag_by_cluster_2024.csv", index=False, encoding="utf-8-sig")
    return summary, lag_df


def horizon_window_association(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    horizons = [3, 6, 12]
    p = panel.copy().sort_values(["dong_cluster", "month"])
    points: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []

    for h in horizons:
        rows_h: list[dict[str, object]] = []
        for cluster, g in p.groupby("dong_cluster"):
            g = g.sort_values("month").copy()
            g["complaint_win"] = g["complaints_per_1000_totalpop_month"].rolling(h, min_periods=h).mean()
            g["outflow_win"] = g["monthly_outflow_rate"].rolling(h, min_periods=h).mean()
            sub = g.dropna(subset=["complaint_win", "outflow_win"])
            for _, r in sub.iterrows():
                rows_h.append(
                    {
                        "horizon_months": h,
                        "dong_cluster": cluster,
                        "end_month": str(r["month"]),
                        "complaint_window": float(r["complaint_win"]),
                        "outflow_window": float(r["outflow_win"]),
                    }
                )

        points.extend(rows_h)
        dfh = pd.DataFrame(rows_h)
        if len(dfh) < 5 or dfh["complaint_window"].nunique() < 2 or dfh["outflow_window"].nunique() < 2:
            summary_rows.append(
                {
                    "horizon_months": h,
                    "n": int(len(dfh)),
                    "pearson_r": float("nan"),
                    "pearson_p": float("nan"),
                    "spearman_r": float("nan"),
                    "spearman_p": float("nan"),
                    "slope": float("nan"),
                    "slope_p": float("nan"),
                    "r2": float("nan"),
                    "status": "insufficient_data",
                }
            )
            continue

        c = _safe_corr(dfh["complaint_window"], dfh["outflow_window"])
        fit = sm.OLS(dfh["outflow_window"], sm.add_constant(dfh[["complaint_window"]])).fit()
        summary_rows.append(
            {
                "horizon_months": h,
                "n": int(len(dfh)),
                "pearson_r": c["pearson_r"],
                "pearson_p": c["pearson_p"],
                "spearman_r": c["spearman_r"],
                "spearman_p": c["spearman_p"],
                "slope": float(fit.params["complaint_window"]),
                "slope_p": float(fit.pvalues["complaint_window"]),
                "r2": float(fit.rsquared),
                "status": "ok",
            }
        )

    summary = pd.DataFrame(summary_rows).sort_values("horizon_months")
    points_df = pd.DataFrame(points).sort_values(["horizon_months", "dong_cluster", "end_month"]) if points else pd.DataFrame()
    summary.to_csv(PROCESSED / "stats_horizon_association_2024.csv", index=False, encoding="utf-8-sig")
    points_df.to_csv(PROCESSED / "horizon_association_points_2024.csv", index=False, encoding="utf-8-sig")
    return summary, points_df


def topic_type_association(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    topic_month = pd.read_csv(PROCESSED / "complaint_topic_group_by_cluster_month_2024.csv")
    topic_year = pd.read_csv(PROCESSED / "complaint_topic_group_by_cluster_2024.csv")
    base = pd.read_csv(PROCESSED / "complaint_mobility_join_2024.csv")

    p = panel.copy()
    p["month"] = p["month"].astype(str)
    topic_month["month"] = topic_month["month"].astype(str)
    merged = p.merge(
        topic_month[["month", "dong_cluster", "topic_group", "complaint_count", "month_cluster_total", "topic_share"]],
        on=["month", "dong_cluster"],
        how="left",
        suffixes=("", "_topic"),
    )
    topic_count_col = "complaint_count_topic" if "complaint_count_topic" in merged.columns else "complaint_count"
    merged["topic_group"] = merged["topic_group"].fillna("기타")
    merged["complaint_count"] = merged[topic_count_col].fillna(0)
    merged["month_cluster_total"] = merged["month_cluster_total"].fillna(0)
    merged["topic_share"] = merged["topic_share"].fillna(0.0)
    merged.to_csv(PROCESSED / "topic_cluster_month_panel_2024.csv", index=False, encoding="utf-8-sig")

    city_topic = (
        topic_month.groupby(["month", "topic_group"], as_index=False)
        .agg(complaint_count=("complaint_count", "sum"))
        .sort_values(["month", "topic_group"])
    )
    month_total = city_topic.groupby("month", as_index=False)["complaint_count"].sum().rename(columns={"complaint_count": "month_total"})
    city_topic = city_topic.merge(month_total, on="month", how="left")
    city_topic["topic_share"] = np.where(city_topic["month_total"] > 0, city_topic["complaint_count"] / city_topic["month_total"], np.nan)
    city_topic.to_csv(PROCESSED / "topic_city_month_2024.csv", index=False, encoding="utf-8-sig")

    horizons = [3, 6]
    point_rows: list[dict[str, object]] = []
    summary_rows: list[dict[str, object]] = []
    priority_topics = ["시설노후/파손", "불법광고물", "보행/도로안전", "생활환경", "불법주정차"]

    for topic in priority_topics:
        gt = merged[merged["topic_group"] == topic].copy()
        if gt.empty:
            for h in horizons:
                summary_rows.append(
                    {
                        "topic_group": topic,
                        "horizon_months": h,
                        "n": 0,
                        "pearson_r": float("nan"),
                        "pearson_p": float("nan"),
                        "spearman_r": float("nan"),
                        "spearman_p": float("nan"),
                        "slope": float("nan"),
                        "slope_p": float("nan"),
                        "r2": float("nan"),
                        "status": "insufficient_data",
                        "method": "rolling_window_pool",
                    }
                )
            continue

        for h in horizons:
            rows_h: list[dict[str, object]] = []
            for cluster, g in gt.groupby("dong_cluster"):
                g = g.sort_values("month").copy()
                g["topic_share_win"] = g["topic_share"].rolling(h, min_periods=h).mean()
                g["outflow_win"] = g["monthly_outflow_rate"].rolling(h, min_periods=h).mean()
                sub = g.dropna(subset=["topic_share_win", "outflow_win"])
                for _, r in sub.iterrows():
                    rows_h.append(
                        {
                            "topic_group": topic,
                            "horizon_months": h,
                            "dong_cluster": cluster,
                            "end_month": str(r["month"]),
                            "topic_share_window": float(r["topic_share_win"]),
                            "outflow_window": float(r["outflow_win"]),
                        }
                    )

            point_rows.extend(rows_h)
            dfh = pd.DataFrame(rows_h)
            if len(dfh) < 5 or dfh["topic_share_window"].nunique() < 2 or dfh["outflow_window"].nunique() < 2:
                summary_rows.append(
                    {
                        "topic_group": topic,
                        "horizon_months": h,
                        "n": int(len(dfh)),
                        "pearson_r": float("nan"),
                        "pearson_p": float("nan"),
                        "spearman_r": float("nan"),
                        "spearman_p": float("nan"),
                        "slope": float("nan"),
                        "slope_p": float("nan"),
                        "r2": float("nan"),
                        "status": "insufficient_data",
                        "method": "rolling_window_pool",
                    }
                )
                continue

            c = _safe_corr(dfh["topic_share_window"], dfh["outflow_window"])
            fit = sm.OLS(dfh["outflow_window"], sm.add_constant(dfh[["topic_share_window"]])).fit()
            summary_rows.append(
                {
                    "topic_group": topic,
                    "horizon_months": h,
                    "n": int(len(dfh)),
                    "pearson_r": c["pearson_r"],
                    "pearson_p": c["pearson_p"],
                    "spearman_r": c["spearman_r"],
                    "spearman_p": c["spearman_p"],
                    "slope": float(fit.params["topic_share_window"]),
                    "slope_p": float(fit.pvalues["topic_share_window"]),
                    "r2": float(fit.rsquared),
                    "status": "ok",
                    "method": "rolling_window_pool",
                }
            )

    # Annual topic composition (12-month complaint composition) vs 2024 outflow rate (cross-section).
    cross = topic_year.merge(base[["dong_cluster", "youth_outflow_rate"]], on="dong_cluster", how="left")
    cross = cross.dropna(subset=["youth_outflow_rate"]).copy()
    cross_rows: list[dict[str, object]] = []
    for topic in priority_topics:
        sub = cross[cross["topic_group"] == topic][["topic_share", "youth_outflow_rate"]].dropna()
        if len(sub) < 5 or sub["topic_share"].nunique() < 2 or sub["youth_outflow_rate"].nunique() < 2:
            cross_rows.append(
                {
                    "topic_group": topic,
                    "n": int(len(sub)),
                    "pearson_r": float("nan"),
                    "pearson_p": float("nan"),
                    "spearman_r": float("nan"),
                    "spearman_p": float("nan"),
                    "slope": float("nan"),
                    "slope_p": float("nan"),
                    "r2": float("nan"),
                    "status": "insufficient_data",
                    "method": "annual_cross_section",
                }
            )
            continue
        c = _safe_corr(sub["topic_share"], sub["youth_outflow_rate"])
        fit = sm.OLS(sub["youth_outflow_rate"], sm.add_constant(sub[["topic_share"]])).fit()
        cross_rows.append(
            {
                "topic_group": topic,
                "n": int(len(sub)),
                "pearson_r": c["pearson_r"],
                "pearson_p": c["pearson_p"],
                "spearman_r": c["spearman_r"],
                "spearman_p": c["spearman_p"],
                "slope": float(fit.params["topic_share"]),
                "slope_p": float(fit.pvalues["topic_share"]),
                "r2": float(fit.rsquared),
                "status": "ok",
                "method": "annual_cross_section",
            }
        )

    summary_df = pd.DataFrame(summary_rows).sort_values(["topic_group", "horizon_months"])
    points_df = pd.DataFrame(point_rows).sort_values(["topic_group", "horizon_months", "dong_cluster", "end_month"]) if point_rows else pd.DataFrame()
    cross_df = pd.DataFrame(cross_rows).sort_values("spearman_p", na_position="last")

    summary_df.to_csv(PROCESSED / "stats_topic_horizon_association_2024.csv", index=False, encoding="utf-8-sig")
    points_df.to_csv(PROCESSED / "topic_horizon_points_2024.csv", index=False, encoding="utf-8-sig")
    cross_df.to_csv(PROCESSED / "stats_topic_cross_section_2024.csv", index=False, encoding="utf-8-sig")
    return summary_df, points_df, cross_df


def complaint_correlation_tests() -> tuple[pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(PROCESSED / "complaint_mobility_join_2024.csv")

    y = "youth_outflow_rate"
    x_vars = [
        "complaints_per_1000_totalpop",
        "processing_days_median",
        "complaint_count",
        "total_pop",
        "youth_pop",
    ]

    rows: list[CorrResult] = []
    for x_col in x_vars:
        if x_col not in df.columns:
            continue
        sub = df[[x_col, y]].dropna()
        if len(sub) < 5:
            continue

        p = pearsonr(sub[x_col], sub[y])
        s = spearmanr(sub[x_col], sub[y], nan_policy="omit")
        ci_low, ci_high = _bootstrap_spearman(sub[x_col].to_numpy(), sub[y].to_numpy())

        rows.append(
            CorrResult(
                variable=x_col,
                n=int(len(sub)),
                pearson_r=float(p.statistic),
                pearson_p=float(p.pvalue),
                spearman_r=float(s.statistic),
                spearman_p=float(s.pvalue),
                spearman_ci_low=ci_low,
                spearman_ci_high=ci_high,
            )
        )

    test_df = pd.DataFrame([r.__dict__ for r in rows]).sort_values("spearman_p", ascending=True)
    test_df.to_csv(PROCESSED / "stats_outflow_complaint_tests_2024.csv", index=False, encoding="utf-8-sig")

    corr_cols = [c for c in [y] + x_vars if c in df.columns]
    corr_df = df[corr_cols].corr(numeric_only=True)
    corr_df.to_csv(PROCESSED / "corr_outflow_complaint_2024.csv", encoding="utf-8-sig")
    return test_df, df


def model_outflow(df: pd.DataFrame) -> pd.DataFrame:
    model_specs = [
        ("M1", ["complaints_per_1000_totalpop"]),
        ("M2", ["complaints_per_1000_totalpop", "processing_days_median"]),
        ("M3", ["complaints_per_1000_totalpop", "processing_days_median", "total_pop"]),
    ]

    rows: list[dict[str, object]] = []
    for model_name, features in model_specs:
        cols = ["youth_outflow_rate"] + [c for c in features if c in df.columns]
        sub = df[cols].dropna().copy()
        if len(sub) < 10:
            continue

        X = sm.add_constant(sub[[c for c in features if c in sub.columns]])
        y = sub["youth_outflow_rate"]
        fit = sm.OLS(y, X).fit()

        for pname, coef in fit.params.items():
            rows.append(
                {
                    "model": model_name,
                    "term": pname,
                    "n": int(fit.nobs),
                    "coef": float(coef),
                    "pvalue": float(fit.pvalues[pname]),
                    "ci_low": float(fit.conf_int().loc[pname, 0]),
                    "ci_high": float(fit.conf_int().loc[pname, 1]),
                    "r2": float(fit.rsquared),
                    "adj_r2": float(fit.rsquared_adj),
                }
            )

    out = pd.DataFrame(rows)
    out.to_csv(PROCESSED / "stats_outflow_models_2024.csv", index=False, encoding="utf-8-sig")
    return out


def sensitivity_analysis(df: pd.DataFrame) -> pd.DataFrame:
    base = df[["dong_cluster", "youth_in", "youth_out", "youth_pop", "youth_outflow_rate"]].dropna().copy()
    base_rank = base.sort_values("youth_outflow_rate", ascending=False)["dong_cluster"].tolist()
    base_top10 = set(base_rank[:10])

    scenarios = [
        ("base", 1.0, 1.0),
        ("low_bias", 0.9, 1.1),
        ("high_bias", 1.1, 0.9),
    ]

    rows = []
    for name, out_mult, in_mult in scenarios:
        temp = base.copy()
        temp["rate"] = ((temp["youth_out"] * out_mult) - (temp["youth_in"] * in_mult)) / temp["youth_pop"] * 100.0
        rank = temp.sort_values("rate", ascending=False)["dong_cluster"].tolist()
        top10 = set(rank[:10])
        overlap = len(top10.intersection(base_top10)) / 10.0

        rows.append(
            {
                "scenario": name,
                "out_multiplier": out_mult,
                "in_multiplier": in_mult,
                "top10_overlap_with_base": overlap,
                "max_rate": float(temp["rate"].max()),
                "min_rate": float(temp["rate"].min()),
            }
        )

    out = pd.DataFrame(rows)
    out.to_csv(PROCESSED / "stats_outflow_sensitivity_2024.csv", index=False, encoding="utf-8-sig")
    return out


def main() -> None:
    rank_outflow()
    panel, city = build_cluster_month_panel()
    monthly_assoc, monthly_lag = monthly_association_tests(panel)
    horizon_assoc, horizon_points = horizon_window_association(panel)
    topic_horizon, topic_points, topic_cross = topic_type_association(panel)
    tests, complaint_df = complaint_correlation_tests()
    models = model_outflow(complaint_df)
    sensitivity = sensitivity_analysis(complaint_df)

    summary = {
        "tests_rows": int(len(tests)),
        "models_rows": int(len(models)),
        "sensitivity_rows": int(len(sensitivity)),
        "monthly_panel_rows": int(len(panel)),
        "monthly_assoc_rows": int(len(monthly_assoc)),
        "monthly_lag_rows": int(len(monthly_lag)),
        "horizon_assoc_rows": int(len(horizon_assoc)),
        "horizon_points_rows": int(len(horizon_points)),
        "topic_horizon_rows": int(len(topic_horizon)),
        "topic_horizon_points_rows": int(len(topic_points)),
        "topic_cross_rows": int(len(topic_cross)),
        "months_in_city_series": int(len(city)),
        "economy_removed": True,
    }
    with (PROCESSED / "analysis_summary_v2.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
