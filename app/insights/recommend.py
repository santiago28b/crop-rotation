"""
Phase 2 orchestration: confirmed history + resources + priorities -> ranked CandidateCrop list.

Per crop:  planting window (frost / season fit)  ->  harvest window (GDD or cycle length)
           -> water need (FAO-56)  ->  suitability (EcoCrop)  ->  rotation rules  ->  risks
           -> transparent weighted score.
Everything the economics model needs is in CandidateCrop; everything we don't know is in `gaps`.
"""

from __future__ import annotations

import datetime as dt
import logging

import numpy as np
import pandas as pd

from app import fieldgeo as geo
from app.config import BASELINE_YEARS, RECENT_YEARS
from app.insights import climate, frost, rotation, suitability
from app.insights.crops import Crop, load_crops
from app.insights.water import crop_water, rainfed_success_prob, sdoy_climatology
from app.schemas import (CandidateCrop, Equipment, Fertilizer, FieldInfo, FieldInsights, FieldInsightsRequest,
                         HarvestWindow, RejectedCrop, Risk, Suitability, Water, Window)
from app.sources import power, soilgrids, ssurgo

log = logging.getLogger(__name__)

RISK_VALUE = {"low": 0.1, "medium": 0.5, "high": 0.9, "unknown": 0.3}


class _Ctx:
    """Everything computed once per field, shared by all crops."""

    def __init__(self, pdf: pd.DataFrame, lat: float):
        self.offset = climate.season_offset_days(lat)
        self.recent = pdf[pdf["season_year"] >= RECENT_YEARS[0]]
        self.baseline = pdf[pdf["season_year"] <= BASELINE_YEARS[1]]
        self.t_clim = sdoy_climatology(self.recent, "T2M")
        self.eto_clim = sdoy_climatology(self.recent, "eto")
        self.p_clim = sdoy_climatology(self.recent, "PRECTOTCORR")
        self.tmean_all = self.recent["T2M"].to_numpy()
        self.tmax_all = self.recent["T2M_MAX"].to_numpy()
        self.sdoy_all = self.recent["sdoy"].to_numpy()
        self.syear_all = self.recent["season_year"].to_numpy()
        self.season_years = sorted(set(self.syear_all))
        self.frost_free = frost.safe_plant_sdoy(self.recent, 0) is None and frost.harvest_by_sdoy(self.recent, 0) is None

    def cal(self, sdoy: float) -> int:
        return climate.to_calendar_doy(sdoy, self.offset)


def _date_label(cal_doy: int) -> str:
    return (dt.date(2025, 1, 1) + dt.timedelta(days=int(cal_doy) - 1)).strftime("%b %d")


async def build_insights(req: FieldInsightsRequest) -> FieldInsights:
    poly = geo.field_polygon(req.geometry.model_dump())
    lat, lon = geo.centroid(poly)
    conus = geo.in_conus(lat, lon)

    df, elevation = await power.fetch_daily(lat, lon)
    soil = None
    if conus:
        try:
            soil = await ssurgo.fetch_soil(lat, lon)
        except Exception as e:
            log.warning("SSURGO failed: %s", e)
    if soil is None:
        soil = await soilgrids.fetch_soil(lat, lon)

    pdf = climate.prepare(df, lat, elevation)
    ctx = _Ctx(pdf, lat)
    planting_year = req.planting_year or dt.date.today().year + 1
    crops = load_crops()
    ids = req.candidate_crop_ids or list(crops)
    irrigated = req.resources.irrigation.type != "none"

    candidates: list[CandidateCrop] = []
    rejected: list[RejectedCrop] = []
    for cid in ids:
        crop = crops.get(cid)
        if not crop:
            rejected.append(RejectedCrop(crop_id=cid, name=cid, reason="unknown crop id"))
            continue
        try:
            out = _evaluate(crop, ctx, soil, req, planting_year, crops, irrigated)
        except Exception as e:  # one bad crop must not kill the whole response
            log.exception("crop %s failed", cid)
            out = RejectedCrop(crop_id=cid, name=crop.name, reason=f"internal error: {type(e).__name__}: {e}")
        (rejected if isinstance(out, RejectedCrop) else candidates).append(out)

    _rank_and_score(candidates, req)

    notes = [
        "Planting windows use 2013-2025 frost statistics; 'shift' compares with 2001-2012.",
        "Yield modifiers and N credits are rotation effects relative to the crop's own baseline yield; the economics model supplies prices, yields and costs.",
        "This is decision support from regional satellite/model data — confirm with local agronomists before acting.",
    ]
    if ctx.frost_free:
        notes.append("No killing frost in the record: planting windows follow temperature and rainfall suitability instead of frost dates.")

    return FieldInsights(
        field=FieldInfo(name=req.name, centroid_lat=round(lat, 5), centroid_lon=round(lon, 5),
                        area_ha=round(geo.area_ha(poly), 2), elevation_m=elevation,
                        hemisphere=geo.hemisphere(lat), in_conus=conus),
        planting_year=planting_year,
        candidates=candidates, rejected=rejected, notes=notes,
        sources=["NASA POWER (climate, ETo)", soil.source, "FAO EcoCrop + FAO-56 (crop requirements)"],
    )


