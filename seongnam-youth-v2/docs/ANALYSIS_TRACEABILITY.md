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

## Chapter 3 (MAIN EVIDENCE: 정책 우선순위 + 신축/노후 지역군)
- What was analyzed:
  - Intervention tiers (A/B/C/D) and axis differences (`신축·재정비` vs `노후·정체`) in complaint/outflow patterns.
  - Claim chain to make conclusion derivation explicit (claim -> data -> processing -> numeric result -> limitation).
- Data used:
  - `complaint_mobility_join_2024.csv`
  - `cluster_month_panel_2024.csv`
  - `od_youth_intra_seongnam_dong.csv`
  - `policy_priority_matrix_2024.csv`
  - `policy_newold_axis_mapping_by_cluster_2024.csv`
  - `policy_newold_group_comparison_2024.csv`
  - `policy_newold_topic_group_comparison_2024.csv`
  - `claim_chain_*.csv`
  - `claim_chain_*.json`
  - `Seongnam Youth Polarization _standalone_.html` (axis-definition context labels)
- Processing:
  - High-outflow / persistent-outflow / high-complaint flags and weighted priority scoring.
  - Axis typing by cluster (`신축·재정비`, `노후·정체`, `혼합/전이`) and grouped complaint/outflow summaries.
  - Topic-composition comparison between `신축·재정비` and `노후·정체` groups (share-difference view).
- What result means:
  - Tiers identify urgency of intervention.
  - Axis comparison clarifies whether complaint burden and outflow pressure are concentrated by urban-structure type.
  - `신축·재정비` / `노후·정체` are region-group labels (grouped administrative-dong clusters), not single dongs.
- Site outputs:
  - Tier criteria, priority, risk charts + axis complaint visual and axis summary table.
  - Alternative-view charts: destination-bucket composition and concentration(HHI).
  - Claim chain table + anti-overclaim guardrails.
  - `outputs/site/chart_data/chapter4_priority_matrix.csv`
  - `outputs/site/chart_data/chapter4_policy_newold_axis_mapping.csv`
  - `outputs/site/chart_data/chapter4_policy_newold_group_comparison.csv`
  - `outputs/site/chart_data/chapter4_policy_newold_topic_group_comparison.csv`
  - `outputs/site/chart_data/chapter4_axis_destination_bucket_mix_by_group.csv`
  - `outputs/site/chart_data/chapter4_axis_destination_bucket_concentration_by_group.csv`
  - `outputs/site/chart_data/chapter4_axis_topic_mix_by_group.csv`
  - `outputs/site/chart_data/chapter4_axis_topic_concentration_by_group.csv`
  - `outputs/site/chart_data/chapter4_axis_complaint_findings.csv`
  - `outputs/site/chart_data/chapter4_axis_complaint_summary.csv`
  - `outputs/site/chart_data/chapter4_axis_context_evidence.csv`
  - `outputs/site/chart_data/chapter4_claim_chain_table.csv`
  - `outputs/site/chart_data/chapter4_cross_section_tests.csv`
  - `outputs/site/chart_data/chapter4_policy_relations.csv`
  - `outputs/site/chart_data/chapter4_models.csv`
  - `outputs/site/chart_data/chapter4_sensitivity.csv`

## Chapter 4 (CLAIM CHAIN: 결론 도출 과정 검증)
- What was analyzed:
  - Claim-by-claim evidence chain to reduce logical leap from findings to conclusions.
- Data used:
  - `claim_chain_*.csv`
  - `claim_chain_*.json`
- Processing:
  - Standardized table: claim -> data -> formula -> numeric result -> limitation.
  - Explicit guardrails for non-causal interpretation and region-group level claims.
- What result means:
  - Judges can audit exactly what each conclusion is based on and where interpretation must stop.
- Site outputs:
  - `outputs/site/chart_data/chapter4_claim_chain_table.csv`
