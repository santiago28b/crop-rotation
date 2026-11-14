"""
Frost-probability planting windows (algorithm A).

From 25 years of daily T2M_MIN we know, for every season-day d, the share of years in which a
killing frost still happened after d (spring) or had already happened before d (fall).
"Safe" = that share <= FROST_RISK (10 %).  Computed per crop because kill temperatures differ
(maize dies at -1 °C, peas shrug off -6 °C).
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from app.config import FROST_RISK
from app.insights.climate import frost_dates


def safe_plant_sdoy(df: pd.DataFrame, kill_frost_c: float, risk: float = FROST_RISK) -> int | None:
    """Earliest season-day with P(frost <= kill_frost_c afterwards in spring) <= risk. None = never frosts."""
    fr = frost_dates(df, kill_frost_c)
    last = fr["last_spring"].to_numpy()
    if (last == 0).all():
        return None
    return int(math.ceil(np.quantile(last, 1 - risk))) + 1


def harvest_by_sdoy(df: pd.DataFrame, kill_frost_c: float, risk: float = FROST_RISK) -> int | None:
    """Latest season-day with P(frost <= kill_frost_c already happened in fall) <= risk. None = never frosts."""
    fr = frost_dates(df, kill_frost_c)
    first = fr["first_fall"].to_numpy()
    if (first == 366).all():
        return None
    return int(math.floor(np.quantile(first, risk))) - 1


def p_frost_between(df: pd.DataFrame, kill_frost_c: float, start_sdoy: int, end_sdoy: int) -> float:
    """Share of seasons with at least one day <= kill_frost_c inside [start, end] (wraps the year)."""
    hits, n = 0, 0
    for _, d in df.groupby("season_year"):
        n += 1
        s = d["sdoy"].to_numpy()
        inside = (s >= start_sdoy) & (s <= end_sdoy) if end_sdoy >= start_sdoy else (s >= start_sdoy) | (s <= end_sdoy)
        if (d["T2M_MIN"].to_numpy()[inside] <= kill_frost_c).any():
            hits += 1
    return round(hits / n, 2) if n else 0.0
