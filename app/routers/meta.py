"""Provenance endpoint: which datasets are behind the NASA-data insights (for the judges and the UI's 'about data' panel)."""

from fastapi import APIRouter

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/sources", summary="Datasets behind the insights numbers")
def sources():
    return [
        {"name": "NASA POWER", "use": "daily temperature, rain, humidity, wind, solar, soil wetness (2001-2025) -> frost windows, GDD, FAO-56 ETo",
         "coverage": "global, ~50 km grid", "auth": "none", "url": "https://power.larc.nasa.gov/"},
        {"name": "USDA NASS Cropland Data Layer (CropScape)", "use": "automatic crop history 2016-2025",
         "coverage": "continental US, 30 m", "auth": "none", "url": "https://nassgeodata.gmu.edu/CropScape/"},
        {"name": "USDA SSURGO (Soil Data Access)", "use": "soil texture, pH, OM, AWC, drainage, slope",
         "coverage": "US", "auth": "none", "url": "https://sdmdataaccess.nrcs.usda.gov/"},
        {"name": "ISRIC SoilGrids v2", "use": "soil texture, pH, SOC, bulk density -> AWC (Saxton-Rawls)",
         "coverage": "global, 250 m", "auth": "none", "url": "https://soilgrids.org/"},
        {"name": "FAO EcoCrop / FAO-56", "use": "crop climate envelopes, crop coefficients (app/data/crops.yaml)",
         "coverage": "global", "auth": "none", "url": "https://www.fao.org/land-water/databases-and-software/crop-information/"},
        {"name": "OpenET (planned)", "use": "field-level ET history", "coverage": "US", "auth": "API key"},
        {"name": "MODIS MOD13Q1 / MOD16A2 via AppEEARS (planned)", "use": "NDVI phenology, ET outside the US", "coverage": "global", "auth": "Earthdata login"},
        {"name": "GRACE-FO JPL mascons (planned)", "use": "groundwater storage trend", "coverage": "global, 0.5°", "auth": "Earthdata login"},
    ]