def _evaluate(crop: Crop, ctx: _Ctx, soil, req: FieldInsightsRequest, planting_year: int,
              crops: dict[str, Crop], irrigated: bool) -> CandidateCrop | RejectedCrop:
    cycle = crop.cycle_days.typ
    evidence: list[str] = []
    gaps: list[str] = []

    if not crop.rainfed_ok and not irrigated:
        return RejectedCrop(crop_id=crop.id, name=crop.name, reason="needs irrigation; none available")

    # ---- 1. allowed planting range (season-days) ----
    safe = frost.safe_plant_sdoy(ctx.recent, crop.kill_frost_c)
    harvest_by = frost.harvest_by_sdoy(ctx.recent, crop.kill_frost_c)
    basis = ""
    if crop.fall_sown and not ctx.frost_free:
        # plant around the *median* first 0 °C frost: ~6 weeks before to 2 weeks after
        first_frost0 = frost.harvest_by_sdoy(ctx.recent, 0, risk=0.5) or 300
        cand = list(range(max(first_frost0 - 40, 1), min(first_frost0 + 15, 365), 5))
        basis = f"fall-sown: establish 6 weeks before to 2 weeks after the median first 0 °C frost (~{_date_label(ctx.cal(first_frost0))})"
    elif safe is None:
        cand = list(range(1, 366, 10))
        basis = "no killing frost here: window set by temperature and rainfall suitability"
    else:
        end = (harvest_by - cycle) if harvest_by else 365
        if end < safe:
            ff = (harvest_by or 365) - safe
            return RejectedCrop(crop_id=crop.id, name=crop.name,
                                reason=f"season too short: needs {cycle} days but only ~{ff} days between "
                                       f"{crop.kill_frost_c:+.0f} °C frosts (P<10 %)")
        cand = list(range(safe, end + 1, 5)) or [safe]
        basis = f"P(frost ≤ {crop.kill_frost_c:+.0f} °C after planting) < 10 % from {_date_label(ctx.cal(safe))}"
        if harvest_by is not None:
            basis += f"; {cycle}-day cycle must finish before {_date_label(ctx.cal(harvest_by))}"

    # ---- 2. best planting day = max climate suitability ----
    scores = []
    for s in cand:
        ts = suitability.temp_suitability(ctx.t_clim, s, cycle, crop)
        idx = (s - 1 + np.arange(cycle)) % 365
        rs = suitability.rain_suitability(float(ctx.p_clim[idx].sum()), crop)
        # rainfed: a rain shortfall is a strong penalty, not a veto (stored soil water, yield loss);
        # temperature outside the range IS a veto. Drought risk/irrigation need carry the rest.
        scores.append(ts if irrigated else ts * (0.3 + 0.7 * rs))
    scores = np.array(scores)
    if scores.max() <= 0:
        return RejectedCrop(crop_id=crop.id, name=crop.name,
                            reason="temperature outside the crop's range for every possible planting date")
    bi = int(scores.argmax())
    best = cand[bi]
    thr = max(0.5, 0.75 * scores[bi])
    lo = bi
    while lo > 0 and scores[lo - 1] >= thr:
        lo -= 1
    hi = bi
    while hi < len(cand) - 1 and scores[hi + 1] >= thr:
        hi += 1
    climate_s = float(scores[bi])

    shift = None
    if safe is not None and not crop.fall_sown:
        safe_base = frost.safe_plant_sdoy(ctx.baseline, crop.kill_frost_c)
        if safe_base is not None:
            shift = float(safe - safe_base)
            evidence.append(f"safe planting date moved {shift:+.0f} days vs 2001-2012 "
                            f"({_date_label(ctx.cal(safe_base))} → {_date_label(ctx.cal(safe))})")

    # ---- 3. harvest window across years (GDD if known, else cycle length) ----
    h_sdoys = _harvest_sdoys(ctx, best, crop, cycle)
    p10, p50, p90 = (int(np.percentile(h_sdoys, q)) for q in (10, 50, 90))
    h_basis = (f"GDD base {crop.gdd.base_c:g} °C to {crop.gdd.to_maturity:g}" if crop.gdd.to_maturity
               else f"typical {cycle}-day cycle")
    fits = True
    if harvest_by is not None and not crop.fall_sown:
        fits = p90 <= harvest_by
        if p50 > harvest_by:
            return RejectedCrop(crop_id=crop.id, name=crop.name,
                                reason=f"median harvest ({_date_label(ctx.cal(p50))}) falls after the first "
                                       f"{crop.kill_frost_c:+.0f} °C frost ({_date_label(ctx.cal(harvest_by))})")
        if not fits:
            evidence.append("late years run into fall frost: harvest 90th percentile is after the safe date")

    # ---- 4. water ----
    etc, peff, irr = crop_water(ctx.eto_clim, ctx.p_clim, best, crop, cycle)
    rain_prob = rainfed_success_prob(ctx.recent, best, cycle, crop.rain_mm.abs_min)
    allot = _allotment_mm(req.resources.irrigation)
    if irrigated:
        if allot is None or allot >= irr:
            deficit = "low"
        elif allot >= 0.7 * irr:
            deficit = "medium"
        else:
            deficit = "high"
    else:
        deficit = "low" if rain_prob >= 0.8 else ("medium" if rain_prob >= 0.5 else "high")
    evidence.append(f"crop water need {etc:.0f} mm; effective rain {peff:.0f} mm; irrigation need {irr:.0f} mm "
                    f"(FAO-56, 2013-2025 climatology)")
    if not irrigated:
        evidence.append(f"rain over the cycle met the crop minimum ({crop.rain_mm.abs_min:.0f} mm) in {rain_prob:.0%} of years")

    # ---- 5. soil, rotation, fertilizer ----
    soil_s, soil_reasons = suitability.soil_suitability(soil, crop)
    gaps += soil_reasons
    rot, n_credit = rotation.evaluate(req.history, crop, crops, planting_year)
    fert = Fertilizer(n_requirement_kg_ha=crop.nitrogen.requirement_kg_ha,
                      n_credit_from_previous_kg_ha=n_credit,
                      n_left_for_next_kg_ha=crop.nitrogen.credit_to_next_kg_ha)

    # ---- 6. risks ----
    risks: dict[str, Risk] = {}
    ss = crop.sensitive_stage
    s0, s1 = int(best + ss.start_frac * cycle), int(best + ss.end_frac * cycle)
    heat_p = _p_heat(ctx, s0, s1, ss.heat_threshold_c)
    risks["heat"] = Risk(level=_lvl(heat_p, 0.2, 0.5),
                         evidence=f"{heat_p:.0%} of years had ≥3 days ≥ {ss.heat_threshold_c:g} °C during {ss.name} "
                                  f"({_date_label(ctx.cal(s0))}–{_date_label(ctx.cal(s1))})")
    frost_p = frost.p_frost_between(ctx.recent, crop.kill_frost_c, best, (best + cycle - 1) % 365 + 1)
    risks["frost"] = Risk(level=_lvl(frost_p, 0.1, 0.3),
                          evidence=f"{frost_p:.0%} of years had a {crop.kill_frost_c:+.0f} °C frost inside the cycle")
    risks["drought"] = Risk(level=deficit, evidence=("irrigated; allotment " + (f"{allot:.0f} mm vs need {irr:.0f} mm" if allot else "unknown"))
                            if irrigated else f"rainfed; cycle rain sufficient in {rain_prob:.0%} of years")
    risks["water_security"] = Risk(level="unknown", evidence="GRACE-FO groundwater trend not wired yet")
    gaps.append("long-term water security (GRACE-FO) and field ET history (OpenET/MOD16) not yet included")
    gaps.append("NASA POWER ~50 km grid: local frost pockets / slopes can differ from these dates")

    # ---- 7. equipment, double crop ----
    has = None
    if req.resources.harvesters:
        has = crop.harvester_class in ("none", "manual") or crop.harvester_class in req.resources.harvesters
    partner = None
    if harvest_by is not None and not crop.fall_sown and crop.role == "cash":
        left = harvest_by - p50
        if left >= 60:
            partner = "mustard_cover"
            evidence.append(f"~{left} frost-free days remain after median harvest: a short cover crop fits")
    elif ctx.frost_free and crop.role == "cash" and cycle <= 150:
        partner = "cowpea" if crop.id != "cowpea" else "pearl_millet"
        evidence.append("frost-free climate: a second short-cycle crop is possible after harvest")

    return CandidateCrop(
        crop_id=crop.id, name=crop.name, role=crop.role,
        plant_window=Window(start_doy=ctx.cal(cand[lo]), end_doy=ctx.cal(cand[hi]), best_doy=ctx.cal(best),
                            shift_days_vs_baseline=shift, basis=basis),
        harvest_window=HarvestWindow(p10_doy=ctx.cal(p10), p50_doy=ctx.cal(p50), p90_doy=ctx.cal(p90), basis=h_basis),
        season_length_days=int(np.median(h_sdoys) - best) if not crop.fall_sown else cycle,
        fits_season=fits, double_crop_partner=partner,
        water=Water(crop_need_mm=etc, effective_rain_mm=peff, irrigation_need_mm=irr,
                    rainfed_success_prob=rain_prob, deficit_risk=deficit),
        fertilizer=fert, rotation=rot,
        suitability=Suitability(climate=round(climate_s, 3), soil=soil_s, overall=round(min(climate_s, soil_s), 3)),
        risks=risks,
        equipment=Equipment(harvester_class=crop.harvester_class, planter_class=crop.planter_class, farmer_has_harvester=has),
        score=0.0, evidence=evidence, gaps=gaps,
    )


