"""
Pydantic models = the API contract shared with the UI (phase 1 + 2) and the economics
model (CandidateCrop). Units are metric everywhere: mm, kg/ha, °C, day-of-year (DOY).

Keep this file boring and stable; teammates code against it.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


# ---------- shared ----------

class GeoJSONGeometry(BaseModel):
    """A GeoJSON geometry, or a Feature / FeatureCollection wrapping one (what Leaflet's
    layer.toGeoJSON() returns). Coordinates are [lon, lat] as in the GeoJSON spec."""
    type: Literal["Polygon", "MultiPolygon", "Point", "Feature", "FeatureCollection"]
    coordinates: Any = None
    geometry: Any = None
    features: Any = None


class FieldInfo(BaseModel):
    name: str | None = None
    centroid_lat: float
    centroid_lon: float
    area_ha: float
    elevation_m: float | None = Field(None, description="NASA POWER grid-cell elevation (coarse)")
    hemisphere: Literal["N", "S"]
    in_conus: bool = Field(..., description="True -> US-only datasets (CDL crop history, SSURGO soil) apply")


# ---------- phase 1: field profile ----------

class SoilProfile(BaseModel):
    source: str
    name: str | None = Field(None, description="SSURGO map-unit name (US only)")
    texture_class: str | None = None
    sand_pct: float | None = None
    silt_pct: float | None = None
    clay_pct: float | None = None
    ph: float | None = None
    organic_matter_pct: float | None = None
    bulk_density_g_cm3: float | None = None
    cec_cmol_kg: float | None = None
    awc_mm_per_m: float | None = Field(None, description="plant-available water, mm per metre of soil")
    drainage_class: str | None = None
    slope_pct: float | None = None
    taxonomic_order: str | None = None
    notes: list[str] = []


class SeasonStats(BaseModel):
    """Climate facts averaged over a block of years."""
    years: str
    n_years: int
    frost_free_days: float | None = None
    last_spring_frost_doy: float | None = None
    first_fall_frost_doy: float | None = None
    gdd_base10_season: float
    hot_days_35c: float
    precip_year_mm: float
    precip_season_mm: float
    eto_year_mm: float = Field(..., description="FAO-56 reference evapotranspiration (grass)")
    eto_season_mm: float
    root_wetness_summer: float | None = Field(None, description="NASA POWER GWETROOT 0-1, warmest two months")
    rain_onset_doy: float | None = Field(None, description="median start of the rains (rainfed planting cue)")


class MonthNormal(BaseModel):
    month: int
    tmin_c: float
    tmax_c: float
    precip_mm: float
    eto_mm: float
    root_wetness: float | None = None


class ClimateProfile(BaseModel):
    source: str
    years: str
    growing_season_months: list[int] = Field(..., description="the 6 warmest months at this location")
    frost_free_climate: bool
    baseline: SeasonStats
    recent: SeasonStats
    shift: dict[str, float | None] = Field(..., description="recent minus baseline, per SeasonStats field")
    trend_per_decade: dict[str, float]
    dry_years: list[int]
    wet_years: list[int]
    monthly_normals: list[MonthNormal]


class CropYear(BaseModel):
    year: int
    crop_id: str | None = Field(None, description="id in crops.yaml, or null if unmapped/unknown")
    crop_label: str = Field(..., description="human label, e.g. CDL category or what the farmer typed")
    confidence: float | None = Field(None, description="share of sampled pixels agreeing (CDL) ; null for farmer input")
    source: Literal["cdl", "farmer", "unknown"] = "unknown"
    cdl_code: int | None = None


class CropHistory(BaseModel):
    available: bool
    status: Literal["complete", "partial", "loading", "unavailable", "not_supported"] = "unavailable"
    source: str | None = None
    years: list[CropYear] = []
    note: str


class FieldProfile(BaseModel):
    field: FieldInfo
    soil: SoilProfile
    climate: ClimateProfile
    crop_history: CropHistory
    sources: list[str]
    gaps: list[str]


# `field` is accepted as an alias of `geometry` so the UI can send the same body shape to /report and /fields/*.
_GEOMETRY = Field(..., validation_alias=AliasChoices("geometry", "field"),
                  description="field polygon as GeoJSON; the key may be `geometry` or `field` (same as POST /report)")


class FieldProfileRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    geometry: GeoJSONGeometry = _GEOMETRY
    name: str | None = None


# ---------- phase 2: insights (input) ----------

class Irrigation(BaseModel):
    type: Literal["none", "surface", "sprinkler", "pivot", "drip"] = "none"
    seasonal_allotment_mm: float | None = Field(None, description="water the farmer can apply per season, mm depth; null = unlimited/unknown")


class Resources(BaseModel):
    irrigation: Irrigation = Irrigation()
    harvesters: list[str] = Field([], description="e.g. grain_combine, root_harvester, forage_harvester, cotton_picker, cane_harvester, manual")
    planters: list[str] = []
    labor: Literal["low", "medium", "high"] | None = None


class Priorities(BaseModel):
    """Relative weights 0-1 (not required to sum to 1)."""
    water: float = 1.0
    soil_health: float = 1.0
    income: float = 1.0
    low_risk: float = 1.0


class FieldInsightsRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    geometry: GeoJSONGeometry = _GEOMETRY
    name: str | None = None
    history: list[CropYear] = Field([], description="farmer-confirmed crop history, oldest first")
    resources: Resources = Resources()
    priorities: Priorities = Priorities()
    planting_year: int | None = None
    candidate_crop_ids: list[str] | None = Field(None, description="restrict to these crops; null = all in crops.yaml")


# ---------- phase 2: insights (output = contract with the economics model) ----------

class Window(BaseModel):
    """Calendar day-of-year window. If start_doy > end_doy the window wraps over New Year
    (e.g. 300 -> 40 = late Oct to early Feb), common for fall-sown crops and the southern hemisphere."""
    start_doy: int
    end_doy: int
    best_doy: int
    shift_days_vs_baseline: float | None = Field(None, description="+ means the window now opens later than 2001-2012")
    basis: str = Field(..., description="how the window was derived, e.g. 'frost P<10% & cycle fits before fall frost'")


class HarvestWindow(BaseModel):
    p10_doy: int
    p50_doy: int
    p90_doy: int
    basis: str


class Water(BaseModel):
    crop_need_mm: float = Field(..., description="seasonal crop ET = sum(Kc * ETo) over the cycle")
    effective_rain_mm: float
    irrigation_need_mm: float
    rainfed_success_prob: float = Field(..., description="share of years the cycle rain met the crop's minimum")
    deficit_risk: Literal["low", "medium", "high"]
    water_productivity_rank: int | None = Field(None, description="1 = least irrigation need among candidates")


class Fertilizer(BaseModel):
    n_requirement_kg_ha: float
    n_credit_from_previous_kg_ha: float
    n_left_for_next_kg_ha: float


class Rotation(BaseModel):
    yield_modifier: float = Field(..., description="1.10 = +10 % vs the crop's baseline yield, from rotation effects")
    years_since_last_grown: int | None
    return_interval_ok: bool
    consecutive_years_same_family: int
    flags: list[str]


class Suitability(BaseModel):
    climate: float = Field(..., ge=0, le=1)
    soil: float = Field(..., ge=0, le=1)
    overall: float = Field(..., ge=0, le=1)


class Risk(BaseModel):
    level: Literal["low", "medium", "high", "unknown"]
    evidence: str


class Equipment(BaseModel):
    harvester_class: str
    planter_class: str
    farmer_has_harvester: bool | None = Field(None, description="null when the farmer listed no equipment")


class CandidateCrop(BaseModel):
    crop_id: str
    variety_id: str | None = None
    name: str
    role: Literal["cash", "cover", "forage"]
    plant_window: Window
    harvest_window: HarvestWindow
    season_length_days: int
    fits_season: bool
    double_crop_partner: str | None = None
    water: Water
    fertilizer: Fertilizer
    rotation: Rotation
    suitability: Suitability
    risks: dict[str, Risk]
    equipment: Equipment
    score: float = Field(..., description="0-1 transparent weighted score using the farmer's priorities")
    evidence: list[str]
    gaps: list[str]


class RejectedCrop(BaseModel):
    crop_id: str
    name: str
    reason: str


class FieldInsights(BaseModel):
    field: FieldInfo
    planting_year: int
    candidates: list[CandidateCrop]
    rejected: list[RejectedCrop]
    notes: list[str]
    sources: list[str]
