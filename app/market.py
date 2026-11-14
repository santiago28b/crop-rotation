"""
Location-aware yields and prices.

1. locate(lat, lon): which US state / county is the field in (FCC Census API, no key).
2. state_market(state): 5-year average yield and price for each crop in that
   state, from USDA NASS QuickStats (free API key: https://quickstats.nass.usda.gov/api).
3. apply_market(crops, state): overwrite the crop table's yield and price with the
   state's numbers where USDA has them, and record where each number came from.

Costs are NOT location-aware yet: they stay as in data/crops.csv.

Set the key with:  export NASS_API_KEY=your_key
Check it works:    python scripts/check_market.py ID
"""

import json
import os
from pathlib import Path

import requests

import app.config  # noqa: F401  (loads .env so NASS_API_KEY can live there)

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
FCC_URL = "https://geo.fcc.gov/api/census/block/find"
NASS_URL = "https://quickstats.nass.usda.gov/api/api_GET/"
FIRST_YEAR = 2020   # average everything USDA has from this year on

# The area the crop table's costs and water numbers were built for (southwest Idaho)
HOME_REGION = {"state": "ID", "lat": (42.9, 44.5), "lon": (-117.3, -115.5),
               "name": "southwest Idaho (Treasure Valley)"}

# crop id -> how to find it in QuickStats.
# "items" are USDA's exact data item names (short_desc); the first one found wins.
# "scale" converts USDA's unit to the crop table's unit (dry beans: lb -> cwt).
NASS_ITEMS = {
    "alfalfa": {
        "commodity": "HAY",
        "yield": {"items": ["HAY, ALFALFA - YIELD, MEASURED IN TONS / ACRE"]},
        "price": {"items": ["HAY, ALFALFA - PRICE RECEIVED, MEASURED IN $ / TON"]},
    },
    "corn_silage": {
        "commodity": "CORN",
        "yield": {"items": ["CORN, SILAGE - YIELD, MEASURED IN TONS / ACRE"]},
        "price": None,   # USDA has no price received for silage
    },
    "winter_wheat": {
        "commodity": "WHEAT",
        "yield": {"items": ["WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE"]},
        "price": {"items": ["WHEAT, WINTER - PRICE RECEIVED, MEASURED IN $ / BU",
                            "WHEAT - PRICE RECEIVED, MEASURED IN $ / BU"]},
    },
    "spring_barley": {
        "commodity": "BARLEY",
        "yield": {"items": ["BARLEY - YIELD, MEASURED IN BU / ACRE"]},
        "price": {"items": ["BARLEY - PRICE RECEIVED, MEASURED IN $ / BU"]},
    },
    "sugar_beets": {
        "commodity": "SUGARBEETS",
        "yield": {"items": ["SUGARBEETS - YIELD, MEASURED IN TONS / ACRE"]},
        "price": {"items": ["SUGARBEETS - PRICE RECEIVED, MEASURED IN $ / TON"]},
    },
    "onions": {
        "commodity": "ONIONS",
        "yield": {"items": ["ONIONS, DRY - YIELD, MEASURED IN CWT / ACRE",
                            "ONIONS, DRY, SUMMER, STORAGE - YIELD, MEASURED IN CWT / ACRE"]},
        "price": {"items": ["ONIONS, DRY - PRICE RECEIVED, MEASURED IN $ / CWT",
                            "ONIONS, DRY, SUMMER, STORAGE - PRICE RECEIVED, MEASURED IN $ / CWT"]},
    },
    "dry_beans": {
        "commodity": "BEANS",
        "yield": {"items": ["BEANS, DRY EDIBLE, (EXCL CHICKPEAS) - YIELD, MEASURED IN LB / ACRE",
                            "BEANS, DRY EDIBLE - YIELD, MEASURED IN LB / ACRE",
                            "BEANS, DRY EDIBLE, INCL CHICKPEAS - YIELD, MEASURED IN LB / ACRE"],
                  "scale": 0.01},
        "price": {"items": ["BEANS, DRY EDIBLE, (EXCL CHICKPEAS) - PRICE RECEIVED, MEASURED IN $ / CWT",
                            "BEANS, DRY EDIBLE - PRICE RECEIVED, MEASURED IN $ / CWT",
                            "BEANS, DRY EDIBLE, INCL CHICKPEAS - PRICE RECEIVED, MEASURED IN $ / CWT"]},
    },
    "potatoes": {
        "commodity": "POTATOES",
        "yield": {"items": ["POTATOES - YIELD, MEASURED IN CWT / ACRE"]},
        "price": {"items": ["POTATOES - PRICE RECEIVED, MEASURED IN $ / CWT"]},
    },
    "mint": {
        "commodity": "MINT",
        "yield": {"items": ["MINT, PEPPERMINT, OIL - YIELD, MEASURED IN LB / ACRE"]},
        "price": {"items": ["MINT, PEPPERMINT, OIL - PRICE RECEIVED, MEASURED IN $ / LB"]},
    },
}
STAT_NAME = {"yield": "YIELD", "price": "PRICE RECEIVED"}


