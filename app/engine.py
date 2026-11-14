"""
Crop recommendation engine.

Given a field, the farmer's current crop and their water supply, score each
candidate crop on expected profit adjusted for water risk, and return a report.

Steps (see the design doc):
  1. Filter crops that don't fit the season or the rotation rules
  2. Odds of a dry / normal / wet year (history, shifted by snowpack outlook)
  3. Water available vs. water the crop needs, per year type
  4. Yield cut when water is short (FAO-33) and for extra hot days
  5. Profit = yield x price - cost, per year type
  6. Score = expected profit - penalty for a bad dry year
  7. Pick at least 3 options (current, best, safest, best for soil)

Try it:  python -m app.engine
"""

import csv
import json
from pathlib import Path

from app.climate import get_climate
from app.geo import field_center_and_acres
from app.snowpack import snowpack_status
from app.market import HOME_REGION, apply_market, in_home_region, locate, state_market
from app.openet import field_water_use_in

ROOT = Path(__file__).resolve().parent.parent
YEAR_TYPES = ["dry", "normal", "wet"]
MM_PER_IN = 25.4

# ---- Assumptions. PLACEHOLDERS until we confirm with the farmer / real data ----
ASSUMPTIONS = {
    "full_allotment_in": 42.0,        # irrigation water delivered per acre in a full-supply year
    "irrigation_efficiency": 0.75,    # share of delivered water the crop actually gets
    "supply_level": {"full": 1.0, "limited": 0.75, "short": 0.5},
    "year_delivery": {"dry": 0.75, "normal": 1.0, "wet": 1.0},   # canal cuts in dry years
    "year_demand": {"dry": 1.08, "normal": 1.0, "wet": 0.95},    # crops need more in hot dry years
    "effective_rain": 0.7,            # share of growing-season rain that reaches the roots
    "hot_day_baseline": 10,           # hot days per season crops handle without loss
    "risk_weight": 0.5,               # how much a bad dry year counts against a crop
    "n_credit_per_acre": {"alfalfa": 60, "dry_beans": 25},  # fertilizer saved on the next crop
}

# Used only if the NASA POWER summary hasn't been generated yet
DEFAULT_CLIMATE = {
    "source": "placeholder (run scripts/fetch_power.py and scripts/summarize_power.py)",
    "frost_free_days": 155,
    "odds": {"dry": 1 / 3, "normal": 1 / 3, "wet": 1 / 3},
    "by_year_type": {
        "dry": {"season_rain_in": 1.5, "hot_days": 22},
        "normal": {"season_rain_in": 2.5, "hot_days": 16},
        "wet": {"season_rain_in": 4.0, "hot_days": 11},
    },
}

SNOWPACK_SHIFT = {
    "low": {"dry": 0.25, "normal": -0.10, "wet": -0.15},
    "normal": {"dry": 0.0, "normal": 0.0, "wet": 0.0},
    "high": {"dry": -0.15, "normal": -0.10, "wet": 0.25},
}


# ---------------------------------------------------------------- loading data

