# DATA CONTRACT V2

## Input data (shared, read-only)
- `D:/compe/seongnam_dataanalysis/seongnam-youth-viz/data_by_type/*.xlsx`
- `D:/compe/seongnam_dataanalysis/seongnam-youth-viz/data_by_region/*.xlsx`
- `D:/compe/seongnam_dataanalysis/seongnam-youth-viz/data/processed/*.csv` (mobility seed)

## Output data (v2)
- `data/processed/input_validation_report.json`
- `data/processed/youth_population_by_dong.csv`
- `data/processed/youth_migration_by_dong.csv`
- `data/processed/youth_migration_by_sgg.csv`
- `data/processed/od_youth_*.csv`
- `data/processed/complaint_events_2024.csv`
- `data/processed/complaint_by_cluster_month_2024.csv`
- `data/processed/complaint_topic_by_cluster_2024.csv`
- `data/processed/complaint_mobility_join_2024.csv`
- `data/processed/complaint_parse_quality_2024.json`
- `data/processed/stats_outflow_complaint_tests_2024.csv`
- `data/processed/stats_outflow_models_2024.csv`
- `data/processed/stats_outflow_sensitivity_2024.csv`
- `data/processed/od_destination_clusters.csv`
- `data/processed/od_destination_profiles_by_dong.csv`
- `data/processed/policy_priority_matrix_2024.csv`
- `data/processed/policy_focus_summary_2024.json`
- `data/processed/analysis_summary_v2.json`

## Metric policy
- `complaints_per_1000_totalpop`: official comparison metric.
- `complaints_per_1000_youth_legacy`: backward-compatible legacy metric.
- Complaint data is interpreted as contextual friction signal, not youth-only causal evidence.