def _allotment_mm(irrigation) -> float | None:
    """Water the crop can actually get from irrigation in a normal year, mm.

    A farmer-given allotment wins. Otherwise, if the UI passed the same full/limited/short
    answer it sends to POST /report, use that engine's assumptions (allotment x supply level x
    application efficiency) so the agronomy and money views share one water budget.
    """
    if irrigation.seasonal_allotment_mm is not None or irrigation.supply is None or irrigation.type == "none":
        return irrigation.seasonal_allotment_mm
    from app.engine import ASSUMPTIONS, MM_PER_IN
    method = "sprinkler" if irrigation.type == "pivot" else irrigation.type
    return round(ASSUMPTIONS["full_allotment_in"] * ASSUMPTIONS["supply_level"][irrigation.supply]
                 * ASSUMPTIONS["efficiency_by_method"][method] * MM_PER_IN)


def _harvest_sdoys(ctx: _Ctx, plant_sdoy: int, crop: Crop, cycle: int) -> list[int]:
    """Harvest season-day per year: accumulate GDD from planting if the crop has a GDD target, else fixed cycle."""
    if not crop.gdd.to_maturity:
        return [plant_sdoy + cycle] * len(ctx.season_years)
    out = []
    n = len(ctx.tmean_all)
    for yr in ctx.season_years:
        starts = np.where((ctx.syear_all == yr) & (ctx.sdoy_all == plant_sdoy))[0]
        if not len(starts):
            continue
        i = int(starts[0])
        seg = np.clip(ctx.tmean_all[i:min(i + int(cycle * 1.6), n)] - crop.gdd.base_c, 0, None)
        cum = np.cumsum(seg)
        hit = np.where(cum >= crop.gdd.to_maturity)[0]
        out.append(plant_sdoy + (int(hit[0]) if len(hit) else len(seg)))
    return out or [plant_sdoy + cycle]


