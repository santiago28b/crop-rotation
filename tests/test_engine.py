"""Run with:  python -m pytest   (or)   python tests/test_engine.py"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.engine import DEFAULT_CLIMATE, build_report, crop_outcome, load_crops, year_odds
from app.geo import field_center_and_acres

FIELD = {"type": "Polygon", "coordinates": [[
    [-116.5650, 43.5800], [-116.5590, 43.5800], [-116.5590, 43.5850],
    [-116.5650, 43.5850], [-116.5650, 43.5800]]]}
CROPS = load_crops()


def report(**kw):
    args = dict(field=FIELD, current_crop="corn_silage", water_supply="full",
                crops=CROPS, climate=DEFAULT_CLIMATE)
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
        r = build_report(FIELD, "corn_silage", "full", crops=CROPS)
    assert "placeholder climate" in r["climate"]["source"]
    assert len(r["options"]) >= 3


if __name__ == "__main__":
    tests = [v for k, v in dict(globals()).items() if k.startswith("test_")]
    for t in tests:
        t()
        print("ok", t.__name__)
    print(f"{len(tests)} tests passed")
