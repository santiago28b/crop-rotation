"""
Current Boise River snowpack from NRCS SNOTEL, compared with the 30-year median.

Next summer's irrigation water in the Treasure Valley comes mostly from snow that
melts into the Boise River reservoirs. Low snow now = more likely a short-water year.

How it works:
  - Read today's snow water equivalent (SWE, inches of water in the snow) at 4
    SNOTEL stations in the Boise River headwaters.
  - Compare with the median SWE on the same calendar day over the last 30 years.
  - Basin percent of median = sum(today) / sum(median), the way NRCS reports it.
  - < 80% -> "low", > 120% -> "high", otherwise "normal".
  - Early in the season (basin median under 1 inch) the percent means little,
    so it reports "normal" and says it's too early.

API docs: https://wcc.sc.egov.usda.gov/awdbRestApi/swagger-ui/index.html (no key needed)
Try it:  python -m app.snowpack
"""

import json
import statistics
from datetime import date, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / "data" / "cache"
AWDB_URL = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"

# SNOTEL sites in the Boise River headwaters (station:state:network)
BOISE_STATIONS = {
    "306:ID:SNTL": "Atlanta Summit (Middle Fork Boise)",
    "496:ID:SNTL": "Graham Guard Station (North Fork Boise)",
    "637:ID:SNTL": "Mores Creek Summit (Mores Creek)",
    "830:ID:SNTL": "Trinity Mountain (South Fork Boise)",
}
YEARS_FOR_MEDIAN = 30
LOW_PCT, HIGH_PCT = 80, 120
TOO_EARLY_IN = 1.0


def water_year(d: date) -> int:
    """Water years start Oct 1: Nov 2026 is water year 2027."""
    return d.year + 1 if d.month >= 10 else d.year


def fetch_swe(triplet: str, begin: date, end: date) -> dict[str, float]:
    """Daily SWE in inches for one station: {"YYYY-MM-DD": value}."""
    params = {"stationTriplets": triplet, "elements": "WTEQ", "duration": "DAILY",
              "beginDate": begin.isoformat(), "endDate": end.isoformat()}
    resp = requests.get(AWDB_URL, params=params, timeout=120)
    resp.raise_for_status()
    out = {}
    for station in resp.json():
        for series in station.get("data", []):
            if series.get("stationElement", {}).get("elementCode") != "WTEQ":
                continue
            for v in series.get("values", []):
                if v.get("value") is not None:
                    out[str(v["date"])[:10]] = float(v["value"])
    return out


def _history(triplet: str, today: date, fetch, cache_dir: Path) -> dict[str, float]:
    """Past 30 water years of daily SWE (cached: old data doesn't change)."""
    first_wy = water_year(today) - YEARS_FOR_MEDIAN
    cached = cache_dir / f"snotel_{triplet.replace(':', '_')}_wy{first_wy}-{water_year(today) - 1}.json"
    if cached.exists():
        return json.loads(cached.read_text())
    data = fetch(triplet, date(first_wy - 1, 10, 1), date(water_year(today) - 1, 9, 30))
    cache_dir.mkdir(parents=True, exist_ok=True)
    cached.write_text(json.dumps(data))
    return data


def _median_same_day(history: dict[str, float], today: date) -> float | None:
    if (today.month, today.day) == (2, 29):
        today = today - timedelta(days=1)
    first_wy = water_year(today) - YEARS_FOR_MEDIAN
    values = []
    for wy in range(first_wy, water_year(today)):
        y = wy - 1 if today.month >= 10 else wy
        v = history.get(date(y, today.month, today.day).isoformat())
        if v is not None:
            values.append(v)
    return statistics.median(values) if len(values) >= 10 else None


def snowpack_status(today: date | None = None, fetch=fetch_swe, cache_dir: Path | None = None) -> dict:
    """Boise River basin snowpack vs. median. Raises if no station can be read."""
    today = today or date.today()
    cache_dir = cache_dir or CACHE_DIR

    stations = []
    for triplet, name in BOISE_STATIONS.items():
        try:
            recent = fetch(triplet, today - timedelta(days=7), today)
            history = _history(triplet, today, fetch, cache_dir)
        except Exception:
            continue
        current_day = max(recent) if recent else None
        current = recent.get(current_day) if current_day else None
        median = _median_same_day(history, date.fromisoformat(current_day)) if current_day else None
        stations.append({"station": triplet, "name": name, "date": current_day,
                         "swe_in": current, "median_in": median,
                         "pct_of_median": round(100 * current / median) if current is not None and median else None})

    usable = [s for s in stations if s["swe_in"] is not None and s["median_in"] is not None]
    if not usable:
        raise RuntimeError("no SNOTEL station in the Boise basin could be read")

    swe_sum = sum(s["swe_in"] for s in usable)
    median_sum = sum(s["median_in"] for s in usable)
    pct = round(100 * swe_sum / median_sum) if median_sum > 0 else None

    if median_sum < TOO_EARLY_IN or pct is None:
        level = "normal"
        note = (f"Too early in the snow season to tell: the stations normally hold only "
                f"{median_sum:.1f} inches of water right now. Check again from January; "
                "the April 1 snowpack is what sets the irrigation supply.")
    else:
        level = "low" if pct < LOW_PCT else ("high" if pct > HIGH_PCT else "normal")
        note = (f"Boise River snowpack is {pct}% of the 30-year median for this date, "
                f"so next season is treated as a {level}-snow year.")

    return {
        "level": level,
        "basin_pct_of_median": pct,
        "basin_swe_in": round(swe_sum, 1),
        "basin_median_in": round(median_sum, 1),
        "as_of": max(s["date"] for s in usable),
        "note": note,
        "stations": stations,
        "source": "NRCS SNOTEL (AWDB REST API), Boise River basin stations",
    }


if __name__ == "__main__":
    print(json.dumps(snowpack_status(), indent=2))
