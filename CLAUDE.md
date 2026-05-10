# Project Context for Claude (Design / Code)

> 이 파일은 Claude Design / Claude Code가 프로젝트 맥락을 빠르게 파악하도록 작성됩니다.

## TL;DR

성남시 공공데이터 활용 시각화 경진대회 출품작 (마감 2026-05-13).
**기존 가설("분당 유입 / 수정 유출")을 데이터로 뒤집고**, 진짜 양극화 축은
**"신축 아파트로의 동 단위 청년 이동"**임을 발견했습니다.

## 한 문장 narrative

> 판교의 빛은 이미 식었다 — 성남 청년 양극화의 진짜 축은 시군구가 아닌 **동 단위 신축 vs 노후**.

## 핵심 발견 (꼭 시각에 담아야 함)

| 동 | 구 | 청년(20-34) 순유출률 | 한줄 |
|---|---|---:|---|
| 신흥2동 | 수정 | **-14.7%** | 재개발 신축 — 압도적 유입 |
| 위례동 | 수정 | -6.4% | 위례신도시 |
| 운중동 / 삼평동 | 분당 | -1~2% | 판교 신축 |
| **수내3동 / 정자동 / 이매2동** | **분당** | **+3~6%** | 1990년대 분당 1세대 — 청년 유출 |
| 상대원2동 / 수진1동 / 태평1·4동 | 중원/수정 | +6~7% | 노후 다세대 |

## 데이터 출처

| 코드 | 출처 | 내용 | 기간 |
|---|---|---|---|
| 15097972 | data.go.kr | 행정동 성·연령별 주민등록 인구 | 2026-03-31 |
| 15108093 | data.go.kr | 지역별 인구이동 현황 (API) | 2024.01–12 |
| GeoJSON | github.com/raqoon886/Local_HangJeongDong | 행정동 경계 | — |

## 4단 분석 구조

1. **WHAT** — 동별 청년 순유출률 Choropleth
2. **WHERE TO** — 동 → 외부 시군구 OD Sankey
3. **WHY** — (진행 중) data.seongnam.go.kr 동별 민원 키워드
4. **CONSEQUENCE** — (진행 중) 성남시 벤처기업·가맹점 분포

## 디렉토리 의미

```
seongnam-youth-viz/
├── data/
│   ├── geojson/seongnam_admdong.geojson  ← 50개 features (49동 + 위례동 분리)
│   ├── processed/                         ← 분석용 정제 CSV (git 포함)
│   └── raw/                               ← 원본 (git 제외, DOWNLOAD_URLS.md 참조)
├── src/
│   ├── fetch_mois_migration.py  ← API 페치 (Phase A 시군구 + B 동)
│   ├── 01_load_population.py    ← 인구·이동 통합
│   ├── 02_load_od.py            ← OD 매트릭스
│   ├── 06_visualizations.py     ← 6개 인터랙티브 시각화 생성
│   └── 07_export_for_web.py     ← 웹용 단일 JSON 빌드
└── outputs/
    ├── site/index.html          ← ★ 메인 산출물 (단일 파일 대시보드)
    ├── site/data.js             ← 임베드 데이터 (224 KB)
    ├── interactive/*.html       ← 개별 시각화 (Folium / Plotly)
    └── dashboard/app.py         ← Streamlit 대안
```

## Claude Design에 부탁할 만한 것

- **`outputs/site/index.html`을 더 영화적/잡지 레이아웃으로 재디자인** — 데이터(`data.js`)는 그대로 사용, 시각만 변경
- **PPT용 정적 슬라이드 6장** — 4단 구조에 맞춰 한 슬라이드씩 + 표지·결론
- **Sankey 대신 chord/arc diagram 등 다른 OD 표현** 실험
- **Mobile-first** 단일 페이지로 변환

## 디자인 가이드 (제안 출발점)

- 색상: 유출 = `#f97316` (orange), 유입 = `#38bdf8` (sky), 강조 = `#facc15` (gold)
- 폰트: Pretendard
- 분위기: 다크 테마 + 그라데이션 noise (현재 `index.html` 참조)
- 핵심 카피: **"판교의 빛은 이미 식었다"**

## 개발 진행도 (2026-05-10)

- [x] data.go.kr API 리버스엔지니어링 + 페치 (424 CSV)
- [x] 1단·2단·3단 시계열 시각화 6종
- [x] Streamlit 대시보드
- [x] 단일 HTML 사이트 (`outputs/site/`)
- [ ] 3단 민원 키워드 (data.seongnam.go.kr 수동 수집 필요)
- [ ] PPT 슬라이드 (Claude Design으로 진행 예정)
