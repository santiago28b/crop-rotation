"""Run with:  python -m pytest   (or)   python tests/test_engine.py"""

import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine import DEFAULT_CLIMATE, build_report, crop_outcome, load_crops, year_odds
from app.geo import field_center_and_acres

FIELD = {"type": "Polygon", "coordinates": [[
    [-116.5650, 43.5800], [-116.5590, 43.5800], [-116.5590, 43.5850],
    [-116.5650, 43.5850], [-116.5650, 43.5800]]]}
CROPS = load_crops()
IDAHO = {"state": "ID", "state_name": "Idaho", "county": "Canyon", "county_fips": "16027"}


def report(**kw):
    args = dict(field=FIELD, current_crop="corn_silage", water_supply="full",
                crops=CROPS, climate=DEFAULT_CLIMATE, location=IDAHO, snowpack="normal")
    args.update(kw)
    return build_report(**args)


def test_field_area():
    lat, lon, acres = field_center_and_acres(FIELD)
    # ~484 m x ~556 m = ~66 acres
    assert 60 < acres < 72, acres
    assert abs(lat - 43.582) < 0.01 and abs(lon + 116.562) < 0.01


def test_odds_sum_to_one_and_snowpack_shifts():
    for s in ("low", "normal", "high"):
        assert abs(sum(year_odds(DEFAULT_CLIMATE, s).values()) - 1) < 1e-9
    assert year_odds(DEFAULT_CLIMATE, "low")["dry"] > year_odds(DEFAULT_CLIMATE, "normal")["dry"]


def test_less_water_never_helps():
    for crop in CROPS.values():
        full = crop_outcome(crop, "full", "dry", DEFAULT_CLIMATE)["profit_per_acre"]
        short = crop_outcome(crop, "short", "dry", DEFAULT_CLIMATE)["profit_per_acre"]
        assert short <= full, crop["crop"]


def test_fao_yield_formula():
    crop = dict(CROPS["corn_silage"], heat_sensitivity=0.0)
    out = crop_outcome(crop, "short", "normal", DEFAULT_CLIMATE)
    ratio = out["water_available_in"] / out["water_needed_in"]
    expected = crop["yield_per_acre"] * (1 - crop["ky"] * (1 - ratio))
    assert abs(out["yield_per_acre"] - expected) < 0.2


def test_report_shape():
    r = report(water_supply="limited")
    assert len(r["options"]) >= 3
    assert r["options"][0]["tag"] == "current"
    assert len({o["crop"] for o in r["options"]}) == len(r["options"])
    for o in r["options"]:
        assert o["expected_profit_field"] == round(o["expected_profit_per_acre"] * r["field"]["acres"])
        assert o["why"] and o["risks"]


def test_rotation_rules():
    r = report(current_crop="potatoes")
    excluded = {e["crop"] for e in r["excluded"]}
    assert "sugar_beets" in excluded            # should not follow potatoes
    current = r["options"][0]
    assert any("two years in a row" in x for x in current["risks"])


def test_area_crops_limit_candidates():
    r = report(area_crops=[{"crop": "alfalfa"}, {"crop": "winter_wheat"}, {"crop": "quinoa"}])
    assert {o["crop"] for o in r["options"]} == {"corn_silage", "alfalfa", "winter_wheat"}
    assert r["unknown_area_crops"] == ["quinoa"]


def test_single_area_crop_still_gives_three_options():
    # README example: only one area crop listed; report must still rank >= 3
    r = report(area_crops=[{"crop": "alfalfa", "share": 0.35}])
    assert len(r["options"]) >= 3
    assert {o["crop"] for o in r["options"]} >= {"corn_silage", "alfalfa"}
    # A tag must not make a false claim: "safest_dry_year" only on the option
    # that really has the best dry-year profit of the non-current options.
    by_tag = {o["tag"]: o for o in r["options"]}
    if "safest_dry_year" in by_tag:
        best_dry = max(o["dry_year_profit_per_acre"] for o in r["options"][1:])
        assert by_tag["safest_dry_year"]["dry_year_profit_per_acre"] == best_dry


def test_top5_and_summary():
    r = report()                                      # full table, 9 candidates
    assert len(r["options"]) == 5
    assert r["options"][0]["tag"] == "current"
    best = max(r["options"], key=lambda o: o["score"])
    assert best["label"].lower() in r["summary"].lower()
    assert "/acre" in r["summary"]


