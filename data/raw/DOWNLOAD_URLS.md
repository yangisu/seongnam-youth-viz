# 데이터 다운로드 가이드

각 데이터셋을 받아 지정된 폴더에 넣어주세요. 모든 파일은 **CSV** 형식 권장 (API 호출이 가능하면 그것도 OK).

---

## 1. `mois_population/` — 행정동 성·연령별 주민등록 인구 (필수, 1단 분모)

- **데이터셋**: 행정안전부_지역별(행정동) 성별 연령별 주민등록 인구수
- **URL**: https://www.data.go.kr/data/15097972/fileData.do
- **받는 법**: "파일데이터 신청" → 다운로드 후 압축 해제
- **중요**: "1세별" 또는 "5세별" CSV (월별 갱신, 가장 최근 1개 파일이면 충분)
- **저장 경로**: `data/raw/mois_population/*.csv`

---

## 2. `mois_migration/` — 지역별 인구이동 현황 (필수, 1·2단 핵심)

- **데이터셋**: 행정안전부_지역별 인구이동 현황 (오픈 API)
- **URL**: https://www.data.go.kr/data/15108093/openapi.do
- **받는 법**: 활용신청(즉시 승인) → 인증키 발급 → API로 CSV 변환 또는 KOSIS에서 동일 데이터 CSV 다운로드 가능
  - **KOSIS 대안**: https://kosis.kr 에서 "행정구역(읍면동)/성/연령별 이동자수" 검색 → 성남시 시군구 4개(수정/중원/분당) 필터 → 다운로드
- **필요 컬럼**: 전출시도/시군구/행정동, 전입시도/시군구/행정동, 총인구수
- **기간**: 최근 12개월 (2025.01 ~ 2025.12 권장)
- **저장 경로**: `data/raw/mois_migration/*.csv`

---

## 3. `seongnam_dong/` — 성남시 동별 인구·세대 현황 (보조)

- **데이터셋**: 경기도 성남시_인구및세대_현황
- **URL**: https://www.data.go.kr/data/15007386/fileData.do
- **저장 경로**: `data/raw/seongnam_dong/*.csv`
- 용도: `mois_population`이 누락된 동 보강 / 19세이상·65세이상 비교 검증

---

## 4. `venture/` — 성남시 벤처기업 현황 (4단)

- **데이터셋**: 경기도 성남시_벤처기업현황
- **URL**: https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=성남시+벤처기업
- **저장 경로**: `data/raw/venture/*.csv`
- 자동으로 **주소 컬럼에서 'XX동' 추출**해 동별 카운트로 변환됨

---

## 5. `vendor/` — 성남사랑상품권 가맹점 / 통신판매업 (4단 보조)

- **데이터셋 A**: 경기도 성남시_성남사랑상품권_가맹점현황 (API)
- **데이터셋 B**: 경기도 성남시_통신판매업_현황 (CSV)
- **URL**: https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=성남시
- **저장 경로**: `data/raw/vendor/*.csv`

---

## 6. `seongnam_complaint/` — 동별 민원 키워드 (3단 ★ 핵심)

- **출처**: data.seongnam.go.kr (성남시 자체 데이터 포털)
- **수집 방법**: 자동 스크래핑이 어려움 → 동별로 수작업 수집
- **CSV 컬럼 (필수)**: `행정동, 키워드, 건수, 긍정비율, 부정비율`
- **저장 경로**: `data/raw/seongnam_complaint/keywords.csv` (단일 파일 OK)

---

## 7. `epeople/` — 국민신문고 분야별 청년 민원 (3단 시계열)

- **출처**: bigdata.epeople.go.kr (인증 필요)
- **필터**: 지역=성남시, 연령=20·30대, 분야=교통/도시/환경/주택건축/보건/노동/교육 등
- **CSV 컬럼**: `일자, 지역, 기관, 연령, 분야, 신청건수`
- **저장 경로**: `data/raw/epeople/*.csv`

---

## ✅ GeoJSON (이미 자동 다운로드 완료)

`data/geojson/seongnam_admdong.geojson` — 성남시 49개 행정동 경계 (출처: [raqoon886/Local_HangJeongDong](https://github.com/raqoon886/Local_HangJeongDong)).

별도 작업 불필요.

---

## 우선순위

| 순위 | 데이터 | 이유 |
|---|---|---|
| 1 | mois_population, mois_migration | 1단(WHAT) + 2단(WHERE TO) — 프로젝트 핵심 |
| 2 | seongnam_complaint | 3단(WHY) — 차별화 포인트 |
| 3 | venture | 4단(CONSEQUENCE) |
| 4 | epeople, seongnam_dong, vendor | 보강 |

1·2번만 있어도 1·2·4단은 실행 가능. 3번이 추가되면 4단 모두 완성.
