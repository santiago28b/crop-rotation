"""Load and validate the master crop list (app/data/crops.yaml)."""

from __future__ import annotations

from functools import lru_cache

import yaml
from pydantic import BaseModel

from app.config import APP_DATA_DIR


class Range(BaseModel):
    abs_min: float
    opt_min: float
    opt_max: float
    abs_max: float


class Cycle(BaseModel):
    min: int
    typ: int
    max: int


class GDD(BaseModel):
    base_c: float
    to_maturity: float | None = None


class Kc(BaseModel):
    ini: float
    mid: float
    end: float


class SensitiveStage(BaseModel):
    start_frac: float
    end_frac: float
    name: str
    heat_threshold_c: float


class Nitrogen(BaseModel):
    requirement_kg_ha: float
    credit_to_next_kg_ha: float


class Crop(BaseModel):
    id: str
    name: str
    family: str
    role: str                      # cash | cover | forage
    perennial: bool = False
    fall_sown: bool = False
    cycle_days: Cycle
    gdd: GDD
    temp_c: Range
    rain_mm: Range
    ph: Range
    kill_frost_c: float
    kc: Kc
    stage_days: list[int]
    sensitive_stage: SensitiveStage
    root_depth_m: float
    nitrogen: Nitrogen
    min_return_years: int
    tolerates_poor_drainage: bool
    harvester_class: str
    planter_class: str
    rainfed_ok: bool = True

    @property
    def is_legume(self) -> bool:
        return self.family == "Fabaceae"


@lru_cache(maxsize=1)
def load_crops() -> dict[str, Crop]:
    raw = yaml.safe_load((APP_DATA_DIR / "crops.yaml").read_text())
    crops = [Crop(**c) for c in raw["crops"]]
    return {c.id: c for c in crops}
