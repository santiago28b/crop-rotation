# Backend plan — NASA-data insights (Field Shift, Space Apps 2026)

Owner: backend / data. Teammates: UI (map + field polygon + farmer inputs), economics (NPV of candidate crops).
Full reasoning and decisions: [conversation-log.md](conversation-log.md).

## Repo layout note

Santiago's water-economics engine (`app/engine.py`, `app/climate.py`, `app/geo.py`, `POST /report`, `GET /crops`) and this
NASA-data insights work (`app/insights/`, `app/sources/`, `app/routers/`, `app/fieldgeo.py`, `/fields/*`, `/catalog/crops`)
are mounted in the same `app.main:app`.

## Decisions so far

- **Global scope** from day one; the only US-only feature is *automatic* crop history (USDA CDL). Everywhere else the farmer types the history.
- **Field input = GeoJSON polygon** (a Point is accepted and buffered to ~45 m).
- **Units are metric** (mm, kg/ha, °C, day-of-year). The economics model converts if it wants acres/lbs.
- **Provider pattern**: each dataset has a US provider and a global provider chosen by whether the centroid is in CONUS.
- **No black box**: every number comes with `evidence[]` and `gaps[]` strings. Scores are weighted sums the judges can read.

## API (FastAPI, `uvicorn app.main:app --reload`, docs at `/docs`)

| Endpoint | Purpose |
|---|---|
| `POST /fields/profile` | Phase 1: crop history (US), soil, climate normals + shift 2001-12 → 2013-25. The "is this right?" screen. |
| `POST /fields/insights` | Phase 2: farmer-confirmed history + resources + priorities → ranked `CandidateCrop[]` for the economics model. |
| `GET /crops`, `GET /crops/{id}` | Master crop list (`app/data/crops.yaml`). |
| `GET /meta/sources`, `GET /health` | Provenance for judges; liveness. |

The contract types live in `app/schemas.py` (`FieldProfile`, `FieldInsights`, `CandidateCrop`).

## Data sources

| Need | US | Global | Status |
|---|---|---|---|
| Climate | NASA POWER | NASA POWER | ✅ live, cached |
| Crop history | CDL via CropScape (30 m, 2008-25, majority vote over sampled pixels) | farmer input (NDVI phenology via AppEEARS planned) | ✅ US |
| Soil | SSURGO (texture, pH, OM, AWC, drainage, slope) | SoilGrids 250 m (+ Saxton-Rawls AWC) | ✅ both |
| ETo | FAO-56 Penman-Monteith from POWER | same | ✅ |
| Field ET history | OpenET (key in hand) | MODIS MOD16A2 via AppEEARS | ⏳ |
| Groundwater trend | GRACE-FO JPL mascons → precomputed CSV | same | ⏳ |
| Soil moisture | POWER GWETROOT (MERRA-2) | SMAP via AppEEARS | ✅ baseline |

## Algorithms (all in `app/insights/`, pure functions, tested offline)

- **A. Frost-probability planting window** (`frost.py`): safe plant day = DOY where P(later frost ≤ crop kill temp) ≤ 10 %; harvest-by = DOY where P(earlier fall frost) ≤ 10 %. Per crop (kill temps differ). Shift = recent − baseline.
- **B. Harvest window** (`recommend._harvest_sdoys`): accumulate GDD from planting per year (or fixed cycle) → p10/p50/p90.
- **C. Water** (`water.py`): Kc curve × ETo climatology = crop need; USDA-SCS effective rain; irrigation need; P(cycle rain ≥ crop minimum).
- **D. EcoCrop suitability** (`suitability.py`): trapezoid envelopes for temperature (min over ~monthly means), rain, pH, drainage. Best planting date = argmax over candidate dates.
- **E. Rotation rules** (`rotation.py`): return intervals, same-family streak drag, legume/cover bonuses, N credit → `yield_modifier`.
- **F. Risks**: heat days in the sensitive stage, frost inside the cycle, drought/deficit, water security (GRACE, pending).
- **G. Score**: weighted by farmer priorities (water, soil_health, income, low_risk).
- Hemisphere-aware via a "season calendar" (sdoy 1 = Jul 1 south of the equator).

## Next steps

1. Smoke-test the three demo fields (Nampa ID; one tropical; one southern hemisphere) and freeze the contract with the economics teammate.
2. OpenET ET history (US) → add to profile; GRACE CSV → `water_security` risk.
3. AppEEARS (needs Earthdata login): MODIS NDVI phenology for non-US crop history hints, MOD16 ET.
4. Validation tab: NASA POWER vs USDA SCAN probes (RMSE, R, 95 % CI).
5. Elevation lapse-rate correction for mountainous fields (NASADEM / Open-Meteo).

## Running

```
uv venv --python 3.12 .venv && uv pip install -r requirements.txt --python .venv/bin/python
.venv/bin/uvicorn app.main:app --reload
.venv/bin/pytest -q
```
Env vars (put in a git-ignored `.env`): `OPENET_API_KEY`, `EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD` (none needed yet).
