"""
USDA NASS Cropland Data Layer via the CropScape web service — US only, no key.
Docs: https://nassgeodata.gmu.edu/CropScape/  (CDLService GetCDLValue)

Automatic crop history is only possible inside CONUS. We sample a few points inside the
field polygon for every year and majority-vote. CropScape is slow and flaky (single
requests can take 30-60 s or time out), so:
  - every point/year answer is cached on disk forever (CDL is static once published)
  - the fetch runs under a time budget: whatever finished is returned as "partial" and the
    remaining requests keep running in the background, filling the cache, so a second call
    (POST /fields/history) a minute later is instant and complete.
"""

from __future__ import annotations

import asyncio
import logging
import re

import httpx

from app import cache
from app.config import CDL_FIRST_YEAR, CDL_LAST_YEAR, CDL_TIME_BUDGET_S
from app.fieldgeo import to_albers
from app.schemas import CropHistory, CropYear

log = logging.getLogger(__name__)

API_URL = "https://nassgeodata.gmu.edu/axis2/services/CDLService/GetCDLValue"
_RESULT_RE = re.compile(r"value:\s*(\d+),\s*category:\s*\"([^\"]*)\"")

# CDL category name -> crops.yaml id (None = known land cover we don't model)
CDL_TO_CROP = {
    "Corn": "maize", "Sweet Corn": "maize", "Pop or Orn Corn": "maize",
    "Winter Wheat": "winter_wheat", "Spring Wheat": "wheat_spring", "Durum Wheat": "wheat_spring",
    "Barley": "spring_barley", "Sorghum": "sorghum", "Millet": "pearl_millet", "Rice": "rice_paddy",
    "Soybeans": "soybean", "Dry Beans": "dry_beans", "Chick Peas": "chickpea", "Lentils": "lentil",
    "Peanuts": "groundnut", "Potatoes": "potatoes", "Sweet Potatoes": "sweet_potato",
    "Sunflower": "sunflower", "Canola": "canola", "Rape Seed": "canola", "Cotton": "cotton",
    "Sugarcane": "sugarcane", "Sugarbeets": "sugar_beets", "Alfalfa": "alfalfa", "Onions": "onions", "Mint": "mint",
    "Rye": "rye_cover", "Mustard": "mustard_cover", "Vetch": "vetch_cover", "Radishes": "radish_cover",
    "Fallow/Idle Cropland": "fallow", "Grassland/Pasture": "pasture", "Other Hay/Non Alfalfa": "hay",
}

_sem = asyncio.Semaphore(4)
_client: httpx.AsyncClient | None = None
_background: set[asyncio.Task] = set()


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=45)
    return _client


async def _point_value(year: int, x: float, y: float) -> tuple[int, str] | None:
    key = {"year": year, "x": round(x), "y": round(y)}
    hit = cache.get("cdl", key)
    if hit is not None:
        return tuple(hit) if hit else None
    client = _get_client()
    async with _sem:
        for attempt in range(2):
            try:
                resp = await client.get(API_URL, params={"year": year, "x": x, "y": y})
                m = _RESULT_RE.search(resp.text)
                if m:
                    val = (int(m.group(1)), m.group(2))
                    cache.put("cdl", key, val)
                    return val
                if resp.status_code == 200 and "Result" in resp.text:
                    cache.put("cdl", key, [])  # valid reply, no data (year not published here)
                    return None
            except httpx.HTTPError as e:
                log.info("CropScape %s %s: %s", year, type(e).__name__, e)
            await asyncio.sleep(2 * (attempt + 1))
    return None


async def fetch_history(points_lonlat: list[tuple[float, float]],
                        first_year: int = CDL_FIRST_YEAR, last_year: int = CDL_LAST_YEAR,
                        budget_s: float | None = CDL_TIME_BUDGET_S) -> CropHistory:
    albers = [to_albers(lon, lat) for lon, lat in points_lonlat]
    years = list(range(first_year, last_year + 1))
    n_pts = len(albers)

    tasks = {asyncio.ensure_future(_point_value(yr, x, y)): (yr, i)
             for yr in years for i, (x, y) in enumerate(albers)}
    done, pending = await asyncio.wait(tasks, timeout=budget_s)
    for t in pending:                      # keep filling the cache after we return
        _background.add(t)
        t.add_done_callback(_background.discard)

    results: dict[int, list[tuple[int, str]]] = {yr: [] for yr in years}
    answered: dict[int, int] = {yr: 0 for yr in years}
    for t in done:
        yr, _ = tasks[t]
        v = t.result() if not t.exception() else None
        if t.exception() is None:
            answered[yr] += 1
        if v is not None and v[0] != 0:
            results[yr].append(v)

    out: list[CropYear] = []
    for yr in years:
        vals = results[yr]
        if not vals:
            continue
        counts: dict[tuple[int, str], int] = {}
        for v in vals:
            counts[v] = counts.get(v, 0) + 1
        (code, label), n = max(counts.items(), key=lambda kv: kv[1])
        out.append(CropYear(year=yr, crop_id=CDL_TO_CROP.get(label), crop_label=label,
                            confidence=round(n / len(vals), 2), source="cdl", cdl_code=code))

    status = "complete" if not pending else ("partial" if out else "loading")
    src = "USDA NASS Cropland Data Layer via CropScape"
    if status == "loading":
        return CropHistory(available=False, status=status, source=src, years=[],
                           note=f"CropScape is slow right now; {len(pending)} of {len(tasks)} pixel lookups still running. "
                                "Call POST /fields/history again in ~1 minute, or enter the history manually.")
    if not out:
        return CropHistory(available=False, status="unavailable", source=src, years=[],
                           note="CropScape returned no crop data for this field.")
    low = [y.year for y in out if (y.confidence or 0) < 0.6]
    note = f"Majority crop per year from {n_pts} sampled 30 m pixels, {first_year}-{last_year}. Please confirm or correct."
    if status == "partial":
        note += f" {len(pending)} lookups still running — re-check /fields/history for the remaining years."
    if low:
        note += f" Mixed/uncertain years: {low}."
    return CropHistory(available=True, status=status, source=src, years=out, note=note)
