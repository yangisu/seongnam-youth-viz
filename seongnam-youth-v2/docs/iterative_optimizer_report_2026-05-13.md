# Iterative Optimizer Report (2026-05-13)

## Execution Log
- [skip] AUTO_DOWNLOAD_MANIFEST.csv not found
- [ok] saved: D:\compe\seongnam_dataanalysis\seongnam-youth-viz\seongnam-youth-v2\data\processed\iterative_feature_correlation_v2.csv
- [ok] saved: D:\compe\seongnam_dataanalysis\seongnam-youth-viz\seongnam-youth-v2\data\processed\iterative_visualization_recommendations_v2.csv

## Iteration Best History
| iteration | stage | feature | spearman_r | abs_spearman_r | n |
|---:|---|---|---:|---:|---:|
| 1 | raw_features | complaint_count | 0.3246 | 0.3246 | 30 |
| 2 | engineered_features | complaint_count__x__internal_moves_per_1000_youth | 0.4242 | 0.4242 | 30 |

## Best Signal
- feature: `complaint_count__x__internal_moves_per_1000_youth`
- spearman_r: `0.4242` (abs=0.4242)
- threshold: `0.35`
- quality: **strong**

## Top 12 Features
| rank | iteration | stage | feature | spearman_r | abs_spearman_r | n |
|---:|---:|---|---|---:|---:|---:|
| 1 | 2 | engineered_features | complaint_count__x__internal_moves_per_1000_youth | 0.4242 | 0.4242 | 30 |
| 2 | 1 | raw_features | complaint_count | 0.3246 | 0.3246 | 30 |
| 3 | 2 | engineered_features | complaint_count | 0.3246 | 0.3246 | 30 |
| 4 | 2 | engineered_features | complaint_count__z | 0.3246 | 0.3246 | 30 |
| 5 | 2 | engineered_features | complaint_count__log1p | 0.3246 | 0.3246 | 30 |
| 6 | 1 | raw_features | internal_moves_per_1000_youth | 0.3157 | 0.3157 | 30 |
| 7 | 2 | engineered_features | internal_moves_per_1000_youth | 0.3157 | 0.3157 | 30 |
| 8 | 2 | engineered_features | internal_moves_per_1000_youth__z | 0.3157 | 0.3157 | 30 |
| 9 | 2 | engineered_features | internal_moves_per_1000_youth__log1p | 0.3157 | 0.3157 | 30 |
| 10 | 1 | raw_features | processed_count | 0.2743 | 0.2743 | 30 |
| 11 | 2 | engineered_features | processed_count | 0.2743 | 0.2743 | 30 |
| 12 | 2 | engineered_features | processed_count__z | 0.2743 | 0.2743 | 30 |

## Visualization Recommendations
| feature | visual | rationale |
|---|---|---|
| complaint_count__x__internal_moves_per_1000_youth | scatter with trendline | Interaction feature should be interpreted as a bivariate relationship. |
| complaint_count | sorted bar chart | Single metric ranking is best communicated with ordered bars. |
| complaint_count | sorted bar chart | Single metric ranking is best communicated with ordered bars. |
| complaint_count__z | sorted bar chart | Single metric ranking is best communicated with ordered bars. |
| complaint_count__log1p | sorted bar chart | Single metric ranking is best communicated with ordered bars. |
| internal_moves_per_1000_youth | sorted bar chart | Single metric ranking is best communicated with ordered bars. |
| internal_moves_per_1000_youth | sorted bar chart | Single metric ranking is best communicated with ordered bars. |
| internal_moves_per_1000_youth__z | sorted bar chart | Single metric ranking is best communicated with ordered bars. |