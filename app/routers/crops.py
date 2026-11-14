from fastapi import APIRouter, HTTPException

from app.insights.crops import Crop, load_crops

router = APIRouter(prefix="/catalog/crops", tags=["catalog"])


@router.get("", response_model=list[Crop], summary="Master crop list (agronomic side of the contract)")
def list_crops() -> list[Crop]:
    return list(load_crops().values())


@router.get("/{crop_id}", response_model=Crop)
def get_crop(crop_id: str) -> Crop:
    crop = load_crops().get(crop_id)
    if not crop:
        raise HTTPException(404, f"unknown crop '{crop_id}'")
    return crop
