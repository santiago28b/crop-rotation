"""
Measured water use of a field from OpenET (NASA/DRI satellite evapotranspiration).

ET = water that left the field through the plants + soil. For an irrigated field
this is basically "how much water the crop actually used" — a measurement, not a
table value. The engine uses it as the water need of the farmer's CURRENT crop.

How it works:
  - One request: monthly Ensemble ET (average of 6 satellite models) at the
    field's center for the last 3 full calendar years, in mm.
  - Sum April-October of each year (the Treasure Valley irrigation season),
    average the years, convert to inches.
  - Cached in data/cache/ (satellite history doesn't change).

Needs OPENET_API_KEY in .env (free: https://account.etdata.org).
Docs: https://openet.gitbook.io/docs/reference/api-reference/raster
"""

import json
import os
from datetime import date
from pathlib import Path

import requests

import app.config  # noqa: F401  (loads .env so OPENET_API_KEY can live there)

ROOT = Path(__file__).resolve().parent.parent
from app.config import CACHE_DIR  # noqa: E402  (one cache location for every module)
API_URL = "https://openet-api.org/raster/timeseries/point"
SEASON_MONTHS = range(4, 11)      # April-October: the irrigation season here
YEARS_BACK = 3
MM_PER_IN = 25.4


def fetch_monthly_et(lat: float, lon: float, start: str, end: str, api_key: str) -> dict[str, float]:
    """Monthly actual ET in mm at a point: {"YYYY-MM-01": mm}."""
    body = {
        "date_range": [start, end],
        "interval": "monthly",
        "geometry": [lon, lat],          # OpenET wants [longitude, latitude]
        "model": "Ensemble",
        "variable": "ET",
        "reference_et": "gridMET",
        "units": "mm",
        "file_format": "JSON",
    }
    resp = requests.post(API_URL, json=body, headers={"Authorization": api_key}, timeout=120)
    resp.raise_for_status()
    out = {}
    for row in resp.json():              # rows look like {"time": "2023-04-01", "et": 112.3}
        values = list(row.values())
        out[str(values[0])[:10]] = float(values[1])
    return out


def field_water_use_in(lat: float, lon: float, today: date | None = None,
                       fetch=fetch_monthly_et, cache_dir: Path | None = None) -> dict:
    """Mean growing-season water use of this field in inches, over recent years."""
    api_key = os.environ.get("OPENET_API_KEY")
    if not api_key:
        raise RuntimeError("OPENET_API_KEY is not set")
    today = today or date.today()
    last = today.year - 1                # last full calendar year
    first = last - YEARS_BACK + 1
    cache_dir = cache_dir or CACHE_DIR

    cached = cache_dir / f"openet_{round(lat, 3)}_{round(lon, 3)}_{first}_{last}.json"
    if cached.exists():
        monthly = json.loads(cached.read_text())
    else:
        monthly = fetch(lat, lon, f"{first}-01-01", f"{last}-12-31", api_key)
        cache_dir.mkdir(parents=True, exist_ok=True)
        cached.write_text(json.dumps(monthly))

    season_mm: dict[int, float] = {}
    for day, mm in monthly.items():
        year, month = int(day[:4]), int(day[5:7])
        if month in SEASON_MONTHS:
            season_mm[year] = season_mm.get(year, 0.0) + mm
    if not season_mm:
        raise RuntimeError("OpenET returned no growing-season data")

    mean_in = sum(season_mm.values()) / len(season_mm) / MM_PER_IN
    years = sorted(season_mm)
    return {
        "season_et_in": round(mean_in, 1),
        "by_year_in": {y: round(season_mm[y] / MM_PER_IN, 1) for y in years},
        "years": f"{years[0]}-{years[-1]}",
        "season": "Apr-Oct",
        "source": f"OpenET Ensemble (satellite-measured ET at the field, Apr-Oct mean {years[0]}-{years[-1]})",
    }
