# crop-rotation

NASA Space Apps Challenge 2026 — **Field Shift: Adapting Farms with NASA Data**

A decision-support tool that helps farmers in Idaho's Treasure Valley (Boise area) compare crop rotations using NASA Earth data. Main focus: **water availability** — the #1 concern a local farmer told us about — plus soil health.

## Idea

1. Pick a field location.
2. Pick the current rotation (for example potatoes → wheat → sugar beets).
3. The app pulls NASA climate and soil data for that spot.
4. It compares 3 rotations (current + 2 others) and explains why, the benefits, and the risks.

This tool supports farmers — it does not replace their judgment or local experts.

## Data sources

| Source | What we use it for |
|---|---|
| NASA POWER | Temperature, rain, frost, heat stress |
| OpenET | Crop water use (evapotranspiration) |
| GRACE / GRACE-FO | Long-term groundwater / water storage trends |
| USGS NWIS | Boise River streamflow and groundwater levels |
| SMAP (via AppEEARS) | Soil moisture trends |
| USDA SSURGO | Soil type |
| CropScape (USDA CDL) | Past crops planted on a field |
| MODIS NDVI (via AppEEARS) | Plant health over time |

## Project structure

```
data/        raw and processed data (not committed)
scripts/     data download / processing scripts
app/         the web app
docs/        notes and write-up
```

## Team

byutv — Girard, OH local event

## Quick start

```
pip install -r requirements.txt
python scripts/fetch_power.py                 # downloads 2001-2025 daily NASA POWER data for Nampa, ID
python scripts/summarize_power.py data/raw/power_nampa_2001_2025.csv
```

OpenET (crop water use) — needs a free API key from https://account.etdata.org:

```
export OPENET_API_KEY=your_key
python scripts/fetch_openet.py
```

Output: yearly water / heat / frost / soil-moisture facts in `data/processed/`, with each year labeled dry, normal or wet.
