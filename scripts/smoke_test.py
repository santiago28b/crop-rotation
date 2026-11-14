"""
End-to-end smoke test against the live upstream APIs, through the FastAPI app (no server needed).

    .venv/bin/python scripts/smoke_test.py            # all demo fields
    .venv/bin/python scripts/smoke_test.py nampa      # one field

Demo fields are ~1-ha squares. Responses are saved to data/processed/smoke_<name>_{profile,insights}.json
so the UI and economics teammates can code against real output.
"""

import json
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app

OUT = Path(__file__).resolve().parent.parent / "data" / "processed"


def square(lat, lon, half_deg=0.0005):
    return {"type": "Polygon", "coordinates": [[
        [lon - half_deg, lat - half_deg], [lon + half_deg, lat - half_deg],
        [lon + half_deg, lat + half_deg], [lon - half_deg, lat + half_deg], [lon - half_deg, lat - half_deg]]]}


FIELDS = {
    # irrigated grain/bean/beet country, Treasure Valley Idaho (Greenleaf, west of Nampa; CDL 2024 = Dry Beans)
    "nampa": dict(geom=square(43.6750, -116.8300),
                  resources={"irrigation": {"type": "sprinkler", "seasonal_allotment_mm": 600}, "harvesters": ["grain_combine"]}),
    # Andean highland smallholder, Boyacá, Colombia (~2,600 m): potatoes, maize, beans
    "boyaca": dict(geom=square(5.5500, -73.3600),
                   resources={"irrigation": {"type": "none"}, "harvesters": ["manual"]}),
    # southern hemisphere dryland maize, Free State, South Africa
    "freestate": dict(geom=square(-28.4500, 26.6000),
                      resources={"irrigation": {"type": "none"}, "harvesters": ["grain_combine"]}),
}


def main():
    names = sys.argv[1:] or list(FIELDS)
    client = TestClient(app)
    OUT.mkdir(parents=True, exist_ok=True)

    for name in names:
        f = FIELDS[name]
        t = time.time()
        r = client.post("/fields/profile", json={"geometry": f["geom"], "name": name})
        print(f"\n=== {name}: /fields/profile {r.status_code} in {time.time() - t:.1f}s ===")
        if r.status_code != 200:
            print(r.text[:800])
            continue
        p = r.json()
        (OUT / f"smoke_{name}_profile.json").write_text(json.dumps(p, indent=2))
        fi, cl, so, hi = p["field"], p["climate"], p["soil"], p["crop_history"]
        print(f"field: {fi['centroid_lat']},{fi['centroid_lon']} {fi['area_ha']} ha elev {fi['elevation_m']} m conus={fi['in_conus']} hemi={fi['hemisphere']}")
        print(f"soil:  {so['source'].split(' (')[0]} | {so.get('name')} | {so['texture_class']} pH {so['ph']} OM {so['organic_matter_pct']}% AWC {so['awc_mm_per_m']} mm/m drainage={so['drainage_class']}")
        b, rc = cl["baseline"], cl["recent"]
        print(f"climate: season months {cl['growing_season_months']} frost_free_climate={cl['frost_free_climate']}")
        print(f"  baseline {b['years']}: frost-free {b['frost_free_days']} d, GDD {b['gdd_base10_season']}, hot days {b['hot_days_35c']}, rain {b['precip_year_mm']} mm, ETo {b['eto_year_mm']} mm, onset doy {b['rain_onset_doy']}")
        print(f"  recent   {rc['years']}: frost-free {rc['frost_free_days']} d, GDD {rc['gdd_base10_season']}, hot days {rc['hot_days_35c']}, rain {rc['precip_year_mm']} mm, ETo {rc['eto_year_mm']} mm, onset doy {rc['rain_onset_doy']}")
        print(f"  shift: frost-free {cl['shift']['frost_free_days']} d, last spring frost {cl['shift']['last_spring_frost_doy']} d, hot days {cl['shift']['hot_days_35c']}, trend/decade {cl['trend_per_decade']}")
        print(f"history: available={hi['available']} {hi['note'][:120]}")
        for y in hi["years"]:
            print(f"  {y['year']}: {y['crop_label']} ({y['crop_id']}) conf {y['confidence']}")

        history = hi["years"] if hi["available"] else []
        t = time.time()
        r = client.post("/fields/insights", json={"geometry": f["geom"], "name": name, "history": history,
                                                  "resources": f["resources"], "priorities": {"water": 1, "soil_health": 1, "income": 1, "low_risk": 1}})
        print(f"--- /fields/insights {r.status_code} in {time.time() - t:.1f}s ---")
        if r.status_code != 200:
            print(r.text[:800])
            continue
        ins = r.json()
        (OUT / f"smoke_{name}_insights.json").write_text(json.dumps(ins, indent=2))
        print(f"{len(ins['candidates'])} candidates, {len(ins['rejected'])} rejected")
        for c in ins["candidates"][:10]:
            pw, hw, w, rot = c["plant_window"], c["harvest_window"], c["water"], c["rotation"]
            risks = ",".join(f"{k}={v['level'][0]}" for k, v in c["risks"].items())
            print(f"  {c['score']:.2f} {c['crop_id']:<14} plant doy {pw['start_doy']}-{pw['end_doy']} (best {pw['best_doy']}, shift {pw['shift_days_vs_baseline']}) "
                  f"harvest p50 {hw['p50_doy']} | need {w['crop_need_mm']:.0f} rain {w['effective_rain_mm']:.0f} irr {w['irrigation_need_mm']:.0f} P(rain) {w['rainfed_success_prob']} "
                  f"| suit c{c['suitability']['climate']:.2f} s{c['suitability']['soil']:.2f} | yield x{rot['yield_modifier']} N+{c['fertilizer']['n_credit_from_previous_kg_ha']:.0f} | {risks}")
        for rj in ins["rejected"]:
            print(f"  REJECT {rj['crop_id']:<14} {rj['reason']}")


if __name__ == "__main__":
    main()