def test_irrigation_method_and_water_source():
    dry_met = lambda **kw: report(water_supply="limited", **kw)["options"][0]["by_year_type"]["dry"]["water_met_pct"]
    base = dry_met()
    # defaults are sprinkler + surface water: explicit values change nothing
    assert dry_met(irrigation_method="sprinkler", water_source="surface") == base
    # more efficient application -> more of the allotment reaches the crop
    assert dry_met(irrigation_method="surface") < base < dry_met(irrigation_method="drip")
    # a well is not cut in a dry year; a canal is
    assert dry_met(water_source="surface") < dry_met(water_source="mixed") < dry_met(water_source="groundwater")
    # dryland: rain only
    none = report(irrigation_method="none")
    assert none["options"][0]["by_year_type"]["normal"]["water_available_in"] < 5
    assert none["assumptions"]["irrigation_efficiency"] == 0.0
    assert none["inputs"]["irrigation_method"] == "none"
    for bad in ({"irrigation_method": "bucket"}, {"water_source": "magic"}):
        try:
            report(**bad)
            assert False, "should have raised"
        except ValueError:
            pass


def test_top5_is_ranked_by_money():
    r = report()
    shown = [o["crop"] for o in r["options"][1:]]
    # the 4 shown are the 4 best scores among everything that fits
    everyone = report(area_crops=None)
    scores = sorted((o["score"] for o in everyone["options"][1:]), reverse=True)
    assert [o["score"] for o in r["options"][1:]] == scores
    assert r["options"][1]["tag"] == "best_overall" and len(shown) == 4


def test_huge_outline_is_rejected_not_hung():
    # a "field" traced while zoomed out to a whole region: fast 400, not a frozen server
    import time as _t
    from app import fieldgeo
    big = {"type": "Polygon", "coordinates": [[[-104, 40], [-96, 40], [-96, 43], [-104, 43], [-104, 40]]]}
    for call in (lambda: build_report(big, "corn_silage", "full", crops=CROPS, climate=DEFAULT_CLIMATE,
                                      location=IDAHO, snowpack="normal"),
                 lambda: fieldgeo.field_polygon(big)):
        try:
            call()
        except ValueError as e:
            assert "too large" in str(e)
        else:
            raise AssertionError("expected ValueError for a region-sized field")
    # and sampling a big-but-legal field is instant (it used to grid at 40 m)
    from shapely.geometry import shape
    ok = shape({"type": "Polygon", "coordinates": [[[-116.8, 43.5], [-116.7, 43.5], [-116.7, 43.58], [-116.8, 43.58], [-116.8, 43.5]]]})
    t0 = _t.time()
    pts = fieldgeo.sample_points(ok, max_points=5)
    assert 1 <= len(pts) <= 6 and _t.time() - t0 < 1.0


def test_local_water_needs_only_outside_home_region():
    from app.engine import apply_local_water_needs
    out = apply_local_water_needs({k: dict(v) for k, v in CROPS.items()},
                                  {"alfalfa": 30.04, "corn_silage": 22.0, "quinoa": 9}, skip="corn_silage")
    assert out["alfalfa"]["water_need_in"] == 30.0
    assert "FAO-56" in out["alfalfa"]["data_notes"]["water_need"]
    assert out["corn_silage"]["water_need_in"] == CROPS["corn_silage"]["water_need_in"]   # measured wins
    nebraska = {"type": "Polygon", "coordinates": [[[-99.49, 42.28], [-99.48, 42.28], [-99.48, 42.29], [-99.49, 42.29], [-99.49, 42.28]]]}
    there = build_report(nebraska, "corn_silage", "full", crops=CROPS, climate=DEFAULT_CLIMATE,
                         location={"state": "NE", "state_name": "Nebraska", "county": "Rock", "county_fips": "31149"},
                         snowpack="normal", crop_water_need_in={"alfalfa": 30.0})
    home = report(crop_water_need_in={"alfalfa": 30.0})
    need = lambda r: next(o for o in r["options"] + [] if o["crop"] == "alfalfa")["by_year_type"]["normal"]["water_needed_in"] \
        if any(o["crop"] == "alfalfa" for o in r["options"]) else None
    assert "Local here" in there["region_warning"] and home["region_warning"] is None
    if need(there) is not None:
        assert need(there) == 30.0
    if need(home) is not None:
        assert need(home) == CROPS["alfalfa"]["water_need_in"]                              # Idaho keeps AgriMet