# ------------------------------------------------------------------- location

def in_home_region(lat: float, lon: float) -> bool:
    (lat0, lat1), (lon0, lon1) = HOME_REGION["lat"], HOME_REGION["lon"]
    return lat0 <= lat <= lat1 and lon0 <= lon <= lon1


def locate(lat: float, lon: float) -> dict:
    """State and county for a point in the US. Raises if the lookup fails."""
    resp = requests.get(FCC_URL, params={"latitude": lat, "longitude": lon, "format": "json"},
                        timeout=20)
    resp.raise_for_status()
    data = resp.json()
    state = (data.get("State") or {}).get("code")
    if not state:
        raise ValueError("location is outside the US (no state found)")
    return {
        "state": state.upper(),
        "state_name": data["State"].get("name"),
        "county": (data.get("County") or {}).get("name"),
        "county_fips": (data.get("County") or {}).get("FIPS"),
    }


# ----------------------------------------------------------------- QuickStats

def _to_number(value: str) -> float | None:
    try:
        return float(str(value).replace(",", "").strip())
    except ValueError:      # "(D)" = withheld, "(NA)" = not available
        return None


def query_nass(commodity: str, stat: str, state: str, api_key: str) -> list[dict]:
    """All state-level yearly records for one commodity and statistic."""
    params = {
        "key": api_key, "format": "JSON", "source_desc": "SURVEY",
        "commodity_desc": commodity, "statisticcat_desc": STAT_NAME[stat],
        "agg_level_desc": "STATE", "state_alpha": state, "year__GE": FIRST_YEAR,
    }
    resp = requests.get(NASS_URL, params=params, timeout=60)
    if resp.status_code == 400:      # QuickStats answers 400 when nothing matches
        return []
    resp.raise_for_status()
    return [r for r in resp.json().get("data", [])
            if r.get("reference_period_desc") in ("YEAR", "MARKETING YEAR")
            and r.get("domain_desc", "TOTAL") == "TOTAL"]


def pick_average(records: list[dict], spec: dict) -> dict | None:
    """Average the first data item in spec['items'] that has numbers."""
    for item in spec["items"]:
        by_year = {}
        for r in records:
            value = _to_number(r.get("Value"))
            if r.get("short_desc") == item and value is not None:
                by_year[int(r["year"])] = value * spec.get("scale", 1)
        if by_year:
            years = sorted(by_year)
            return {"value": round(sum(by_year.values()) / len(by_year), 2),
                    "years": f"{years[0]}-{years[-1]}", "item": item}
    return None


def state_market(state: str, api_key: str | None = None, cache_dir: Path | None = None) -> dict:
    """{crop: {"yield": {...} | None, "price": {...} | None}} for a state (cached on disk)."""
    api_key = api_key or os.environ.get("NASS_API_KEY")
    if not api_key:
        raise RuntimeError("NASS_API_KEY is not set")
    cache_dir = cache_dir or CACHE_DIR
    cached = cache_dir / f"market_{state}_{FIRST_YEAR}.json"
    if cached.exists():
        return json.loads(cached.read_text())

    market = {}
    for crop, spec in NASS_ITEMS.items():
        market[crop] = {}
        for stat in ("yield", "price"):
            if spec[stat] is None:
                market[crop][stat] = None
                continue
            records = query_nass(spec["commodity"], stat, state, api_key)
            market[crop][stat] = pick_average(records, spec[stat])

    cache_dir.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(market, indent=2))
    return market


def apply_market(crops: dict, market: dict, state: str) -> dict:
    """Copy of the crop table with the state's USDA yield and price where available."""
    table_note = "crop table (data/crops.csv)"
    out = {}
    for name, crop in crops.items():
        crop = dict(crop)
        found = market.get(name, {})
        crop["data_notes"] = {"yield": table_note, "price": table_note, "cost": table_note}
        for stat, column in (("yield", "yield_per_acre"), ("price", "price_per_unit")):
            hit = found.get(stat)
            if hit:
                crop[column] = hit["value"]
                crop["data_notes"][stat] = f"USDA NASS {state} average {hit['years']}"
        out[name] = crop
    return out
