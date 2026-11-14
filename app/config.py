"""Paths, env vars and the few knobs the whole backend shares."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent          # repo root
APP_DATA_DIR = Path(__file__).resolve().parent / "data"  # crops.yaml etc. (committed)
CACHE_DIR = ROOT / "data" / "cache"                    # API responses (git-ignored)

load_dotenv(ROOT / ".env")

OPENET_API_KEY = os.getenv("OPENET_API_KEY")
EARTHDATA_USERNAME = os.getenv("EARTHDATA_USERNAME")
EARTHDATA_PASSWORD = os.getenv("EARTHDATA_PASSWORD")

# NASA POWER daily data starts 1981; 2001 keeps requests small and matches the existing scripts.
POWER_START_YEAR = 2001
POWER_END_YEAR = 2025            # latest full year
BASELINE_YEARS = (2001, 2012)    # "how it used to be"
RECENT_YEARS = (2013, 2025)      # "how it is now" -> the difference is the climate-change story

CDL_FIRST_YEAR = 2016            # CropScape covers CONUS from 2008, but 10 years is enough for rotation logic and 2x faster
CDL_LAST_YEAR = 2025
CDL_SAMPLE_POINTS = 5            # pixels sampled per field per year (CropScape is slow; 5 x 10 yrs = 50 requests)
OPENET_TIME_BUDGET_S = 20        # profile does not wait longer than this for measured field water use
IRRIGATED_ET_MARGIN_MM = 150     # field ET this far above growing-season rain = irrigated (soil storage can't supply that)
CDL_TIME_BUDGET_S = 45           # profile returns after this long; the fetch keeps filling the cache in the background

FROST_RISK = 0.10                # "safe" planting date = 10 % chance of a later killing frost
