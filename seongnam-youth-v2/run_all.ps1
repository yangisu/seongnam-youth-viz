$ErrorActionPreference = "Stop"

Write-Host "[1/10] validate inputs"
python src/00_validate_inputs.py

Write-Host "[2/10] load population/migration baseline"
python src/01_load_population.py

Write-Host "[3/10] load OD baseline"
python src/02_load_od.py

Write-Host "[4/10] parse complaint 2024"
python src/03_load_complaint_2024.py

Write-Host "[5/10] run statistical analysis"
python src/05_analysis.py

Write-Host "[6/10] build destination clusters and policy priority"
python src/06_policy_focus.py

Write-Host "[7/10] run iterative optimizer"
python src/08_iterative_optimizer.py --threshold 0.35 --max-iterations 4

Write-Host "[8/10] run axis additional analysis"
python src/09_axis_additional_analysis.py

Write-Host "[9/10] build claim chain"
python src/10_claim_chain.py

Write-Host "[10/10] build html site"
python src/07_build_site.py

Write-Host "[done] v2 pipeline complete"