def test_out_of_region_drops_crops_the_state_does_not_report():
    from app import engine
    nebraska = {"type": "Polygon", "coordinates": [[[-99.49, 42.28], [-99.48, 42.28], [-99.48, 42.29], [-99.49, 42.29], [-99.49, 42.28]]]}
    ne = {"state": "NE", "state_name": "Nebraska", "county": "Rock", "county_fips": "31149"}

    def fake_market(crops, location):          # USDA has NE numbers for everything except onions and mint
        out = {}
        for name, row in crops.items():
            row = dict(row)
            src = "crop table (data/crops.csv)" if name in ("onions", "mint") else "USDA NASS NE average 2020-2025"
            row["data_notes"] = {"yield": src, "price": src, "cost": "crop table (data/crops.csv)"}
            out[name] = row
        return out, "Yields and prices: USDA NASS QuickStats for NE (14 values found); crop table for the rest"

    with patch.object(engine, "with_local_market", fake_market), \
         patch.object(engine, "resolve_field_water", lambda lat, lon: {"season_et_in": None, "source": "x", "note": "x"}):
        r = build_report(nebraska, "corn_silage", "full", climate=DEFAULT_CLIMATE, location=ne, snowpack="normal")
    shown = {o["crop"] for o in r["options"]}
    assert "onions" not in shown and "mint" not in shown
    assert {e["crop"] for e in r["excluded"]} >= {"onions", "mint"}
    assert any("not grown commercially" in e["reasons"][0] for e in r["excluded"])
    assert len(r["options"]) >= 3


def test_bad_input():
    for kw in ({"current_crop": "bananas"}, {"water_supply": "lots"}):
        try:
            report(**kw)
        except ValueError:
            continue
        raise AssertionError(f"expected ValueError for {kw}")


def _fake_daily(lat, lon, start, end):
    import numpy as np
    import pandas as pd
    dates = pd.date_range(f"{start}-01-01", f"{end}-12-31")
    rng = np.random.default_rng(int(abs(lat * 100)))
    base = 11 - 14 * np.cos(2 * np.pi * (dates.dayofyear.values - 15) / 365)
    return pd.DataFrame({"T2M_MAX": base + 8 + rng.normal(0, 3, len(dates)),
                         "T2M_MIN": base - 8 + rng.normal(0, 3, len(dates)),
                         "PRECTOTCORR": rng.exponential(0.5, len(dates)),
                         "GWETROOT": 0.4}, index=dates)


def test_climate_uses_field_location_and_caches():
    import tempfile
    from unittest.mock import patch
    from app import climate as cl

    calls = []
    def fake(lat, lon, s, e):
        calls.append((lat, lon))
        return _fake_daily(lat, lon, s, e)

    tmp = Path(tempfile.mkdtemp())
    with patch.object(cl, "fetch_power", fake):
        a = cl.get_climate(43.58, -116.56, cache_dir=tmp)   # Nampa
        b = cl.get_climate(43.61, -116.52, cache_dir=tmp)   # nearby, same grid cell
        c = cl.get_climate(42.56, -114.46, cache_dir=tmp)   # Twin Falls, different cell
    assert calls == [(43.5, -116.5), (42.5, -114.5)]       # cached, not re-fetched
    assert a == b and a["grid_cell"] != c["grid_cell"]
    assert "43.5, -116.5" in a["source"]


def test_report_falls_back_when_nasa_unreachable():
    from unittest.mock import patch
    from app import engine
    with patch.object(engine, "get_climate", side_effect=ConnectionError("offline")):
        r = build_report(FIELD, "corn_silage", "full", crops=CROPS, location=IDAHO)
    assert "placeholder climate" in r["climate"]["source"]
    assert len(r["options"]) >= 3


def _nass_row(item, year, value, period="YEAR"):
    return {"short_desc": item, "year": str(year), "Value": value,
            "reference_period_desc": period, "domain_desc": "TOTAL"}


