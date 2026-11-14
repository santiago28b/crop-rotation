"""
Rotation rules engine (algorithm E): what the farmer-confirmed crop history implies for a
candidate crop — return intervals, same-family streaks, legume / cover-crop benefits.

The coefficients below are typical ranges from extension literature (verify before pitch):
  - consecutive same-family cash cropping: ~6 % yield drag per extra year, capped at 20 %
  - cereal after a legume: ~+10 % plus the N credit
  - violating the minimum return interval: -15 % (soil-borne disease pressure)
"""

from __future__ import annotations

from app.insights.crops import Crop
from app.schemas import CropYear, Rotation

MONOCULTURE_DRAG_PER_YEAR = 0.06
MONOCULTURE_DRAG_CAP = 0.20
LEGUME_BREAK_BONUS = 0.10
COVER_CROP_BONUS = 0.03
RETURN_INTERVAL_PENALTY = 0.15


def evaluate(history: list[CropYear], crop: Crop, crops: dict[str, Crop], planting_year: int) -> tuple[Rotation, float]:
    """Returns (Rotation, nitrogen credit kg/ha from the previous crop)."""
    hist = sorted(history, key=lambda y: y.year)
    flags: list[str] = []
    modifier = 1.0

    years_since = None
    for y in reversed(hist):
        if y.crop_id == crop.id:
            years_since = planting_year - y.year
            break
    interval_ok = years_since is None or years_since >= max(crop.min_return_years, 1)

    prev = hist[-1] if hist else None
    prev_crop = crops.get(prev.crop_id) if prev and prev.crop_id else None
    n_credit = prev_crop.nitrogen.credit_to_next_kg_ha if prev_crop else 0.0

    streak = 0
    for y in reversed(hist):
        c = crops.get(y.crop_id) if y.crop_id else None
        if c and c.family == crop.family:
            streak += 1
        else:
            break

    if crop.role == "cash":
        if streak >= 1 and prev_crop and prev_crop.family == crop.family:
            drag = min(MONOCULTURE_DRAG_PER_YEAR * streak, MONOCULTURE_DRAG_CAP)
            modifier -= drag
            flags.append(f"{streak} consecutive year(s) of {crop.family} crops already: pests/disease carry over, "
                         f"-{drag:.0%} yield drag applied")
        if prev_crop and prev_crop.is_legume and not crop.is_legume:
            modifier += LEGUME_BREAK_BONUS
            flags.append(f"legume ({prev_crop.name}) before this crop: +{LEGUME_BREAK_BONUS:.0%} rotation benefit "
                         f"and {n_credit:.0f} kg/ha N credit")
        if prev_crop and prev_crop.role == "cover":
            modifier += COVER_CROP_BONUS
            flags.append(f"cover crop ({prev_crop.name}) last season: better infiltration / organic matter")
        if not interval_ok:
            modifier -= RETURN_INTERVAL_PENALTY
            flags.append(f"grown {years_since} yr ago but should return only every {crop.min_return_years} yr "
                         f"(soil-borne disease); -{RETURN_INTERVAL_PENALTY:.0%}")
        if prev_crop and prev_crop.family == "Brassicaceae" and crop.family in ("Solanaceae", "Amaranthaceae"):
            flags.append("brassica before this crop: biofumigant effect may suppress nematodes")
    if prev and prev.crop_id is None:
        flags.append(f"previous crop '{prev.crop_label}' is not in the crop list; rotation effects unknown")
    if crop.perennial:
        flags.append("perennial stand: occupies the field for several years; N and soil benefits accrue after removal")

    return Rotation(
        yield_modifier=round(max(modifier, 0.5), 2),
        years_since_last_grown=years_since,
        return_interval_ok=interval_ok,
        consecutive_years_same_family=streak,
        flags=flags,
    ), n_credit
