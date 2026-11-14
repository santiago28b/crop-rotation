"""
NASA POWER daily point data (global, no key).
Docs: https://power.larc.nasa.gov/docs/services/api/temporal/daily/

Returns a daily DataFrame (index = date) with the "AG" community parameters plus the
grid-cell elevation. Cached on disk; ~25 years is a ~2 MB JSON and takes 1-3 s live.
"""

from __future__ import annotations

import httpx
import pandas as pd

from app import cache
from app.config import POWER_END_YEAR, POWER_START_YEAR

API_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

PARAMETERS = {
    "T2M": "avg air temp (C)",
    "T2M_MAX": "max air temp (C)",
    "T2M_MIN": "min air temp (C)",
    "PRECTOTCORR": "precipitation (mm/day)",
    "RH2M": "relative humidity (%)",
    "WS2M": "wind speed at 2m (m/s)",
    "ALLSKY_SFC_SW_DWN": "solar radiation (MJ/m^2/day)",
    "GWETTOP": "surface soil wetness (0-1)",
    "GWETROOT": "root-zone soil wetness (0-1)",
}
FILL_VALUE = -999


async def fetch_daily(lat: float, lon: float,
                      start_year: int = POWER_START_YEAR,
                      end_year: int = POWER_END_YEAR) -> tuple[pd.DataFrame, float | None]:
    """Daily weather for the POWER grid cell containing (lat, lon). Returns (df, elevation_m)."""
    # POWER cells are 0.5 x 0.625 degrees; rounding to 0.1 keeps the cache hit rate high
    key = {"lat": round(lat, 1), "lon": round(lon, 1), "start": start_year, "end": end_year,
           "params": sorted(PARAMETERS)}
    data = cache.get("power", key)
    if data is None:
        params = {
            "parameters": ",".join(PARAMETERS),
            "community": "AG",
            "latitude": lat,
            "longitude": lon,
            "start": f"{start_year}0101",
            "end": f"{end_year}1231",
            "format": "JSON",
        }
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.get(API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        cache.put("power", key, data)

    raw = data["properties"]["parameter"]
    df = pd.DataFrame(raw)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "date"
    df = df.astype(float).replace(FILL_VALUE, float("nan"))

    elevation = None
    try:
        elevation = float(data["geometry"]["coordinates"][2])
    except (KeyError, IndexError, TypeError, ValueError):
        pass
    return df, elevation
