"""
ISRIC SoilGrids v2 (global, 250 m, no key). Docs: https://rest.isric.org/soilgrids/v2.0/docs

We take the 0-30 cm depth-weighted mean of texture, pH, organic carbon, bulk density and
CEC, then derive a USDA texture class and plant-available water (Saxton & Rawls 2006
pedotransfer) because SoilGrids has no AWC layer.
"""

from __future__ import annotations

import httpx

from app import cache
from app.schemas import SoilProfile

API_URL = "https://rest.isric.org/soilgrids/v2.0/properties/query"

# property -> (SoilGrids unit divisor -> conventional unit)
PROPS = {
    "clay": 10.0,   # g/kg   -> %
    "sand": 10.0,   # g/kg   -> %
    "silt": 10.0,   # g/kg   -> %
    "phh2o": 10.0,  # pH*10  -> pH
    "soc": 100.0,   # dg/kg  -> % (g/kg = dg/kg/10, % = g/kg/10)
    "bdod": 100.0,  # cg/cm3 -> g/cm3
    "cec": 10.0,    # mmol(c)/kg -> cmol(c)/kg
}
DEPTHS = {"0-5cm": 5, "5-15cm": 10, "15-30cm": 15}  # label -> thickness (cm) used as weight


async def _query(lat: float, lon: float) -> dict[str, float | None]:
    key = {"lat": round(lat, 4), "lon": round(lon, 4)}
    data = cache.get("soilgrids", key)
    if data is None:
        params = [("lon", lon), ("lat", lat), ("value", "mean")]
        params += [("property", p) for p in PROPS]
        params += [("depth", d) for d in DEPTHS]
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        cache.put("soilgrids", key, data)

    values: dict[str, float | None] = {}
    for layer in data.get("properties", {}).get("layers", []):
        name = layer["name"]
        total, weight = 0.0, 0.0
        for d in layer.get("depths", []):
            v = d.get("values", {}).get("mean")
            w = DEPTHS.get(d.get("label"), 0)
            if v is not None and w:
                total += v * w
                weight += w
        values[name] = (total / weight) / PROPS[name] if weight else None
    return values


# SoilGrids has no-data pixels (buildings, water, rock); try the centroid, then ~280 m to each side
_OFFSETS = [(0, 0), (0.0025, 0), (-0.0025, 0), (0, 0.0025), (0, -0.0025)]


async def fetch_soil(lat: float, lon: float) -> SoilProfile:
    notes = ["SoilGrids is a 250 m global model, not a field survey; expect local variation.",
             "No drainage class or slope outside the US yet (planned: NASADEM slope)."]
    values: dict[str, float | None] = {}
    for dlat, dlon in _OFFSETS:
        values = await _query(lat + dlat, lon + dlon)
        if values.get("clay") is not None:
            if (dlat, dlon) != (0, 0):
                notes.append("no SoilGrids data at the field centre; used the nearest pixel with data (~280 m away)")
            break

    sand, silt, clay = values.get("sand"), values.get("silt"), values.get("clay")
    om_pct = values["soc"] * 1.724 if values.get("soc") is not None else None  # Van Bemmelen factor
    if sand is None or clay is None:
        notes.append("SoilGrids has no data within ~300 m of this field (water body / urban / rock?)")

    return SoilProfile(
        source="ISRIC SoilGrids v2.0 (0-30 cm mean)",
        texture_class=usda_texture(sand, silt, clay),
        sand_pct=_r(sand), silt_pct=_r(silt), clay_pct=_r(clay),
        ph=_r(values.get("phh2o")),
        organic_matter_pct=_r(om_pct, 2),
        bulk_density_g_cm3=_r(values.get("bdod"), 2),
        cec_cmol_kg=_r(values.get("cec")),
        awc_mm_per_m=_r(awc_saxton_rawls(sand, clay, om_pct), 0),
        drainage_class=None,
        slope_pct=None,
        notes=notes,
    )


def _r(v, nd=1):
    return None if v is None else round(float(v), nd)


def usda_texture(sand: float | None, silt: float | None, clay: float | None) -> str | None:
    """USDA soil texture triangle (percent sand/silt/clay)."""
    if sand is None or silt is None or clay is None:
        return None
    s, si, c = sand, silt, clay
    if si + 1.5 * c < 15:
        return "sand"
    if si + 1.5 * c >= 15 and si + 2 * c < 30:
        return "loamy sand"
    if (7 <= c < 20 and s > 52 and si + 2 * c >= 30) or (c < 7 and si < 50 and si + 2 * c >= 30):
        return "sandy loam"
    if 7 <= c < 27 and 28 <= si < 50 and s <= 52:
        return "loam"
    if (si >= 50 and 12 <= c < 27) or (50 <= si < 80 and c < 12):
        return "silt loam"
    if si >= 80 and c < 12:
        return "silt"
    if 20 <= c < 35 and si < 28 and s > 45:
        return "sandy clay loam"
    if 27 <= c < 40 and 20 < s <= 45:
        return "clay loam"
    if 27 <= c < 40 and s <= 20:
        return "silty clay loam"
    if c >= 35 and s > 45:
        return "sandy clay"
    if c >= 40 and si >= 40:
        return "silty clay"
    if c >= 40 and s <= 45 and si < 40:
        return "clay"
    return "loam"


def awc_saxton_rawls(sand_pct: float | None, clay_pct: float | None, om_pct: float | None) -> float | None:
    """
    Plant-available water (field capacity - wilting point), mm per metre of soil.
    Saxton & Rawls (2006) equations 1-3. S, C as fractions; OM in % by weight.
    """
    if sand_pct is None or clay_pct is None:
        return None
    S, C = sand_pct / 100, clay_pct / 100
    OM = om_pct if om_pct is not None else 2.0

    t1500 = -0.024 * S + 0.487 * C + 0.006 * OM + 0.005 * S * OM - 0.013 * C * OM + 0.068 * S * C + 0.031
    wp = t1500 + (0.14 * t1500 - 0.02)

    t33 = -0.251 * S + 0.195 * C + 0.011 * OM + 0.006 * S * OM - 0.027 * C * OM + 0.452 * S * C + 0.299
    fc = t33 + (1.283 * t33 ** 2 - 0.374 * t33 - 0.015)

    awc = max(fc - wp, 0.02)          # m3/m3
    return awc * 1000                  # mm per m