def test_market_overrides_yield_and_price():
    import tempfile
    from unittest.mock import patch
    from app import engine, market

    def fake_query(commodity, stat, state, key):
        assert state == "KS"
        if commodity == "WHEAT" and stat == "yield":
            return [_nass_row("WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE", 2022, "40"),
                    _nass_row("WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE", 2023, "50"),
                    _nass_row("WHEAT, WINTER - YIELD, MEASURED IN BU / ACRE", 2024, "(D)"),
                    _nass_row("WHEAT, WINTER, IRRIGATED - YIELD, MEASURED IN BU / ACRE", 2023, "99")]
        if commodity == "BEANS" and stat == "yield":
            return [_nass_row("BEANS, DRY EDIBLE - YIELD, MEASURED IN LB / ACRE", 2023, "2,400")]
        return []

    tmp = Path(tempfile.mkdtemp())
    with patch.object(market, "query_nass", fake_query):
        m = market.state_market("KS", api_key="x", cache_dir=tmp)
    assert m["winter_wheat"]["yield"]["value"] == 45 and m["winter_wheat"]["yield"]["years"] == "2022-2023"
    assert m["dry_beans"]["yield"]["value"] == 24          # lb -> cwt
    assert m["winter_wheat"]["price"] is None and m["corn_silage"]["price"] is None

    kansas = {"state": "KS", "state_name": "Kansas", "county": "Reno", "county_fips": "20155"}
    field = {"type": "Polygon", "coordinates": [[[-98.0, 38.0], [-97.99, 38.0], [-97.99, 38.01], [-98.0, 38.01]]]}
    with patch.object(engine, "state_market", lambda state: m):
        r = build_report(field, "winter_wheat", "full", climate=DEFAULT_CLIMATE, location=kansas)
    wheat = r["options"][0]
    assert wheat["data_notes"]["yield"] == "USDA NASS KS average 2022-2023"
    assert wheat["data_notes"]["price"].startswith("crop table")
    assert wheat["by_year_type"]["wet"]["yield_per_acre"] <= 45
    assert r["region_warning"] and "Reno, KS" in r["region_warning"]
    assert any("USDA NASS QuickStats for KS" in s for s in r["data_sources"])


def test_no_key_keeps_crop_table_and_home_region_has_no_warning():
    import os
    from unittest.mock import patch
    with patch.dict(os.environ, {}, clear=True):
        r = build_report(FIELD, "corn_silage", "full", climate=DEFAULT_CLIMATE, location=IDAHO)
    assert r["region_warning"] is None
    assert any("NASS_API_KEY is not set" in s for s in r["data_sources"])
    assert len(r["options"]) >= 3


def test_openet_field_water_use_math():
    from datetime import date
    from app.openet import field_water_use_in
    # 100 mm in every month of 2023-2025 -> Apr-Oct = 700 mm = 27.6 in each year
    def fake(lat, lon, start, end, key):
        return {f"{y}-{m:02d}-01": 100.0 for y in (2023, 2024, 2025) for m in range(1, 13)}
    import tempfile
    with patch.dict(os.environ, {"OPENET_API_KEY": "x"}):
        r = field_water_use_in(43.58, -116.56, date(2026, 11, 14), fake, Path(tempfile.mkdtemp()))
    assert r["season_et_in"] == 27.6
    assert r["years"] == "2023-2025"
    assert r["by_year_in"][2024] == 27.6


def test_openet_overrides_current_crop_water_need():
    from app.engine import apply_field_water
    fw = {"season_et_in": 24.0, "years": "2023-2025"}
    crops = apply_field_water({k: dict(v) for k, v in CROPS.items()}, "corn_silage", fw)
    assert crops["corn_silage"]["water_need_in"] == 24.0
    assert fw["applied_to_current_crop"] is True
    assert "water_need" in crops["corn_silage"]["data_notes"]
    # other crops untouched
    assert crops["alfalfa"]["water_need_in"] == CROPS["alfalfa"]["water_need_in"]


def test_openet_desert_measurement_not_applied():
    from app.engine import apply_field_water
    fw = {"season_et_in": 8.0, "years": "2023-2025"}   # sagebrush, not corn
    before = CROPS["corn_silage"]["water_need_in"]
    crops = apply_field_water({k: dict(v) for k, v in CROPS.items()}, "corn_silage", fw)
    assert crops["corn_silage"]["water_need_in"] == before
    assert fw["applied_to_current_crop"] is False
    assert "wasn't growing it" in fw["note"]


