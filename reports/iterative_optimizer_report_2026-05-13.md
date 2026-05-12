# 반복형 분석 리포트 (2026-05-13)

## 실행 로그
- [skip] AUTO_DOWNLOAD_MANIFEST.csv 없음 (자동 다운로드 미실행)
- [skip] --skip-pipeline 옵션으로 01~05 실행 생략
- [ok] saved: data\processed\iterative_feature_correlation.csv

## 최적 피처 결과
- 목표변수 대비 최고 절대상관: `청년_인구` (corr=-0.3973, abs=0.3973)
- 판정 기준(threshold): 0.30
- 품질 판정: **insufficient_data**

## 반복 단계별 최고 피처
- iter 1 / raw_features: `청년_인구` (corr=-0.3973, abs=0.3973)
- iter 2 / engineered_iter_2: `청년_인구` (corr=-0.3973, abs=0.3973)

## TOP 10 상관 피처
| rank | iteration | stage | feature | corr | abs_corr | n |
|---|---:|---|---|---:|---:|---:|
| 1 | 1 | raw_features | 청년_인구 | -0.3973 | 0.3973 | 50 |
| 2 | 2 | engineered_iter_2 | 청년_인구 | -0.3973 | 0.3973 | 50 |

## 재계획 규칙
- 최고 절대상관이 `0.30` 미만이면 약한 상관으로 간주하고 추가 데이터 결합을 권장.
- 우선 결합 후보: 벤처/가맹점의 행정동 주소 데이터, 임대료/주택가격, 대중교통 접근성, 일자리 지표.