"""
USDA NRCS Soil Data Access (SSURGO) — US only, no key.
Docs: https://sdmdataaccess.nrcs.usda.gov/

Dominant soil component at the field centroid + its 0-30 cm horizons. Richer than
SoilGrids (drainage class, slope, measured AWC) so it's preferred inside CONUS.
"""

from __future__ import annotations

import httpx

from app import cache
from app.schemas import SoilProfile
from app.sources.soilgrids import usda_texture

API_URL = "https://sdmdataaccess.sc.egov.usda.gov/Tabular/post.rest"


async def _query(sql: str) -> list[list]:
    key = {"sql": sql}
    data = cache.get("ssurgo", key)
    if data is None:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(API_URL, json={"format": "JSON+COLUMNNAME", "query": sql})
            resp.raise_for_status()
            data = resp.json()
        cache.put("ssurgo", key, data)
    return data.get("Table", [])


async def fetch_soil(lat: float, lon: float) -> SoilProfile | None:
    comp_sql = f"""
        SELECT TOP 1 mu.muname, mu.mukey, c.cokey, c.compname, c.comppct_r, c.drainagecl,
               c.slope_r, c.taxorder, c.hydgrp
        FROM mapunit mu JOIN component c ON c.mukey = mu.mukey
        WHERE mu.mukey IN (SELECT * FROM SDA_Get_Mukey_from_intersection_with_WktWgs84('point({lon} {lat})'))
        ORDER BY c.comppct_r DESC"""
    rows = await _query(comp_sql)
    if len(rows) < 2:
        return None
    cols, vals = rows[0], rows[1]
    comp = dict(zip(cols, vals))

    hz_sql = f"""
        SELECT hzdept_r, hzdepb_r, sandtotal_r, silttotal_r, claytotal_r, ph1to1h2o_r, om_r,
               dbthirdbar_r, cec7_r, awc_r
        FROM chorizon WHERE cokey = '{comp["cokey"]}' AND hzdept_r < 30 ORDER BY hzdept_r"""
    hz_rows = await _query(hz_sql)

    # depth-weighted 0-30 cm means
    agg: dict[str, float] = {}
    weight_tot = 0.0
    if len(hz_rows) > 1:
        hcols = hz_rows[0]
        for r in hz_rows[1:]:
            h = dict(zip(hcols, r))
            top = float(h["hzdept_r"] or 0)
            bot = min(float(h["hzdepb_r"] or 30), 30)
            w = max(bot - top, 0)
            if w == 0:
                continue
            weight_tot += w
            for k in ("sandtotal_r", "silttotal_r", "claytotal_r", "ph1to1h2o_r", "om_r",
                      "dbthirdbar_r", "cec7_r", "awc_r"):
                if h.get(k) not in (None, ""):
                    agg[k] = agg.get(k, 0.0) + float(h[k]) * w
    mean = {k: (v / weight_tot if weight_tot else None) for k, v in agg.items()}

    def g(k, nd=1):
        v = mean.get(k)
        return None if v is None else round(v, nd)

    awc_frac = mean.get("awc_r")  # cm water / cm soil
    return SoilProfile(
        source="USDA SSURGO via Soil Data Access (dominant component at centroid, 0-30 cm)",
        name=comp.get("muname"),
        texture_class=usda_texture(mean.get("sandtotal_r"), mean.get("silttotal_r"), mean.get("claytotal_r")),
        sand_pct=g("sandtotal_r"), silt_pct=g("silttotal_r"), clay_pct=g("claytotal_r"),
        ph=g("ph1to1h2o_r"),
        organic_matter_pct=g("om_r", 2),
        bulk_density_g_cm3=g("dbthirdbar_r", 2),
        cec_cmol_kg=g("cec7_r"),
        awc_mm_per_m=None if awc_frac is None else round(awc_frac * 1000, 0),
        drainage_class=comp.get("drainagecl"),
        slope_pct=None if comp.get("slope_r") in (None, "") else float(comp["slope_r"]),
        taxonomic_order=comp.get("taxorder"),
        notes=[f"dominant component '{comp.get('compname')}' = {comp.get('comppct_r')}% of map unit",
               "sampled at the field centroid only; large fields can span several map units"],
    )
