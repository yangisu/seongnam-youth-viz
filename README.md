# 판교 그늘에 가려진 원도심 — 성남시 청년 양극화 데이터 분석

성남시 공공데이터 활용 시각화 경진대회 출품작 (마감: 2026-05-13).

분당·판교의 청년 유입과 수정·중원의 청년 유출이라는 **성남시 내부 양극화**를 데이터로 입증하고, 민원 데이터로 원인을 추적하며, 상권·법인 데이터로 결과를 보여주는 4단 분석.

## 4단 구조

1. **WHAT** — 행정동별 20-34세 순유출률 Choropleth
2. **WHERE TO** — 주민등록 전입·전출 OD Sankey
3. **WHY** — 동×민원 키워드 히트맵 + 비교 워드클라우드 + 분야별 시계열
4. **CONSEQUENCE** — 청년 유출 ↔ 벤처기업/가맹점 분포

## 디렉토리

```
seongnam-youth-viz/
├── data/
│   ├── raw/
│   │   ├── mois_population/      # 행안부 행정동 성·연령 인구 (CSV)
│   │   ├── mois_migration/       # 행안부 인구이동 (CSV)
│   │   ├── seongnam_dong/        # 성남시 동별 인구·세대 (보조)
│   │   ├── seongnam_complaint/   # data.seongnam.go.kr 동별 키워드
│   │   ├── epeople/              # 국민신문고 청년 민원 시계열
│   │   ├── venture/              # 성남시 벤처기업
│   │   ├── vendor/               # 가맹점·통신판매업
│   │   └── DOWNLOAD_URLS.md      # ★ 데이터 받는 법
│   ├── processed/                # 정제본 (자동 생성)
│   └── geojson/                  # 성남시 행정동 경계 (자동 확보 완료)
├── src/                          # 분석 스크립트 (01~06)
├── outputs/{figures,interactive,dashboard}/
└── docs/
```

## 실행 방법

```bash
# 1. 가상환경
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. 데이터 다운로드 → data/raw/DOWNLOAD_URLS.md 안내대로 raw/* 채우기

# 3. 정제·분석·시각화
python src/01_load_population.py    # 청년 순유출률
python src/02_load_od.py            # OD 흐름
python src/03_load_complaint.py     # 민원 키워드·시계열
python src/04_load_economy.py       # 벤처·가맹점
python src/05_analysis.py           # 파생 지표
python src/06_visualizations.py     # Folium/Plotly 산출물

# 4. 대시보드 (옵션)
streamlit run outputs/dashboard/app.py

# 5. Iterative Optimization (CTO workflow)
# - Re-plan automatically when correlations are weak
# - Optional auto-download if AUTO_DOWNLOAD_MANIFEST.csv exists
python src/08_iterative_optimizer.py --threshold 0.30 --max-iterations 4
python src/08_iterative_optimizer.py --auto-download --threshold 0.30 --max-iterations 4
```

Copy `docs/AUTO_DOWNLOAD_MANIFEST.example.csv` to
`data/raw/AUTO_DOWNLOAD_MANIFEST.csv` and fill source URLs for auto-download.
## 데이터 출처 (모두 data.go.kr 또는 GitHub 공개)

| 코드 | 출처 | 용도 |
|---|---|---|
| 15097972 | data.go.kr | 행정동 성·연령 인구 → 청년 모집단 |
| 15108093 | data.go.kr | 인구이동 → 전입·전출, OD |
| 15007386 | data.go.kr | 성남시 인구·세대 보조 |
| 성남시 벤처기업 | data.go.kr | 동별 경제활력 |
| data.seongnam.go.kr | 성남시 | 동별 민원 키워드 (수작업) |
| bigdata.epeople.go.kr | 국민신문고 | 청년 민원 시계열 |
| GeoJSON | [raqoon886/Local_HangJeongDong](https://github.com/raqoon886/Local_HangJeongDong) | 행정동 경계 (자동 확보) |

## 청년 정의

기본 **20-34세**. 인구이동 데이터에 연령 분해가 없으므로,
- 동별 **(전 연령) 전입·전출 총량 × (동별 청년 비중)** 으로 청년 이동량 추정
- 청년 비중 = `청년 인구 / 총인구` (mois_population 기반)
- **한계**: 청년의 이동성향이 전 연령 평균과 다를 수 있음 → 발표 시 명시

## 진행 현황 (2026-05-10)

- [x] 디렉토리·requirements·README
- [x] data.go.kr 인구이동 API 리버스엔지니어링 (`fetch_mois_migration.py`)
- [x] Phase A 페치 — 시군구 OD 12개월 × 17시도 (316 CSV)
- [x] Phase B 페치 — 동 OD 12개월 × 17시도 (108 CSV)
- [x] 모든 로더 스크립트 (01~04) — API 응답에 맞춤
- [x] 1단 Choropleth (시군구·동 단위)
- [x] 2단 Sankey (외부 outflow, inflow)
- [x] 3단 시계열 (시군구·동 핫스팟)
- [x] Streamlit 통합 대시보드
- [ ] 4단 민원 키워드 (data.seongnam.go.kr 수동수집 필요)
- [ ] 4단 경제 (성남시 벤처기업 CSV 추가 시 자동 통합)

## 핵심 발견

**"분당 vs 수정"이 아닌 "신축 vs 노후"가 진짜 양극화 축**

| 동 | 구 | 청년 순유출률 |
|---|---|---:|
| 신흥2동 (재개발) | 수정 | **-14.7%** (최대 유입) |
| 위례동 (신도시) | 수정 | -6.4% |
| 운중동 / 삼평동(판교) | 분당 | -1~-2% |
| **수내3동 / 정자동 / 이매2동** | **분당** | **+3~6%** (분당 1세대 유출!) |
| 상대원2동 / 수진1동 | 중원/수정 | +6~7% |
