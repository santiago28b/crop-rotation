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

## Run the app

Start the FastAPI app from the repository root:

```
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In another terminal, start the Vue app:

```
cd app
npm install
npm run dev
```

The Vite development server proxies `/api` requests to `http://localhost:8000`. Set `VITE_API_BASE_URL` when the API is hosted elsewhere. The UI uses `/fields/profile` and `/fields/history` to review the field and estimated crop history, then `/fields/insights` and `/report` for separate agronomy and profit views. The insights API uses metric units; `/report` uses acres, inches, and dollars per acre. Profit and yield inputs in the current report data are placeholders.

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

## Yields and prices by location

The engine looks up the field's state (FCC Census API, no key) and replaces the crop table's yield and price with that state's USDA NASS QuickStats averages (2020 onward) where USDA has them. Each option's `data_notes` says where its yield, price and cost came from.

```
export NASS_API_KEY=your_key          # free: https://quickstats.nass.usda.gov/api
python scripts/check_market.py ID     # shows which crops were found, and USDA's item names for any that weren't
```

Without a key the engine uses `data/crops.csv` as is. Costs per acre, crop water needs and irrigation assumptions are still southwest Idaho only; fields outside that area get a `region_warning` in the report.

## Live snowpack (SNOTEL)

With `"snowpack": "auto"` (the default), fields in the Boise area read today's snow water at 4 Boise River SNOTEL stations (Atlanta Summit, Graham Guard Station, Mores Creek Summit, Trinity Mountain) and compare it with the NRCS median for the same day (one request; the API sends the median). Under 80% → low-snow year (dry year more likely), over 120% → high. From October to December it reports "too early" and assumes normal, because NRCS starts its water supply forecasts in January and the April 1 snowpack is what sets the irrigation supply. No API key needed. The SNOTEL API randomly refuses about 1 in 4 requests, so the code retries.

```
python -m app.snowpack       # prints the current Boise basin snowpack
```

The report's `snowpack` field has the level, percent of median, a plain-English note and each station's numbers. You can still force `"low"`, `"normal"` or `"high"`, for example to demo a dry year.

## NASA-data insights API (fields → crop candidates)

Lives in `app/insights/` (algorithms), `app/sources/` (NASA POWER, SoilGrids, SSURGO, CropScape CDL), `app/routers/`
(FastAPI routes, mounted into the same `app.main:app`). Design and decisions: `docs/plan.md`, `docs/conversation-log.md`.

| Endpoint | What it does |
|---|---|
| `POST /fields/profile` | Field polygon (GeoJSON, or a Leaflet `Feature`) → crop history (US, CDL), soil, climate normals and the 2001-12 → 2013-25 shift. Shown to the farmer to confirm. |
| `POST /fields/history` | Crop history only; re-poll when `status` is `partial`/`loading` (CropScape is slow). |
| `POST /fields/insights` | Confirmed history + resources + priorities → ranked candidate crops with planting/harvest windows, water need, N credit, rotation yield modifier, risks, evidence, gaps. Input for the economics model. |
| `GET /catalog/crops` | Master crop list (`app/data/crops.yaml`, FAO EcoCrop / FAO-56 values). |
| `GET /meta/sources` | Datasets behind the numbers. |

```
uv venv --python 3.12 .venv && uv pip install -r requirements.txt --python .venv/bin/python
.venv/bin/uvicorn app.main:app --reload          # http://localhost:8000/docs
.venv/bin/pytest -q                               # offline tests (both engines)
PYTHONPATH=. .venv/bin/python scripts/smoke_test.py   # live run: Idaho, Colombia, South Africa demo fields
```
Automatic crop history is US-only (USDA CDL); elsewhere the farmer enters it. Everything else is global.
