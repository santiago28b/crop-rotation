"""
Climate for any field: fetch NASA POWER for the field's location, summarize it,
and cache it so nearby fields (same NASA grid cell) don't re-download.

NASA POWER's grid is about 0.5 degrees (~50 km), so we round the location to
the nearest 0.5 degree for the cache key. Most Treasure Valley fields share
1-2 cells, so after the first request it's instant.
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from fetch_power import fetch_power          # noqa: E402
from summarize_power import yearly_summary   # noqa: E402

CACHE_DIR = ROOT / "data" / "cache"
YEAR_TYPES = ["dry", "normal", "wet"]
MM_PER_IN = 25.4
START_YEAR, END_YEAR = 2001, 2025
GRID_DEG = 0.5


def grid_cell(lat: float, lon: float) -> tuple[float, float]:
    snap = lambda v: round(round(v / GRID_DEG) * GRID_DEG, 2)
    return snap(lat), snap(lon)


def climate_from_yearly_csv(path: Path, label: str) -> dict | None:
    """Turn a yearly summary CSV (from summarize_power) into what the engine needs."""
    with open(path, newline="") as f:
        rows = [r for r in csv.DictReader(f) if r.get("year_type") in YEAR_TYPES]
    if not rows:
        return None

    def avg(items, col):
        vals = [float(r[col]) for r in items if r.get(col) not in ("", None)]
        return sum(vals) / len(vals) if vals else 0.0

    by_type, odds = {}, {}
    for t in YEAR_TYPES:
        group = [r for r in rows if r["year_type"] == t]
        odds[t] = len(group) / len(rows)
        by_type[t] = {
            "season_rain_in": round(avg(group, "precip_season_mm") / MM_PER_IN, 2),
            "hot_days": round(avg(group, "hot_days"), 1),
        }
    return {
        "source": f"NASA POWER {START_YEAR}-{END_YEAR}, {label}",
        "frost_free_days": round(avg(rows, "frost_free_days")),
        "odds": odds,
        "by_year_type": by_type,
    }


def get_climate(lat: float, lon: float, cache_dir: Path | None = None) -> dict:
    """Climate for this field's grid cell. Downloads once, then reads from cache.

    Raises on network/API errors so the caller can decide what to fall back to.
    """
    cache_dir = cache_dir or CACHE_DIR
    glat, glon = grid_cell(lat, lon)
    label = f"grid cell {glat}, {glon}"
    cached = cache_dir / f"power_{glat}_{glon}_{START_YEAR}_{END_YEAR}_yearly.csv"

    if not cached.exists():
        daily = fetch_power(glat, glon, START_YEAR, END_YEAR)
        cache_dir.mkdir(parents=True, exist_ok=True)
        yearly_summary(daily).to_csv(cached)

    climate = climate_from_yearly_csv(cached, label)
    if climate is None:
        raise ValueError(f"NASA POWER summary for {label} has no usable years")
    climate["grid_cell"] = {"lat": glat, "lon": glon}
    return climate
