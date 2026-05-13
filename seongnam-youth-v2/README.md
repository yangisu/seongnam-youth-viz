# seongnam-youth-v2

This v2 project rebuilds the analysis logic while keeping existing source datasets unchanged.
Economic consequence analysis is intentionally removed; this version focuses on mobility, complaint-context, statistical rigor, and policy prioritization.

## Run
```powershell
cd D:/compe/seongnam_dataanalysis/seongnam-youth-viz/seongnam-youth-v2
python -m venv .venv
. .venv/Scripts/Activate.ps1
pip install -r requirements.txt
./run_all.ps1
```

## Iterative Optimizer
The v2 pipeline now includes `src/08_iterative_optimizer.py` for repeated plan-analyze-replan cycles.

```powershell
# Optional: run standalone with raw-data auto download + pipeline refresh
python src/08_iterative_optimizer.py --auto-download --refresh-pipeline --threshold 0.35 --max-iterations 4
```

Outputs:
- `data/processed/iterative_feature_correlation_v2.csv`
- `data/processed/iterative_visualization_recommendations_v2.csv`
- `data/processed/iterative_optimizer_summary_v2.json`
- `docs/iterative_optimizer_report_YYYY-MM-DD.md`

Auto download:
- Create `../data/raw/AUTO_DOWNLOAD_MANIFEST.csv` from `../data/raw/AUTO_DOWNLOAD_MANIFEST.example.csv`
- Required columns: `subdir,url` (`filename` optional)

## Notes
- Shared source data is read from the sibling project folder (`../`).
- All v2 results are written only into `seongnam-youth-v2/data/processed`.
- Core judge-facing outputs:
  - `stats_outflow_complaint_tests_2024.csv`
  - `stats_outflow_models_2024.csv`
  - `stats_outflow_sensitivity_2024.csv`
  - `od_destination_clusters.csv`
  - `policy_priority_matrix_2024.csv`
