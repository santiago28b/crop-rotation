"""
Water balance pieces (FAO-56):
  - reference ET (ETo) from NASA POWER daily weather, Penman-Monteith
  - crop coefficient curve Kc(t) from stage lengths
  - seasonal crop water need, effective rain, irrigation need
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.insights.crops import Crop


def eto_fao56(df: pd.DataFrame, lat: float, elevation_m: float | None) -> pd.Series:
    """Daily FAO-56 Penman-Monteith reference ET (mm/day) for a grass reference surface."""
    T, Tmax, Tmin = df["T2M"], df["T2M_MAX"], df["T2M_MIN"]
    RH, u2, Rs = df["RH2M"], df["WS2M"], df["ALLSKY_SFC_SW_DWN"]
    z = elevation_m or 0.0

    P = 101.3 * ((293 - 0.0065 * z) / 293) ** 5.26
    gamma = 0.000665 * P

    def svp(t):
        return 0.6108 * np.exp(17.27 * t / (t + 237.3))

    es = (svp(Tmax) + svp(Tmin)) / 2
    ea = (RH / 100) * es
    delta = 4098 * svp(T) / (T + 237.3) ** 2

    doy = df.index.day_of_year.to_numpy()
    phi = np.radians(lat)
    dr = 1 + 0.033 * np.cos(2 * np.pi / 365 * doy)
    dec = 0.409 * np.sin(2 * np.pi / 365 * doy - 1.39)
    ws = np.arccos(np.clip(-np.tan(phi) * np.tan(dec), -1, 1))
    Ra = 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    Rso = (0.75 + 2e-5 * z) * Ra
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.clip(np.where(Rso > 0, Rs / Rso, 0.5), 0.3, 1.0)
    Rns = 0.77 * Rs
    Rnl = 4.903e-9 * ((Tmax + 273.16) ** 4 + (Tmin + 273.16) ** 4) / 2 * (0.34 - 0.14 * np.sqrt(ea.clip(lower=0))) * (1.35 * ratio - 0.35)
    Rn = Rns - Rnl

    eto = (0.408 * delta * Rn + gamma * 900 / (T + 273) * u2 * (es - ea)) / (delta + gamma * (1 + 0.34 * u2))
    return eto.clip(lower=0).fillna(0)


def sdoy_climatology(df: pd.DataFrame, column: str, smooth_days: int = 15) -> np.ndarray:
    """Mean value per season-day (array index 0 = sdoy 1, length 365), circularly smoothed."""
    clim = df.groupby("sdoy")[column].mean().reindex(range(1, 366)).interpolate(limit_direction="both").to_numpy()
    k = np.ones(smooth_days) / smooth_days
    padded = np.concatenate([clim[-smooth_days:], clim, clim[:smooth_days]])
    return np.convolve(padded, k, "same")[smooth_days:-smooth_days]


def kc_curve(crop: Crop, total_days: int | None = None) -> np.ndarray:
    """Daily Kc over the cycle: flat ini, linear dev, flat mid, linear late (FAO-56 Fig. 25)."""
    stages = np.array(crop.stage_days, dtype=float)
    if total_days:
        stages = stages * total_days / stages.sum()
    n = [max(int(round(s)), 1) for s in stages]
    ini = np.full(n[0], crop.kc.ini)
    dev = np.linspace(crop.kc.ini, crop.kc.mid, n[1])
    mid = np.full(n[2], crop.kc.mid)
    late = np.linspace(crop.kc.mid, crop.kc.end, n[3])
    return np.concatenate([ini, dev, mid, late])


def effective_rain_scs(p_month_mm: float) -> float:
    """USDA-SCS monthly effective rainfall (FAO CROPWAT default)."""
    if p_month_mm <= 250:
        return max(p_month_mm * (125 - 0.2 * p_month_mm) / 125, 0.0)
    return 125 + 0.1 * p_month_mm


def crop_water(eto_clim: np.ndarray, p_clim: np.ndarray, plant_sdoy: int, crop: Crop,
               cycle_days: int) -> tuple[float, float, float]:
    """Seasonal (crop ET, effective rain, irrigation need) in mm from planting over cycle_days."""
    kcs = kc_curve(crop, cycle_days)
    idx = (plant_sdoy - 1 + np.arange(len(kcs))) % 365
    etc = float((kcs * eto_clim[idx]).sum())
    p = p_clim[idx]
    peff = sum(effective_rain_scs(float(p[i:i + 30].sum())) for i in range(0, len(p), 30))
    return round(etc, 0), round(peff, 0), round(max(etc - peff, 0.0), 0)


def rainfed_success_prob(df: pd.DataFrame, plant_sdoy: int, cycle_days: int, need_mm: float) -> float:
    """Share of seasons in which rain over the cycle met need_mm."""
    ok, n = 0, 0
    for _, d in df.groupby("season_year"):
        p = d.groupby("sdoy")["PRECTOTCORR"].sum().reindex(range(1, 366)).fillna(0).to_numpy()
        idx = (plant_sdoy - 1 + np.arange(cycle_days)) % 365
        n += 1
        if p[idx].sum() >= need_mm:
            ok += 1
    return round(ok / n, 2) if n else 0.0