def _p_heat(ctx: _Ctx, s0: int, s1: int, threshold: float, min_days: int = 3) -> float:
    hits, n = 0, 0
    for yr in ctx.season_years:
        m = ctx.syear_all == yr
        s = ctx.sdoy_all[m]
        inside = (s >= s0) & (s <= s1) if s1 >= s0 else (s >= s0) | (s <= s1 % 365)
        n += 1
        if (ctx.tmax_all[m][inside] >= threshold).sum() >= min_days:
            hits += 1
    return round(hits / n, 2) if n else 0.0


def _lvl(p: float, med: float, high: float) -> str:
    return "low" if p < med else ("medium" if p < high else "high")


def _rank_and_score(cands: list[CandidateCrop], req: FieldInsightsRequest) -> None:
    """Transparent weighted score 0-1 using the farmer's priorities; also fills water_productivity_rank."""
    if not cands:
        return
    by_irr = sorted(cands, key=lambda c: c.water.irrigation_need_mm)
    for r, c in enumerate(by_irr, 1):
        c.water.water_productivity_rank = r
    max_irr = max(c.water.irrigation_need_mm for c in cands) or 1.0
    w = req.priorities
    total_w = w.water + w.soil_health + w.income + w.low_risk or 1.0

    for c in cands:
        water_s = 1 - c.water.irrigation_need_mm / max_irr
        soil_s = min(1.0, (0.5 if c.fertilizer.n_left_for_next_kg_ha > 0 else 0)
                     + 0.3 * min(1.0, c.season_length_days and 1.0)  # placeholder weight for residue/cover
                     + (0.2 if c.role == "cover" else 0)
                     + (0.2 if c.rotation.consecutive_years_same_family == 0 else 0))
        # cover crops earn nothing directly; forage (alfalfa) is sold, so it counts like a cash crop
        income_s = 0.0 if c.role == "cover" else min(1.0, c.suitability.overall * c.rotation.yield_modifier)
        risk_s = 1 - float(np.mean([RISK_VALUE[r.level] for r in c.risks.values()]))
        if c.equipment.farmer_has_harvester is False:
            risk_s *= 0.8
        c.score = round((w.water * water_s + w.soil_health * soil_s + w.income * income_s + w.low_risk * risk_s) / total_w, 3)
    cands.sort(key=lambda c: c.score, reverse=True)