def test_openet_failure_keeps_report_working():
    from app import engine
    with patch.object(engine, "field_water_use_in", side_effect=ConnectionError("down")), \
         patch.dict(os.environ, {}, clear=True):
        r = build_report(FIELD, "corn_silage", "full", climate=DEFAULT_CLIMATE,
                         location=IDAHO, snowpack="normal")
    assert r["field_water_use"]["season_et_in"] is None
    assert "not used" in r["field_water_use"]["source"]
    assert len(r["options"]) >= 3


def _fake_swe(current_by_station, median):
    """Fake SNOTEL: each station has today's value and the same median."""
    def fetch(triplets, begin, end):
        return {t: {end.isoformat(): (current_by_station[t], median)}
                for t in triplets if t in current_by_station}
    return fetch


def test_snowpack_low_normal_and_too_early():
    from datetime import date
    from app.snowpack import BOISE_STATIONS, snowpack_status
    feb = date(2027, 2, 14)
    ids = list(BOISE_STATIONS)

    low = snowpack_status(feb, _fake_swe({t: 3.0 for t in ids}, 5.0))
    assert low["level"] == "low" and low["basin_pct_of_median"] == 60

    high = snowpack_status(feb, _fake_swe({t: 7.0 for t in ids}, 5.0))
    assert high["level"] == "high"

    tiny = snowpack_status(feb, _fake_swe({t: 0.0 for t in ids}, 0.1))
    assert tiny["level"] == "normal" and "Too early" in tiny["note"]


def test_snowpack_before_january_is_too_early():
    from datetime import date
    from app.snowpack import BOISE_STATIONS, snowpack_status
    nov = snowpack_status(date(2026, 11, 14), _fake_swe({t: 1.0 for t in BOISE_STATIONS}, 5.0))
    assert nov["level"] == "normal" and "Too early" in nov["note"]
    assert nov["basin_pct_of_median"] == 20                   # still reported, just not used


def test_snowpack_missing_station_is_listed():
    from datetime import date
    from app.snowpack import BOISE_STATIONS, snowpack_status
    ids = list(BOISE_STATIONS)
    r = snowpack_status(date(2027, 2, 14), _fake_swe({t: 3.0 for t in ids[:3]}, 5.0))
    assert len(r["stations"]) == 3 and len(r["stations_missing"]) == 1
    assert "Not read today" in r["note"]


def test_snowpack_retries_on_403():
    from unittest.mock import patch, MagicMock
    from app import snowpack
    bad, good = MagicMock(ok=False, status_code=403), MagicMock(ok=True)
    good.json.return_value = []
    with patch.object(snowpack.requests, "get", side_effect=[bad, bad, good]) as get, \
         patch.object(snowpack.time, "sleep"):
        assert snowpack._get({}) == []
    assert get.call_count == 3


def test_snowpack_auto_in_report():
    from unittest.mock import patch
    from app import engine
    fake = {"level": "low", "basin_pct_of_median": 60, "as_of": "2026-11-14",
            "note": "x", "source": "NRCS SNOTEL"}
    engine._SNOW_CACHE.clear()                                # the 1-hour cache must not leak between tests
    with patch.object(engine, "snowpack_status", lambda: dict(fake)):
        r = build_report(FIELD, "corn_silage", "full", crops=CROPS, climate=DEFAULT_CLIMATE,
                         location=IDAHO, snowpack="auto")
        again = build_report(FIELD, "corn_silage", "full", crops=CROPS, climate=DEFAULT_CLIMATE,
                             location=IDAHO, snowpack="auto")
    assert r["snowpack"]["level"] == "low" and again["snowpack"]["level"] == "low"
    engine._SNOW_CACHE.clear()
    assert r["year_odds"]["dry"] > 0.5                        # low snow shifts toward dry
    with patch.object(engine, "snowpack_status", side_effect=ConnectionError()):
        r = build_report(FIELD, "corn_silage", "full", crops=CROPS, climate=DEFAULT_CLIMATE,
                         location=IDAHO, snowpack="auto")
    assert r["snowpack"]["level"] == "normal" and "unavailable" in r["snowpack"]["source"]


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
