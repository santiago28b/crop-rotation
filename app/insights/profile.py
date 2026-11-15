"""Phase 1 orchestration: polygon -> FieldProfile (what we can see from space + soil)."""

from __future__ import annotations

import asyncio
import logging

from app import fieldgeo as geo
from app.config import CDL_SAMPLE_POINTS, CDL_TIME_BUDGET_S, IRRIGATED_ET_MARGIN_MM, OPENET_TIME_BUDGET_S
from app.insights import climate
from app.schemas import CropHistory, FieldInfo, FieldProfile, FieldProfileRequest, FieldWaterUse, SoilProfile
from app.sources import cdl, power, soilgrids, ssurgo

log = logging.getLogger(__name__)


async def crop_history(poly, budget_s: float | None = CDL_TIME_BUDGET_S) -> CropHistory:
    """US: CDL majority vote under a time budget. Elsewhere: the farmer types it."""
    lat, lon = geo.centroid(poly)
    if not geo.in_conus(lat, lon):
        return CropHistory(
            available=False, status="not_supported", source=None, years=[],
            note="Automatic crop history (USDA CDL) is only available in the continental US. "
                 "Please enter the crops grown in each of the last few years.")
    try:
        pts = geo.sample_points(poly, max_points=CDL_SAMPLE_POINTS)
        return await cdl.fetch_history(pts, budget_s=budget_s)
    except Exception as e:
        log.warning("CDL failed: %s", e)
        return CropHistory(available=False, status="unavailable", source="USDA CDL (CropScape)", years=[],
                           note=f"CropScape did not respond ({type(e).__name__}); please enter the crop history manually.")


async def measured_water_use(lat: float, lon: float) -> dict:
    """OpenET season ET via the /report engine's lookup (same cache, same key), under a time budget."""
    from app.engine import resolve_field_water      # the economics engine owns the OpenET client
    try:
        return await asyncio.wait_for(asyncio.to_thread(resolve_field_water, lat, lon), OPENET_TIME_BUDGET_S)
    except asyncio.TimeoutError:
        return {"season_et_in": None, "source": "OpenET: not used (too slow to answer)",
                "note": "No measured field water use."}


def classify_water_use(raw: dict, season_rain_mm: float) -> FieldWaterUse:
    """Did the field use far more water than the rain supplied? Then it was irrigated."""
    et_in = raw.get("season_et_in")
    if et_in is None:
        return FieldWaterUse(available=False, source=raw.get("source", "OpenET: not used"),
                             note="No satellite water-use measurement for this field, so we can't tell whether it is irrigated.")
    et_mm = round(et_in * 25.4)
    irrigated = et_mm > season_rain_mm + IRRIGATED_ET_MARGIN_MM
    compare = (f"about {et_in:.0f} inches of water per growing season ({raw.get('years')}), "
               f"while rain gives about {season_rain_mm / 25.4:.0f} inches")
    note = (f"Satellites measured this field using {compare}. That looks irrigated."
            if irrigated else
            f"Satellites measured this field using {compare}. That does not look irrigated.")
    return FieldWaterUse(available=True, season_et_mm=et_mm, season_rain_mm=round(season_rain_mm),
                         looks_irrigated=irrigated, years=raw.get("years"), source=raw["source"], note=note)


async def build_history(req: FieldProfileRequest) -> CropHistory:
    """POST /fields/history — re-poll after a 'partial'/'loading' profile; cached lookups make it fast."""
    return await crop_history(geo.field_polygon(req.geometry.model_dump()))


async def build_profile(req: FieldProfileRequest) -> FieldProfile:
    poly = geo.field_polygon(req.geometry.model_dump())
    lat, lon = geo.centroid(poly)
    conus = geo.in_conus(lat, lon)
    sources: list[str] = []
    gaps: list[str] = []

    async def soil_task() -> SoilProfile:
        if conus:
            try:
                s = await ssurgo.fetch_soil(lat, lon)
                if s:
                    return s
            except Exception as e:  # fall through to SoilGrids
                log.warning("SSURGO failed: %s", e)
                gaps.append("USDA soil survey not available here, so a global soil map was used")
        return await soilgrids.fetch_soil(lat, lon)

    (df, elevation), soil, history, raw_water = await asyncio.gather(
        power.fetch_daily(lat, lon), soil_task(), crop_history(poly), measured_water_use(lat, lon))

    pdf = climate.prepare(df, lat, elevation)
    clim = climate.climate_profile(pdf, lat)

    water_use = classify_water_use(raw_water, clim.recent.precip_season_mm)
    sources += [clim.source, soil.source]
    if water_use.available:
        sources.append(water_use.source)
    if history.source:
        sources.append(history.source)
    gaps += [
        "Weather is for the area around your field (about 30 miles), not your exact field",
        *([] if water_use.available else
          ["No field-level water use (ET) for this field: OpenET needs OPENET_API_KEY and covers the western US"]),
        "Long-term groundwater trends are not included yet",
    ]
    if not history.available:
        gaps.append("Crop history could not be found automatically, so it comes from your answers")

    return FieldProfile(
        field=FieldInfo(name=req.name, centroid_lat=round(lat, 5), centroid_lon=round(lon, 5),
                        area_ha=round(geo.area_ha(poly), 2), elevation_m=elevation,
                        hemisphere=geo.hemisphere(lat), in_conus=conus),
        soil=soil, climate=clim, crop_history=history, water_use=water_use, sources=sources, gaps=gaps,
    )
