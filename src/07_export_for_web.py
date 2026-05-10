"""Web 대시보드용 JSON 데이터 + GeoJSON을 단일 .js 파일로 export."""
import json
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROC = ROOT / "data" / "processed"
GEO = ROOT / "data" / "geojson" / "seongnam_admdong.geojson"
OUT = ROOT / "outputs" / "site" / "data.js"
OUT.parent.mkdir(parents=True, exist_ok=True)

dong = pd.read_csv(PROC / "youth_migration_by_dong.csv")
sgg = pd.read_csv(PROC / "youth_migration_by_sgg.csv")
m_sgg = pd.read_csv(PROC / "od_youth_monthly_sgg.csv")
m_dong = pd.read_csv(PROC / "od_youth_monthly_dong.csv")
od_out = pd.read_csv(PROC / "od_youth_seongnam_dong_to_outside.csv")
od_in = pd.read_csv(PROC / "od_youth_seongnam_dong_inflow.csv")
od_intra = pd.read_csv(PROC / "od_youth_intra_seongnam_dong.csv")
pop = pd.read_csv(PROC / "youth_population_by_dong.csv")

with open(GEO, encoding="utf-8") as f:
    geo = json.load(f)

# 동별 메타 + 구 매핑 추가
sgg_map = dict(zip(pop["dong"], pop["sgg"]))
for f in geo["features"]:
    nm = f["properties"]["adm_nm"].split()[-1]
    f["properties"]["dong"] = nm
    f["properties"]["sgg_full"] = sgg_map.get(nm, "")
    row = dong[dong["dong"] == nm]
    if not row.empty:
        r = row.iloc[0]
        f["properties"]["youth_pop"] = int(r["청년_인구"])
        f["properties"]["youth_in"] = int(r["청년_전입"])
        f["properties"]["youth_out"] = int(r["청년_전출"])
        f["properties"]["net"] = int(r["청년_순이동_6m"])
        f["properties"]["rate"] = float(round(r["청년_순유출률"], 2))

# OD: 외부 시군구 라벨 단축
od_out["dest"] = (od_out["dest_sido"].str.replace("특별자치도|특별자치시|특별시|광역시|도", "", regex=True).str.strip()
                  + " " + od_out["dest_sgg"])
od_in["origin"] = (od_in["origin_sido"].str.replace("특별자치도|특별자치시|특별시|광역시|도", "", regex=True).str.strip()
                   + " " + od_in["origin_sgg"])

# 동별 TOP 5 destination 흐름 (Sankey 단순화)
top_per_dong = (od_out.groupby(["origin_dong", "dest"])["n"].sum().reset_index()
                .sort_values(["origin_dong", "n"], ascending=[True, False]))
top_per_dong["rk"] = top_per_dong.groupby("origin_dong")["n"].rank("first", ascending=False)
top_per_dong = top_per_dong[top_per_dong["rk"] <= 5].drop(columns=["rk"])

# 월별 시계열
m_dong["m"] = m_dong["statsYm"].astype(str)
m_sgg["m"] = m_sgg["statsYm"].astype(str)

payload = {
    "geo": geo,
    "dong": dong.to_dict(orient="records"),
    "sgg": sgg.to_dict(orient="records"),
    "monthly_sgg": m_sgg[["m", "sgg", "전입", "전출", "순이동"]].to_dict(orient="records"),
    "monthly_dong": m_dong[["m", "dong", "전입", "전출", "순이동"]].to_dict(orient="records"),
    "od_out": top_per_dong.to_dict(orient="records"),
    "od_in_top": od_in.groupby(["origin", "dest_dong"])["n"].sum().reset_index()
                  .sort_values("n", ascending=False).head(300).to_dict(orient="records"),
    "od_intra": od_intra.head(150).to_dict(orient="records"),
    "summary": {
        "total_in": int(sgg["청년_전입"].sum()),
        "total_out": int(sgg["청년_전출"].sum()),
        "n_dong": int(len(dong)),
        "youth_pop": int(pop["청년_인구"].sum()),
    },
}

with open(OUT, "w", encoding="utf-8") as f:
    f.write("window.SN_DATA = ")
    json.dump(payload, f, ensure_ascii=False)
    f.write(";")

print(f"[저장] {OUT}  ({OUT.stat().st_size/1024:.0f} KB)")
print(f"  dong={len(dong)}, monthly_dong={len(m_dong)}, od_out={len(top_per_dong)}, geo features={len(geo['features'])}")
