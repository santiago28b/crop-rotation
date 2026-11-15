"""
EcoCrop-style suitability (algorithm D), after Ramirez-Villegas et al. 2013.

Each requirement is a trapezoid: 0 below abs_min, rising to 1 at opt_min, flat to opt_max,
falling to 0 at abs_max. Climate suitability for a planting date = min over the cycle's
~monthly mean temperatures (one cold or hot month ruins the crop) combined with total rain
over the cycle (rainfed only). Soil suitability = pH trapezoid x drainage tolerance.
"""

from __future__ import annotations

import numpy as np

from app.insights.crops import Crop, Range
from app.schemas import SoilProfile


def trapezoid(x: float | None, r: Range) -> float:
    if x is None:
        return 0.5  # unknown -> neutral, flagged as a gap by the caller
    if x <= r.abs_min or x >= r.abs_max:
        return 0.0
    if x < r.opt_min:
        return (x - r.abs_min) / (r.opt_min - r.abs_min)
    if x <= r.opt_max:
        return 1.0
    return (r.abs_max - x) / (r.abs_max - r.opt_max)


def temp_suitability(t_clim: np.ndarray, plant_sdoy: int, cycle_days: int, crop: Crop) -> float:
    """t_clim: mean temperature per season-day (len 365)."""
    idx = (plant_sdoy - 1 + np.arange(cycle_days)) % 365
    temps = t_clim[idx]
    chunks = [temps[i:i + 30].mean() for i in range(0, len(temps), 30)]
    scores = [trapezoid(float(t), crop.temp_c) for t in chunks]
    # fall-sown / perennial crops sit through a cold winter by design: judge the average, not the worst month
    return round(float(np.mean(scores) if (crop.fall_sown or crop.perennial) else min(scores)), 3)


def rain_suitability(total_rain_mm: float, crop: Crop) -> float:
    return round(trapezoid(total_rain_mm, crop.rain_mm), 3)


def soil_suitability(soil: SoilProfile, crop: Crop) -> tuple[float, list[str]]:
    reasons = []
    ph_s = trapezoid(soil.ph, crop.ph)
    if soil.ph is None:
        reasons.append("Soil acidity (pH) is unknown")
    elif ph_s == 0:
        # map-unit pH is an average; keep a strong penalty but not a hard zero that hides the crop
        ph_s = 0.2
        reasons.append(f"Soil pH {soil.ph} is outside what this crop tolerates ({crop.ph.abs_min}-{crop.ph.abs_max}); the soil may need lime or sulfur, so check locally")
    elif ph_s < 1:
        reasons.append(f"Soil pH {soil.ph} is not ideal for this crop (best {crop.ph.opt_min}-{crop.ph.opt_max})")

    drain_s = 1.0
    dc = (soil.drainage_class or "").lower()
    if dc and not crop.tolerates_poor_drainage and ("poorly" in dc or "very poorly" in dc):
        drain_s = 0.3 if "somewhat" in dc else 0.1
        reasons.append(f"This soil drains poorly ({soil.drainage_class.lower()}); the crop needs good drainage")
    if crop.id == "rice_paddy" and dc and "well" in dc and "poorly" not in dc:
        drain_s = 0.6
        reasons.append("Paddy rice needs soil that holds water; this one drains well")

    tex = (soil.texture_class or "")
    if crop.id in ("potato", "groundnut", "sweet_potato", "onion") and tex in ("clay", "silty clay", "sandy clay"):
        drain_s = min(drain_s, 0.5)
        reasons.append(f"Heavy {tex} soil makes it hard to grow and dig root crops")

    return round(min(ph_s, drain_s), 3), reasons
