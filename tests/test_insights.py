"""Offline unit tests for the pure engine (no network)."""

import numpy as np
import pandas as pd

from app.insights import climate, frost, rotation, suitability
from app.insights.crops import load_crops
from app.insights.water import crop_water, eto_fao56, kc_curve, sdoy_climatology
from app.schemas import CropYear, SoilProfile


def synthetic_power(years=(2001, 2025), lat=43.6):
    """A fake temperate climate: sinusoidal temps, frost in winter, rain spread through the year."""
    idx = pd.date_range(f"{years[0]}-01-01", f"{years[1]}-12-31", freq="D")
    doy = idx.day_of_year.to_numpy()
    rng = np.random.default_rng(0)
    t = 10 - 14 * np.cos(2 * np.pi * (doy - 15) / 365) + rng.normal(0, 2, len(idx))
    df = pd.DataFrame({
        "T2M": t, "T2M_MAX": t + 7, "T2M_MIN": t - 7,
        "PRECTOTCORR": rng.gamma(0.5, 2.0, len(idx)),
        "RH2M": 55.0, "WS2M": 2.0,
        "ALLSKY_SFC_SW_DWN": 15 - 9 * np.cos(2 * np.pi * (doy - 15) / 365),
        "GWETTOP": 0.4, "GWETROOT": 0.5,
    }, index=idx)
    df.index.name = "date"
    return df


def test_crops_load_and_validate():
    crops = load_crops()
    assert len(crops) >= 20
    for c in crops.values():
        assert c.temp_c.abs_min < c.temp_c.opt_min <= c.temp_c.opt_max < c.temp_c.abs_max
        assert len(c.stage_days) == 4


def test_eto_is_positive_and_seasonal():
    df = synthetic_power()
    eto = eto_fao56(df, 43.6, 700)
    assert (eto >= 0).all()
    assert eto[df.index.month == 7].mean() > eto[df.index.month == 1].mean()


def test_kc_curve_scales_to_cycle():
    maize = load_crops()["maize"]
    assert len(kc_curve(maize, 130)) == 130
    assert abs(kc_curve(maize).max() - maize.kc.mid) < 1e-9


def test_frost_windows_make_sense():
    pdf = climate.prepare(synthetic_power(), 43.6, 700)
    safe = frost.safe_plant_sdoy(pdf, -1)
    by = frost.harvest_by_sdoy(pdf, -1)
    assert safe is not None and by is not None
    assert 60 < safe < 200 < by < 340
    # hardier crop can be planted earlier
    assert frost.safe_plant_sdoy(pdf, -6) <= safe


def test_southern_hemisphere_offset():
    assert climate.to_calendar_doy(1, 182) == 183
    assert climate.to_season_doy(183, 182) == 1
    assert climate.to_calendar_doy(climate.to_season_doy(50, 182), 182) == 50


def test_crop_water_balance():
    pdf = climate.prepare(synthetic_power(), 43.6, 700)
    maize = load_crops()["maize"]
    etc, peff, irr = crop_water(sdoy_climatology(pdf, "eto"), sdoy_climatology(pdf, "PRECTOTCORR"), 130, maize, 130)
    assert 300 < etc < 900
    assert irr == max(etc - peff, 0)


def test_trapezoid_and_soil():
    maize = load_crops()["maize"]
    assert suitability.trapezoid(25, maize.temp_c) == 1.0
    assert suitability.trapezoid(5, maize.temp_c) == 0.0
    assert 0 < suitability.trapezoid(14, maize.temp_c) < 1
    soil = SoilProfile(source="t", ph=6.5, drainage_class="Poorly drained")
    s, reasons = suitability.soil_suitability(soil, maize)
    assert s < 0.5 and reasons


def test_rotation_rules():
    crops = load_crops()
    hist = [CropYear(year=y, crop_id="wheat_spring", crop_label="Spring wheat", source="farmer") for y in (2023, 2024, 2025)]
    rot, credit = rotation.evaluate(hist, crops["wheat_spring"], crops, 2026)
    assert rot.yield_modifier < 1.0 and rot.consecutive_years_same_family == 3
    rot2, credit2 = rotation.evaluate(hist + [CropYear(year=2026, crop_id="chickpea", crop_label="Chickpea", source="farmer")],
                                      crops["wheat_spring"], crops, 2027)
    assert rot2.yield_modifier > 1.0 and credit2 == 30
    rot3, _ = rotation.evaluate([CropYear(year=2025, crop_id="potatoes", crop_label="Potatoes", source="cdl")],
                                crops["potatoes"], crops, 2026)
    assert not rot3.return_interval_ok


def test_shared_crop_ids_match_report_engine():
    """Every crop the /report engine knows (data/crops.csv) has an agronomic entry with the same id."""
    from app.engine import load_crops as load_report_crops
    assert set(load_report_crops()) <= set(load_crops())


def test_field_key_is_an_alias_of_geometry():
    from app.schemas import FieldInsightsRequest, FieldProfileRequest
    poly = {"type": "Polygon", "coordinates": [[[-116.565, 43.58], [-116.559, 43.58], [-116.559, 43.585], [-116.565, 43.58]]]}
    assert FieldProfileRequest(field=poly).geometry.type == "Polygon"
    assert FieldProfileRequest(geometry=poly).geometry.type == "Polygon"
    assert FieldInsightsRequest.model_validate({"field": poly}).geometry.coordinates == poly["coordinates"]


def test_cdl_categories_seen_live_are_mapped():
    # CropScape returns "Grass/Pasture" (observed live 2026-11-14), not "Grassland/Pasture"
    from app.sources.cdl import CDL_TO_CROP
    assert CDL_TO_CROP["Grass/Pasture"] == "pasture"
    assert CDL_TO_CROP["Grassland/Pasture"] == "pasture"


def test_profile_water_use_prefill_and_shared_water_budget():
    from app.insights.profile import classify_water_use
    from app.insights.recommend import _allotment_mm
    from app.schemas import Irrigation

    # 30 in of measured ET against 100 mm of rain: irrigated
    wet = classify_water_use({"season_et_in": 30.0, "years": "2021-2025", "source": "OpenET"}, 100)
    assert wet.available and wet.looks_irrigated is True and wet.season_et_mm == 762
    # desert-like ET close to rain: not irrigated
    dry = classify_water_use({"season_et_in": 6.0, "years": "2021-2025", "source": "OpenET"}, 100)
    assert dry.looks_irrigated is False
    # no key / failure: unknown, never a guess
    none = classify_water_use({"season_et_in": None, "source": "OpenET: not used (RuntimeError)"}, 100)
    assert none.available is False and none.looks_irrigated is None

    # one water budget for both engines: 42 in x 0.75 (limited) x 0.75 (sprinkler) = 23.6 in = 600 mm
    assert _allotment_mm(Irrigation(type="sprinkler", supply="limited")) == 600
    assert _allotment_mm(Irrigation(type="pivot", supply="limited")) == 600
    assert _allotment_mm(Irrigation(type="drip", supply="full")) > _allotment_mm(Irrigation(type="surface", supply="full"))
    assert _allotment_mm(Irrigation(type="sprinkler", supply="full", seasonal_allotment_mm=300)) == 300   # farmer's number wins
    assert _allotment_mm(Irrigation(type="sprinkler")) is None
    assert _allotment_mm(Irrigation(type="none", supply="full")) is None
