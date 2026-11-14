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

app = FastAPI(title="Crop Rotation Advisor")
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
        )
    except (ValueError, KeyError) as e:
        raise HTTPException(status_code=400, detail=str(e))
