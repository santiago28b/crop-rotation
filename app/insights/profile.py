"""Phase 1 orchestration: polygon -> FieldProfile (what we can see from space + soil)."""

from __future__ import annotations

import asyncio
import logging

from app import fieldgeo as geo
from app.config import CDL_SAMPLE_POINTS, CDL_TIME_BUDGET_S
from app.insights import climate
from app.schemas import CropHistory, FieldInfo, FieldProfile, FieldProfileRequest, SoilProfile
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
                gaps.append("SSURGO unavailable; used SoilGrids instead")
        return await soilgrids.fetch_soil(lat, lon)

    (df, elevation), soil, history = await asyncio.gather(
        power.fetch_daily(lat, lon), soil_task(), crop_history(poly))

    pdf = climate.prepare(df, lat, elevation)
    clim = climate.climate_profile(pdf, lat)

    sources += [clim.source, soil.source]
    if history.source:
        sources.append(history.source)
    gaps += [
        "NASA POWER is a ~50 km grid: temperatures/rain are regional, not field-specific (lapse-rate downscaling planned)",
        "No field-level water-use (ET) yet: OpenET (US) / MODIS MOD16 (global) pending",
        "No groundwater trend yet: GRACE-FO lookup pending",
    ]
    if not history.available:
        gaps.append("crop history not auto-detected; relies on farmer input")

    return FieldProfile(
        field=FieldInfo(name=req.name, centroid_lat=round(lat, 5), centroid_lon=round(lon, 5),
                        area_ha=round(geo.area_ha(poly), 2), elevation_m=elevation,
                        hemisphere=geo.hemisphere(lat), in_conus=conus),
        soil=soil, climate=clim, crop_history=history, sources=sources, gaps=gaps,
    )
