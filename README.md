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

## Recommendation engine

```
python -m app.engine            # demo report for a field near Nampa
python tests/test_engine.py     # tests
uvicorn app.main:app --reload   # API at http://localhost:8000/docs
```

`POST /report`

```json
{
  "field": { "type": "Polygon", "coordinates": [[[-116.565, 43.58], [-116.559, 43.58], [-116.559, 43.585], [-116.565, 43.585]]] },
  "current_crop": "corn_silage",
  "water_supply": "limited",
  "area_crops": [{ "crop": "alfalfa", "share": 0.35 }],
  "snowpack": "normal"
}
```

Returns `options` (current crop first, then ranked), each with expected and dry-year profit per acre and for the field, water needed vs. available per year type, `why` and `risks`.

**Climate:** fetched from NASA POWER for each field's own location (snapped to NASA's ~0.5° grid) and cached in `data/cache/`. The first request for an area takes a few seconds; after that it's instant. If NASA can't be reached, the engine uses placeholder climate and says so in the report.

**Placeholders to replace:** every number in `data/crops.csv` (marked `source = placeholder`) and the water assumptions at the top of `app/engine.py`.
