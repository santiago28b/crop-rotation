import httpx
from fastapi import APIRouter, HTTPException

from app.insights.recommend import build_insights
from app.insights.profile import build_history, build_profile
from app.schemas import CropHistory, FieldInsights, FieldInsightsRequest, FieldProfile, FieldProfileRequest

router = APIRouter(prefix="/fields", tags=["fields"])


@router.post("/history", response_model=CropHistory,
             summary="Crop history only (US). Re-poll this when /fields/profile returned status 'partial' or 'loading'")
async def field_history(req: FieldProfileRequest) -> CropHistory:
    try:
        return await build_history(req)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/profile", response_model=FieldProfile,
             summary="Phase 1: what we can see for this field (crop history, soil, climate) for the farmer to confirm")
async def field_profile(req: FieldProfileRequest) -> FieldProfile:
    try:
        return await build_profile(req)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"upstream data service failed: {e}")


@router.post("/insights", response_model=FieldInsights,
             summary="Phase 2: ranked candidate crops with planting/harvest windows, water, fertilizer, rotation effects, risks")
async def field_insights(req: FieldInsightsRequest) -> FieldInsights:
    try:
        return await build_insights(req)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except httpx.HTTPError as e:
        raise HTTPException(502, f"upstream data service failed: {e}")
