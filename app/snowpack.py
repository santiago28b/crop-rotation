"""
Current Boise River snowpack from NRCS SNOTEL, compared with the official median.

Next summer's irrigation water in the Treasure Valley comes mostly from snow that
melts into the Boise River reservoirs. Low snow now = more likely a short-water year.

How it works:
  - One request reads today's snow water equivalent (SWE, inches of water in the
    snow) at 4 SNOTEL stations in the Boise River headwaters, plus the NRCS median
    for the same day (centralTendencyType=MEDIAN, the median NRCS publishes).
  - Basin percent of median = sum(today) / sum(median), the way NRCS reports it.
  - < 80% -> "low", > 120% -> "high", otherwise "normal".
  - Before January it reports "normal" and says it's too early: NRCS starts its
    water supply forecasts in January, and early-season snow says little about
    the April 1 snowpack that sets the irrigation supply. Same if the basin
    median is under 1 inch.
  - The API randomly answers 403 to about 1 in 4 requests, so we retry.

API docs: https://wcc.sc.egov.usda.gov/awdbRestApi/swagger-ui/index.html (no key needed)
Try it:  python -m app.snowpack
"""

import json
import time
from datetime import date, timedelta

import requests

AWDB_URL = "https://wcc.sc.egov.usda.gov/awdbRestApi/services/v1/data"

# SNOTEL sites in the Boise River headwaters (station:state:network)
BOISE_STATIONS = {
    "306:ID:SNTL": "Atlanta Summit (Middle Fork Boise)",
    "496:ID:SNTL": "Graham Guard Station (North Fork Boise)",
    "637:ID:SNTL": "Mores Creek Summit (Mores Creek)",
    "830:ID:SNTL": "Trinity Mountain (South Fork Boise)",
}
LOW_PCT, HIGH_PCT = 80, 120
TOO_EARLY_IN = 1.0
FIRST_USEFUL_MONTH = 1          # January: NRCS's first water supply forecast of the year
EARLY_MONTHS = {10, 11, 12}     # Oct-Dec: start of the water year, too early to tell
RETRIES = 4


def _get(params: dict) -> list:
    """GET with retries: AWDB randomly returns 403/5xx."""
    for attempt in range(RETRIES):
        try:
            resp = requests.get(AWDB_URL, params=params, timeout=60)
            if resp.ok:
                return resp.json()
            err = requests.HTTPError(f"{resp.status_code} from SNOTEL")
        except requests.RequestException as e:
            err = e
        if attempt < RETRIES - 1:
            time.sleep(1 + attempt)
    raise err


def fetch_swe(triplets: list[str], begin: date, end: date) -> dict[str, dict[str, tuple]]:
    """Daily SWE and median (inches) per station: {triplet: {"YYYY-MM-DD": (value, median)}}."""
    data = _get({"stationTriplets": ",".join(triplets), "elements": "WTEQ", "duration": "DAILY",
                 "beginDate": begin.isoformat(), "endDate": end.isoformat(),
                 "centralTendencyType": "MEDIAN"})
    out = {}
    for station in data:
        days = {}
        for series in station.get("data", []):
            if series.get("stationElement", {}).get("elementCode") != "WTEQ":
                continue
            for v in series.get("values", []):
                if v.get("value") is not None:
                    median = v.get("median")
                    days[str(v["date"])[:10]] = (float(v["value"]),
                                                 float(median) if median is not None else None)
        out[station["stationTriplet"]] = days
    return out


def snowpack_status(today: date | None = None, fetch=fetch_swe) -> dict:
    """Boise River basin snowpack vs. median. Raises if no station can be read."""
    today = today or date.today()
    recent = fetch(list(BOISE_STATIONS), today - timedelta(days=7), today)

    stations, missing = [], []
    for triplet, name in BOISE_STATIONS.items():
        days = recent.get(triplet) or {}
        if not days:
            missing.append(name)
            continue
        day = max(days)
        current, median = days[day]
        stations.append({"station": triplet, "name": name, "date": day,
                         "swe_in": current, "median_in": median,
                         "pct_of_median": round(100 * current / median) if median else None})

    usable = [s for s in stations if s["median_in"] is not None]
    if not usable:
        raise RuntimeError("no SNOTEL station in the Boise basin could be read")

    swe_sum = sum(s["swe_in"] for s in usable)
    median_sum = sum(s["median_in"] for s in usable)
    pct = round(100 * swe_sum / median_sum) if median_sum > 0 else None

    if today.month in EARLY_MONTHS or median_sum < TOO_EARLY_IN or pct is None:
        level = "normal"
        note = ("Too early in the snow season to tell"
                + (f" (snowpack is {pct}% of median today)" if pct is not None else "")
                + ". NRCS starts its water supply forecasts in January, and the April 1 "
                "snowpack is what sets the irrigation supply, so a normal year is assumed.")
    else:
        level = "low" if pct < LOW_PCT else ("high" if pct > HIGH_PCT else "normal")
        note = (f"Boise River snowpack is {pct}% of the median for this date, "
                f"so next season is treated as a {level}-snow year.")
    if missing:
        note += f" Not read today: {', '.join(missing)}."

    return {
        "level": level,
        "basin_pct_of_median": pct,
        "basin_swe_in": round(swe_sum, 1),
        "basin_median_in": round(median_sum, 1),
        "as_of": max(s["date"] for s in usable),
        "note": note,
        "stations": stations,
        "stations_missing": missing,
        "source": "NRCS SNOTEL (AWDB REST API), Boise River basin stations vs. NRCS median",
    }


if __name__ == "__main__":
    print(json.dumps(snowpack_status(), indent=2))
