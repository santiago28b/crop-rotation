"""
Web API for the crop recommendation engine.

Run:   uvicorn app.main:app --reload
Docs:  http://localhost:8000/docs
"""

from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.engine import build_report, load_crops

app = FastAPI(title="Patato")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class AreaCrop(BaseModel):
    crop: str
    share: float | None = None


class ReportRequest(BaseModel):
    field: dict                                   # GeoJSON Polygon (or Feature) drawn on the map
    current_crop: str
    water_supply: Literal["full", "limited", "short"] = "full"
    area_crops: list[AreaCrop] | None = None      # common crops in the area (from Ethan's part)
    snowpack: Literal["auto", "low", "normal", "high"] = "auto"   # auto = live SNOTEL near Boise
    # How the field is watered -> irrigation efficiency ("none" = dryland, rain only)
    irrigation_method: Literal["none", "surface", "sprinkler", "drip"] = "sprinkler"
    # Where the water comes from -> how hard a dry year cuts deliveries
    water_source: Literal["surface", "groundwater", "mixed"] = "surface"
    # Optional {crop id: inches}: water needs computed for this location by the agronomy
    # engine (FAO-56). Used only outside southwest Idaho, where the table doesn't apply.
    crop_water_need_in: dict[str, float] | None = None


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/crops")
def crops():
    """Crops the engine knows about (for the 'current crop' dropdown)."""
    return [{"crop": c["crop"], "label": c["label"]} for c in load_crops().values()]


@app.post("/report")
def report(req: ReportRequest):
    try:
        return build_report(
            field=req.field,
            current_crop=req.current_crop,
            water_supply=req.water_supply,
            area_crops=[c.model_dump() for c in req.area_crops] if req.area_crops else None,
            snowpack=req.snowpack,
            irrigation_method=req.irrigation_method,
            water_source=req.water_source,
            crop_water_need_in=req.crop_water_need_in,
        )
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))


# --- NASA-data insights (fields profile/history/insights, crop catalog, data provenance) ---
from app.routers import crops as catalog_router, fields as fields_router, meta as meta_router  # noqa: E402

app.include_router(fields_router.router)
app.include_router(catalog_router.router)
app.include_router(meta_router.router)
