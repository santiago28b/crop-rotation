"""
Climate facts from NASA POWER daily data, hemisphere-aware.

Everything is computed on a "season calendar": season day-of-year (sdoy) 1 = Jan 1 in the
northern hemisphere, = Jul 1 in the southern hemisphere, so "spring frost" / "fall frost"
and growing-season logic work anywhere. Convert back with `to_calendar_doy`.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.config import BASELINE_YEARS, RECENT_YEARS
from app.insights.water import eto_fao56
from app.schemas import ClimateProfile, MonthNormal, SeasonStats

HOT_DAY_C = 35
FROST_C = 0
GDD_BASE_C = 10


def season_offset_days(lat: float) -> int:
    return 0 if lat >= 0 else 182


def to_calendar_doy(sdoy: float, offset: int) -> int:
    return int((round(sdoy) - 1 + offset) % 365 + 1)


def to_season_doy(cal_doy: float, offset: int) -> int:
    return int((round(cal_doy) - 1 - offset) % 365 + 1)


def prepare(df: pd.DataFrame, lat: float, elevation_m: float | None) -> pd.DataFrame:
    """Add season calendar columns, GDD and FAO-56 ETo. Drops incomplete seasons."""
    df = df.copy()
    offset = season_offset_days(lat)
    sdate = df.index - pd.Timedelta(days=offset)
    df["season_year"] = sdate.year.to_numpy()
    df["sdoy"] = np.minimum(sdate.day_of_year.to_numpy(), 365)
    df["month"] = df.index.month
    df["gdd10"] = ((df["T2M_MAX"] + df["T2M_MIN"]) / 2 - GDD_BASE_C).clip(lower=0)
    df["eto"] = eto_fao56(df, lat, elevation_m)
    counts = df.groupby("season_year").size()
    full = counts[counts >= 300].index
    return df[df["season_year"].isin(full)]


def warmest_months(df: pd.DataFrame) -> list[int]:
    monthly = df.groupby("month")["T2M"].mean()
    return sorted(monthly.sort_values(ascending=False).index[:6].tolist())


def frost_dates(df: pd.DataFrame, threshold_c: float = FROST_C) -> pd.DataFrame:
    """Per season-year: last 'spring' frost sdoy (first half) and first 'fall' frost sdoy (second half)."""
    rows = []
    for yr, d in df.groupby("season_year"):
        frost = d.loc[d["T2M_MIN"] <= threshold_c, "sdoy"]
        spring = frost[frost < 183]
        fall = frost[frost >= 183]
        rows.append({"season_year": yr,
                     "last_spring": int(spring.max()) if len(spring) else 0,       # 0 = no spring frost
                     "first_fall": int(fall.min()) if len(fall) else 366})         # 366 = no fall frost
    return pd.DataFrame(rows).set_index("season_year")


def rain_onset(df: pd.DataFrame, min_10day_mm: float = 25, dry_spell_days: int = 10) -> float | None:
    """
    Median sdoy of the start of the rains: first day whose 10-day rain total >= min_10day_mm
    and whose following 30 days contain no dry spell longer than dry_spell_days.
    Standard rainfed-planting cue (used where frost doesn't set the calendar).
    """
    onsets = []
    for _, d in df.groupby("season_year"):
        p = d["PRECTOTCORR"].to_numpy()
        if len(p) < 300:
            continue
        r10 = np.convolve(p, np.ones(10), "valid")
        found = None
        for i in range(len(r10) - 30):
            if r10[i] >= min_10day_mm:
                nxt = p[i + 10:i + 40] < 1.0
                # longest run of dry days in the next 30
                run = best = 0
                for dry in nxt:
                    run = run + 1 if dry else 0
                    best = max(best, run)
                if best <= dry_spell_days:
                    found = i + 1
                    break
        if found:
            onsets.append(found)
    if len(onsets) < 3:
        return None
    return float(np.median(onsets))


def period_stats(df: pd.DataFrame, years: tuple[int, int], season_months: list[int]) -> SeasonStats:
    d = df[(df["season_year"] >= years[0]) & (df["season_year"] <= years[1])]
    fr = frost_dates(d)
    by_year = d.groupby("season_year")
    season = d[d["month"].isin(season_months)]
    season_by_year = season.groupby("season_year")

    # warmest two months for root-zone wetness (irrigation / drought stress signal)
    warm2 = d.groupby("month")["T2M"].mean().sort_values(ascending=False).index[:2].tolist()
    root = d[d["month"].isin(warm2)]["GWETROOT"].mean()

    has_frost = (fr["last_spring"] > 0).any() or (fr["first_fall"] < 366).any()
    last_spring = fr["last_spring"].replace(0, np.nan).mean()
    first_fall = fr["first_fall"].replace(366, np.nan).mean()
    frost_free = None
    if has_frost:
        ff = fr["first_fall"].replace(366, 365) - fr["last_spring"]
        frost_free = float(ff.mean())

    return SeasonStats(
        years=f"{years[0]}-{years[1]}",
        n_years=int(by_year.ngroups),
        frost_free_days=_r(frost_free),
        last_spring_frost_doy=_r(last_spring),
        first_fall_frost_doy=_r(first_fall),
        gdd_base10_season=_r(season_by_year["gdd10"].sum().mean(), 0),
        hot_days_35c=_r((season["T2M_MAX"] >= HOT_DAY_C).groupby(season["season_year"]).sum().mean()),
        precip_year_mm=_r(by_year["PRECTOTCORR"].sum().mean(), 0),
        precip_season_mm=_r(season_by_year["PRECTOTCORR"].sum().mean(), 0),
        eto_year_mm=_r(by_year["eto"].sum().mean(), 0),
        eto_season_mm=_r(season_by_year["eto"].sum().mean(), 0),
        root_wetness_summer=_r(root, 3),
        rain_onset_doy=_r(rain_onset(d), 0),
    )


def climate_profile(df: pd.DataFrame, lat: float) -> ClimateProfile:
    """df must already be `prepare`d."""
    offset = season_offset_days(lat)
    months = warmest_months(df)
    base = period_stats(df, BASELINE_YEARS, months)
    rec = period_stats(df, RECENT_YEARS, months)

    # frost DOYs are in season-days; convert to calendar for the UI
    for s in (base, rec):
        for f in ("last_spring_frost_doy", "first_fall_frost_doy", "rain_onset_doy"):
            v = getattr(s, f)
            if v is not None:
                setattr(s, f, float(to_calendar_doy(v, offset)))

    shift = {}
    for f in SeasonStats.model_fields:
        a, b = getattr(base, f), getattr(rec, f)
        shift[f] = round(b - a, 2) if isinstance(a, (int, float)) and isinstance(b, (int, float)) else None

    yearly = df.groupby("season_year").agg(precip=("PRECTOTCORR", "sum"), eto=("eto", "sum"))
    season = df[df["month"].isin(months)].groupby("season_year").agg(
        precip=("PRECTOTCORR", "sum"), hot=("T2M_MAX", lambda s: int((s >= HOT_DAY_C).sum())), gdd=("gdd10", "sum"))
    low, high = season["precip"].quantile([1 / 3, 2 / 3])

    recent = df[(df["season_year"] >= RECENT_YEARS[0])]
    mn = recent.groupby("month").agg(tmin=("T2M_MIN", "mean"), tmax=("T2M_MAX", "mean"),
                                     p=("PRECTOTCORR", "sum"), eto=("eto", "sum"), rw=("GWETROOT", "mean"))
    n_years = recent["season_year"].nunique()
    normals = [MonthNormal(month=int(m), tmin_c=_r(r.tmin), tmax_c=_r(r.tmax),
                           precip_mm=_r(r.p / n_years, 0), eto_mm=_r(r.eto / n_years, 0), root_wetness=_r(r.rw, 2))
               for m, r in mn.iterrows()]

    return ClimateProfile(
        source="NASA POWER daily (MERRA-2 / GPM-based), AG community; ETo = FAO-56 Penman-Monteith",
        years=f"{int(df['season_year'].min())}-{int(df['season_year'].max())}",
        growing_season_months=months,
        frost_free_climate=base.frost_free_days is None and rec.frost_free_days is None,
        baseline=base, recent=rec, shift=shift,
        trend_per_decade={
            "hot_days": round(_slope(season["hot"]) * 10, 2),
            "season_precip_mm": round(_slope(season["precip"]) * 10, 1),
            "gdd_season": round(_slope(season["gdd"]) * 10, 0),
            "eto_year_mm": round(_slope(yearly["eto"]) * 10, 1),
        },
        dry_years=season.index[season["precip"] <= low].tolist(),
        wet_years=season.index[season["precip"] >= high].tolist(),
        monthly_normals=normals,
    )


def _slope(series: pd.Series) -> float:
    s = series.dropna()
    if len(s) < 3:
        return 0.0
    x = s.index.to_series().astype(float)
    x = x - x.mean()
    return float((x * (s - s.mean())).sum() / (x ** 2).sum())


def _r(v, nd=1):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return round(float(v), nd)
