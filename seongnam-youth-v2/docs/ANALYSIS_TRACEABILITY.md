# Analysis Traceability (v2)

## Chapter 1 (WHAT: 동별 순유출 지형)
- What was analyzed:
  - Which dongs are net youth outflow hotspots vs net inflow zones.
- Data used:
  - `youth_migration_by_dong.csv`
  - `youth_population_by_dong.csv`
  - `seongnam_admdong.geojson`
- Processing:
  - `youth_outflow_rate = (youth_out - youth_in) / youth_pop * 100`
  - map join by dong name and metric attachment to each polygon.
- What result means:
  - Higher positive outflow-rate dongs indicate stronger youth retention pressure.
- Site outputs:
  - Choropleth + dong detail panel.
  - `outputs/site/chart_data/chapter1_dong_metrics.csv`

## Chapter 2 (WHERE: 성남 내부 재배치 경로)
- What was analyzed:
  - Where youth moves inside Seongnam (origin cluster -> destination cluster).
- Data used:
  - `od_youth_intra_seongnam_dong.csv`
- Processing:
  - Dong OD flows aggregated to cluster matrix.
  - Largest corridors extracted for rank view.
- What result means:
  - High-volume origin->destination pairs identify dominant in-city relocation channels.
- Site outputs:
  - Intra-cluster heatmap + top corridor table.
  - `outputs/site/chart_data/chapter2_intra_cluster_matrix_top12.csv`
  - `outputs/site/chart_data/chapter2_intra_cluster_pairs.csv`

## Chapter 3 (WHEN: 월별 민원-이동 연관)
- What was analyzed:
  - Whether complaint pressure co-moves with youth outflow over time.
- Data used:
  - `od_youth_monthly_dong.csv`
  - `complaint_by_cluster_month_2024.csv`
  - `youth_population_by_dong.csv`
- Processing:
  - Monthly city rollup (`youth_net`, `complaint_count`).
  - Horizon windows (3/6/12 months) and association tests (Spearman/Pearson/OLS).
- What result means:
  - Sign and strength of coefficients show whether complaint pressure and outflow pressure move together.
- Site outputs:
  - Monthly dual-axis trend + horizon scatter + association table.
  - `outputs/site/chart_data/chapter3_monthly_city.csv`
  - `outputs/site/chart_data/chapter3_monthly_lag_points.csv`
  - `outputs/site/chart_data/chapter3_monthly_assoc.csv`
  - `outputs/site/chart_data/chapter3_horizon_assoc.csv`
  - `outputs/site/chart_data/chapter3_horizon_points.csv`

## Chapter 4 (EVIDENCE: 정책 우선순위 + 신축/노후 민원축)
- What was analyzed:
  - Intervention tiers (A/B/C/D) and axis differences (`신축·재정비` vs `노후·정체`) in complaint/outflow patterns.
- Data used:
  - `complaint_mobility_join_2024.csv`
  - `cluster_month_panel_2024.csv`
  - `od_youth_intra_seongnam_dong.csv`
  - `policy_priority_matrix_2024.csv`
  - `policy_newold_axis_mapping_by_cluster_2024.csv`
  - `policy_newold_group_comparison_2024.csv`
  - `policy_newold_topic_group_comparison_2024.csv`
  - `Seongnam Youth Polarization _standalone_.html` (axis-definition context labels)
- Processing:
  - High-outflow / persistent-outflow / high-complaint flags and weighted priority scoring.
  - Axis typing by cluster (`신축·재정비`, `노후·정체`, `혼합/전이`) and grouped complaint/outflow summaries.
- What result means:
  - Tiers identify urgency of intervention.
  - Axis comparison clarifies whether complaint burden and outflow pressure are concentrated by urban-structure type.
- Site outputs:
  - Tier criteria, priority, risk charts + axis complaint visual and axis summary table.
  - `outputs/site/chart_data/chapter4_priority_matrix.csv`
  - `outputs/site/chart_data/chapter4_policy_newold_axis_mapping.csv`
  - `outputs/site/chart_data/chapter4_policy_newold_group_comparison.csv`
  - `outputs/site/chart_data/chapter4_policy_newold_topic_group_comparison.csv`
  - `outputs/site/chart_data/chapter4_axis_complaint_findings.csv`
  - `outputs/site/chart_data/chapter4_axis_complaint_summary.csv`
  - `outputs/site/chart_data/chapter4_axis_context_evidence.csv`
  - `outputs/site/chart_data/chapter4_cross_section_tests.csv`
  - `outputs/site/chart_data/chapter4_policy_relations.csv`
  - `outputs/site/chart_data/chapter4_models.csv`
  - `outputs/site/chart_data/chapter4_sensitivity.csv`

## Chapter 5 (ITERATIVE LOOP: 반복형 신호 강화)
- What was analyzed:
  - How much engineered features improve association compared to raw features.
- Data used:
  - `iterative_feature_correlation_v2.csv`
  - `iterative_optimizer_summary_v2.json`
  - `iterative_visualization_recommendations_v2.csv`
  - `policy_priority_matrix_2024.csv` (for interaction scatter points)
- Processing:
  - Iteration-wise best absolute Spearman extraction.
  - Raw -> engineered/interactions loop progression tracking.
- What result means:
  - Improvement by iteration validates whether repeated feature engineering materially increases explanatory signal.
- Site outputs:
  - Loop progress chart + loop table + top-signal chart + interaction scatter + visualization recommendations.
  - `outputs/site/chart_data/chapter5_iterative_feature_correlation.csv`
  - `outputs/site/chart_data/chapter5_iterative_loop_progress.csv`
  - `outputs/site/chart_data/chapter5_iterative_visualization_recommendations.csv`