def load_crops(path: Path | None = None) -> dict:
    path = path or ROOT / "data" / "crops.csv"
    crops = {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            for col in ("water_need_in", "ky", "yield_per_acre", "price_per_unit", "cost_per_acre",
                        "frost_free_days_needed", "heat_sensitivity", "soil_score"):
                row[col] = float(row[col])
            row["fixes_nitrogen"] = row["fixes_nitrogen"] == "1"
            row["no_repeat"] = row["no_repeat"] == "1"
            row["avoid_after"] = [c for c in row["avoid_after"].split(";") if c]
            crops[row["crop"]] = row
    return crops


def load_climate(lat: float, lon: float) -> dict:
    """NASA POWER climate for the field's location (cached by grid cell).

    If NASA can't be reached, fall back to placeholder numbers and say so in
    the report's data sources, so the app still works during a demo.
    """
    try:
        return get_climate(lat, lon)
    except Exception as e:  # network down, API error, bad data
        fallback = dict(DEFAULT_CLIMATE)
        fallback["source"] = f"placeholder climate (NASA POWER unavailable: {type(e).__name__})"
        return fallback


def resolve_snowpack(choice: str, lat: float, lon: float) -> dict:
    """Snowpack level for the year odds: the user's choice, or SNOTEL when "auto"."""
    if choice != "auto":
        return {"level": choice, "source": f"Snowpack: set by user ({choice})",
                "note": "Snowpack chosen by hand."}
    if not in_home_region(lat, lon):
        return {"level": "normal", "source": "Snowpack: not used (outside the Boise River area)",
                "note": "Live snowpack is only wired up for the Boise River basin."}
    try:
        status = snowpack_status()
    except Exception as e:
        return {"level": "normal", "source": f"Snowpack: SNOTEL unavailable ({type(e).__name__})",
                "note": "Could not read SNOTEL, so a normal snow year is assumed."}
    status["source"] = (f"Snowpack: {status['source']}, as of {status['as_of']}, "
                        f"{status['basin_pct_of_median']}% of median")
    return status


def resolve_field_water(lat: float, lon: float) -> dict:
    """Measured water use of this field from OpenET, or a note saying why not."""
    try:
        return field_water_use_in(lat, lon)
    except Exception as e:
        return {"season_et_in": None,
                "source": f"OpenET: not used ({type(e).__name__}: {e})",
                "note": "No measured field water use; crop table water needs used."}


def apply_field_water(crops: dict, current_crop: str, field_water: dict) -> dict:
    """Use the field's measured water use as the CURRENT crop's water need.

    Only the current crop: OpenET measured what actually grew on this field, so
    it says nothing about crops the field didn't grow. If the measurement is
    under half the table's need, the field probably wasn't growing this crop
    (bare ground measures like desert) — keep the table value and say so.
    """
    measured = field_water["season_et_in"]
    table_need = crops[current_crop]["water_need_in"]
    if measured < 0.5 * table_need:
        field_water["applied_to_current_crop"] = False
        field_water["note"] = (
            f"OpenET measured only {measured} in/season on this field, under half of what "
            f"{crops[current_crop]['label'].lower()} typically needs ({table_need} in) — the field "
            "probably wasn't growing it (or wasn't fully irrigated). Crop table value kept.")
        return crops
    row = dict(crops[current_crop])
    row["water_need_in"] = measured
    notes = dict(row.get("data_notes") or {})
    notes["water_need"] = f"OpenET measured on this field, Apr-Oct mean {field_water['years']}"
    row["data_notes"] = notes
    field_water["applied_to_current_crop"] = True
    field_water["note"] = (
        f"This field actually used about {measured} in of water per season "
        f"({field_water['years']}). Used as the water need for {row['label'].lower()}; "
        "other crops use table values.")
    return {**crops, current_crop: row}


def find_location(lat: float, lon: float) -> dict | None:
    """State and county of the field, or None if the lookup can't be done."""
    try:
        return locate(lat, lon)
    except Exception:
        return None


def with_local_market(crops: dict, location: dict | None) -> tuple[dict, str]:
    """Swap in the state's USDA yields and prices. On any problem keep the crop table."""
    table = "Yields and prices: crop table (data/crops.csv)"
    if not location:
        return crops, table + "; field's state could not be looked up"
    try:
        market = state_market(location["state"])
    except Exception as e:
        return crops, table + f"; USDA NASS not used ({type(e).__name__}: {e})"
    found = sum(1 for c in market.values() for v in c.values() if v)
    return (apply_market(crops, market, location["state"]),
            f"Yields and prices: USDA NASS QuickStats for {location['state']} "
            f"({found} values found); crop table for the rest")


def region_warning(lat: float, lon: float, location: dict | None) -> str | None:
    """Costs and water numbers are only valid in the home region. Say so elsewhere."""
    if in_home_region(lat, lon):
        return None
    place = f"{location['county']}, {location['state']}" if location else "this location"
    return (f"This tool is tuned for {HOME_REGION['name']}. For {place}, climate is local, "
            "but the crop list, costs per acre, crop water needs and irrigation assumptions "
            "are southwest Idaho numbers. Treat the dollar figures as rough.")


# ------------------------------------------------------------------- the math

def year_odds(climate: dict, snowpack: str = "normal") -> dict:
    shift = SNOWPACK_SHIFT[snowpack]
    odds = {t: max(0.02, climate["odds"][t] + shift[t]) for t in YEAR_TYPES}
    total = sum(odds.values())
    return {t: odds[t] / total for t in YEAR_TYPES}


def water_available_in(supply: str, year_type: str, climate: dict, a=ASSUMPTIONS) -> float:
    irrigation = (a["full_allotment_in"] * a["supply_level"][supply]
                  * a["year_delivery"][year_type] * a["irrigation_efficiency"])
    rain = climate["by_year_type"][year_type]["season_rain_in"] * a["effective_rain"]
    return irrigation + rain


def crop_outcome(crop: dict, supply: str, year_type: str, climate: dict,
                 n_credit: float = 0.0, a=ASSUMPTIONS) -> dict:
    need = crop["water_need_in"] * a["year_demand"][year_type]
    available = water_available_in(supply, year_type, climate, a)
    water_ratio = min(1.0, available / need)

    # FAO-33: relative yield loss = Ky x relative water shortfall
    water_factor = max(0.0, 1 - crop["ky"] * (1 - water_ratio))
    extra_hot = max(0.0, climate["by_year_type"][year_type]["hot_days"] - a["hot_day_baseline"])
    heat_factor = max(0.0, 1 - crop["heat_sensitivity"] * extra_hot)

    yield_per_acre = crop["yield_per_acre"] * water_factor * heat_factor
    profit = yield_per_acre * crop["price_per_unit"] - (crop["cost_per_acre"] - n_credit)
    return {
        "water_needed_in": round(need, 1),
        "water_available_in": round(available, 1),
        "water_met_pct": round(water_ratio * 100),
        "yield_per_acre": round(yield_per_acre, 1),
        "profit_per_acre": round(profit),
    }


def score_crop(crop: dict, supply: str, odds: dict, climate: dict, previous_crop: str | None,
               a=ASSUMPTIONS) -> dict:
    n_credit = 0.0 if crop["fixes_nitrogen"] else a["n_credit_per_acre"].get(previous_crop, 0.0)
    by_year = {t: crop_outcome(crop, supply, t, climate, n_credit, a) for t in YEAR_TYPES}
    expected = sum(odds[t] * by_year[t]["profit_per_acre"] for t in YEAR_TYPES)
    dry = by_year["dry"]["profit_per_acre"]
    score = expected - a["risk_weight"] * max(0.0, expected - dry)
    return {
        "crop": crop["crop"],
        "label": crop["label"],
        "unit": crop["unit"],
        "score": round(score),
        "expected_profit_per_acre": round(expected),
        "dry_year_profit_per_acre": dry,
        "by_year_type": by_year,
        "soil_score": crop["soil_score"],
        "soil_note": crop["soil_note"],
        "nitrogen_credit_per_acre": n_credit,
    }


def check_fit(crop: dict, climate: dict, previous_crop: str | None) -> list[str]:
    """Reasons this crop should not be planted here next season (empty = fine)."""
    problems = []
    if crop["frost_free_days_needed"] > climate["frost_free_days"]:
        problems.append(f"needs {crop['frost_free_days_needed']:.0f} frost-free days; "
                        f"this field averages {climate['frost_free_days']}")
    if previous_crop in crop["avoid_after"]:
        problems.append(f"should not follow {previous_crop.replace('_', ' ')} (shared disease risk)")
    if crop["no_repeat"] and previous_crop == crop["crop"]:
        problems.append("should not be planted two years in a row (disease and pest build-up)")
    return problems


# ----------------------------------------------------------------- the report

def _why(option: dict, tag: str, supply: str) -> str:
    dry = option["by_year_type"]["dry"]
    parts = {
        "current": "This is what you grow now. It is the baseline the other options are compared with.",
        "best_overall": "Best balance of profit and water risk for this field.",
        "safest_dry_year": "Holds up best if next season is dry.",
        "best_for_soil": "Does the most for soil health of the crops that fit here.",
        "alternative": "Another option that scores well here.",
    }
    text = parts[tag]
    text += (f" In a dry year with {supply} water supply it gets about {dry['water_met_pct']}% "
             f"of the water it needs.")
    if option["nitrogen_credit_per_acre"]:
        text += f" Saves about ${option['nitrogen_credit_per_acre']:.0f}/acre in fertilizer after your current crop."
    return text


def _risks(option: dict, problems: list[str]) -> list[str]:
    risks = list(problems)
    dry = option["by_year_type"]["dry"]
    if dry["water_met_pct"] < 90:
        risks.append(f"Water shortfall in a dry year: only {dry['water_met_pct']}% of need is met.")
    if option["dry_year_profit_per_acre"] < 0:
        risks.append("Loses money in a dry year.")
    risks.append("Prices, yields and costs are regional averages. Check with your own numbers "
                 "and a local agronomist or extension office.")
    return risks


def build_report(field, current_crop: str, water_supply: str = "full",
                 area_crops: list[dict] | None = None, snowpack: str = "auto",
                 crops: dict | None = None, climate: dict | None = None,
                 location: dict | None = None) -> dict:
    use_market = crops is None      # a crop table passed in by hand is used as is
    crops = crops or load_crops()
    if water_supply not in ASSUMPTIONS["supply_level"]:
        raise ValueError("water_supply must be full, limited or short")
    if snowpack != "auto" and snowpack not in SNOWPACK_SHIFT:
        raise ValueError("snowpack must be auto, low, normal or high")
    if current_crop not in crops:
        raise ValueError(f"unknown current_crop '{current_crop}'. Known: {sorted(crops)}")

    lat, lon, acres = field_center_and_acres(field)
    climate = climate or load_climate(lat, lon)
    location = location or find_location(lat, lon)
    market_source = "Yields and prices: crop table (data/crops.csv)"
    field_water = None
    if use_market:      # production path (a hand-passed crop table is used as is)
        crops, market_source = with_local_market(crops, location)
        field_water = resolve_field_water(lat, lon)
        if field_water["season_et_in"] is not None:
            crops = apply_field_water(crops, current_crop, field_water)
    snow = resolve_snowpack(snowpack, lat, lon)
    odds = year_odds(climate, snow["level"])

    # Candidates = crops common in the area (from Ethan) that we have numbers for
    area_names = [c["crop"] for c in (area_crops or [])]
    candidates = [c for c in area_names if c in crops] or list(crops)
    unknown = [c for c in area_names if c not in crops]
    if current_crop not in candidates:
        candidates.append(current_crop)

    scored, excluded = {}, []
    for name in candidates:
        problems = check_fit(crops[name], climate, current_crop)
        result = score_crop(crops[name], water_supply, odds, climate, current_crop)
        result["problems"] = problems
        if problems and name != current_crop:
            excluded.append({"crop": name, "label": crops[name]["label"], "reasons": problems})
        else:
            scored[name] = result

    # The report promises at least 3 options. If the area's crop list is short
    # (say only one crop), top up with crops from the full table that fit here.
    for name in crops:
        if len(scored) >= 3:
            break
        if name in scored or name in {e["crop"] for e in excluded}:
            continue
        if check_fit(crops[name], climate, current_crop):
            continue
        result = score_crop(crops[name], water_supply, odds, climate, current_crop)
        result["problems"] = []
        scored[name] = result

    # Pick the options
    picks: list[tuple[str, str]] = [(current_crop, "current")]
    others = [s for n, s in scored.items() if n != current_crop]
    chosen = {current_crop}

    def pick(tag, key):
        pool = [s for s in others if s["crop"] not in chosen]
        if pool:
            best = max(pool, key=key)
            # If a crop we already picked beats this one on the same measure,
            # the tag would be a false claim ("safest in a dry year" on a crop
            # that loses the most). Call it an alternative instead.
            if key(best) < key(max(others, key=key)):
                tag = "alternative"
            picks.append((best["crop"], tag))
            chosen.add(best["crop"])

    pick("best_overall", lambda s: s["score"])
    pick("safest_dry_year", lambda s: s["dry_year_profit_per_acre"])
    pick("best_for_soil", lambda s: (s["soil_score"], s["score"]))

    options = []
    for name, tag in picks:
        o = scored[name]
        options.append({
            "tag": tag,
            "crop": name,
            "label": o["label"],
            "score": o["score"],
            "expected_profit_per_acre": o["expected_profit_per_acre"],
            "expected_profit_field": round(o["expected_profit_per_acre"] * acres),
            "dry_year_profit_per_acre": o["dry_year_profit_per_acre"],
            "dry_year_profit_field": round(o["dry_year_profit_per_acre"] * acres),
            "by_year_type": o["by_year_type"],
            "soil_score": o["soil_score"],
            "soil_note": o["soil_note"],
            "data_notes": crops[name].get("data_notes"),
            "why": _why(o, tag, water_supply),
            "risks": _risks(o, o["problems"]),
        })
    # Current crop first, then the rest by score
    options = options[:1] + sorted(options[1:], key=lambda o: o["score"], reverse=True)

    return {
        "field": {"lat": lat, "lon": lon, "acres": acres},
        "location": location,
        "region_warning": region_warning(lat, lon, location),
        "inputs": {"current_crop": current_crop, "water_supply": water_supply, "snowpack": snowpack},
        "snowpack": snow,
        "field_water_use": field_water,
        "year_odds": {t: round(odds[t], 2) for t in YEAR_TYPES},
        "climate": climate,
        "options": options,
        "excluded": excluded,
        "unknown_area_crops": unknown,
        "data_sources": [
            climate["source"],
            market_source,
            snow["source"],
            *([field_water["source"]] if field_water else []),
            "Crop table: data/crops.csv ("
            + ", ".join(sorted({c["source"] for c in crops.values()})) + ")",
        ],
        "assumptions": ASSUMPTIONS,
        "disclaimer": "This tool supports decisions. It does not replace your judgment "
                      "or local agricultural experts.",
    }


if __name__ == "__main__":
    # Demo: an ~80 acre field near Nampa, ID
    demo_field = {"type": "Polygon", "coordinates": [[
        [-116.5650, 43.5800], [-116.5590, 43.5800], [-116.5590, 43.5850],
        [-116.5650, 43.5850], [-116.5650, 43.5800]]]}
    report = build_report(demo_field, "corn_silage", "limited")
    print(f"Field: {report['field']['acres']} acres | year odds: {report['year_odds']}")
    for o in report["options"]:
        print(f"  [{o['tag']}] {o['label']}: ${o['expected_profit_per_acre']}/ac expected, "
              f"${o['dry_year_profit_per_acre']}/ac dry year, score {o['score']}")
    print("Excluded:", [(e["crop"], e["reasons"]) for e in report["excluded"]])
    print("\nFull JSON for the first option:\n", json.dumps(report["options"][0], indent=2))
