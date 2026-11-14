# Handoff — Patato (NASA Space Apps 2026), Ethan's branch

Written 2026-11-14 ~16:35 by Ethan's agent, which ran out of budget mid-task.
Read this, then `git status` and the Agent Hub (`get_status`, messages #49, #55).

## State of the repo
- Local branch `patato-theme`, fast-forwarded to `origin/main` = `def6217`.
- **Everything below is UNCOMMITTED in the working tree. Nothing is pushed.**
- Backup of the earlier UI diff: scratchpad `patato-all.patch` (may be gone after reboot).
- Backend tests: `.venv/bin/python -m pytest -q` -> 36 passed. Vue build passed before the
  backend edits (`cd app && npm run build`); re-run it.
- Dev servers: uvicorn on 127.0.0.1:8000, Vite on [::1]:5173.

## Blockers to resolve first
1. **Commit**: the machine has no git identity and the agent's attempts to commit with
   `-c user.name/-c user.email` were denied by the permission classifier. Ethan must either
   run `git config user.name/user.email` in the repo or approve the commit.
2. **Push**: `origin` is SSH and host-key verification fails. Use HTTPS + gh credentials:
   `git push https://github.com/santiago28b/crop-rotation.git patato-theme`
   (`~/.gitconfig` already has the gh credential helper for https://github.com).
   Team convention (Santi, hub #45): work on a branch, merge to main when tested.
3. Then tell the hub it is on origin (Ethan asked that the other AIs use these changes).
4. Amelia (hub #54) is editing App.vue / FieldPicker.vue / new geolocation.js — merge carefully.

## DONE (uncommitted)
- Rename "Field Shift" -> "Patato"; russet/cream retheme (style.css); favicon
  `app/public/favicon.svg` (line-style potato, same paths as the welcome art).
- `FieldInfoPage.vue` + `api.js`: crop catalog loads independently; per-field state in a
  WeakMap survives returning to the map; `getFieldProfile()` is one call;
  `pollFieldHistory()` (abortable, 3 min budget); spinner + status chip; per-year label
  "Satellite saw <CDL label> · N% of sampled points agree"; farmer picks never overwritten.
- `/report` (app/engine.py, app/main.py): new optional `irrigation_method`
  (none|surface|sprinkler|drip, default sprinkler) and `water_source`
  (surface|groundwater|mixed, default surface) via `request_assumptions()`. Defaults are
  unchanged behaviour. Test: `test_irrigation_method_and_water_source`.
  **Santi has not acknowledged this yet (proposed in hub #55) — get his OK.**
- Insights: `Irrigation.supply` (full|limited|short) -> `_allotment_mm()` derives the
  allotment from the /report ASSUMPTIONS (one water budget for both engines).
- `/fields/profile` now returns `water_use` (OpenET via `resolve_field_water`, 20 s budget)
  with `looks_irrigated` (ET > season rain + 150 mm). Null/unavailable without
  OPENET_API_KEY. Test: `test_profile_water_use_prefill_and_shared_water_budget`.
- docs/data-sources.md: FAO citation for efficiencies (from memory — verify the reference).

## NOT DONE — the UI half (Ethan's explicit requests)
1. **FieldInfoPage.vue water card**: replace the two multi-select questions with
   - "Is this field irrigated?" Yes/No, prefilled from `profile.water_use.looks_irrigated`
     (show `water_use.note`; never overwrite an answer the farmer already gave);
   - if yes: method (Drip / Sprinkler or pivot / Flood or furrow) -> `drip|sprinkler|surface`;
   - if yes: source (Canal or river / Well / Both) -> `surface|groundwater|mixed`.
   - **Remove every "Other" option.** Emit these in `answers`.
2. **ResourcesPage.vue**: delete unused questions (equipment condition, workers, seasonal
   workers, facilities, supplies, additional resources, biggest need). Keep: current crop,
   water reliability (full/limited/short), priorities, and ONE harvest-equipment question
   mapped to real classes (`grain_combine`, `forage_harvester`, `root_harvester`; "not sure"
   -> `[]`). Today "Harvester" is sent as `['manual']`, which is wrong.
3. **Engines talking** (in `saveResources`):
   - send `resources.irrigation = { type, supply }` to `/fields/insights`;
   - append the current crop as a 2026 `source: 'farmer'` history entry for insights;
   - call insights first, then `/report` with `area_crops` = insights candidate ids that
     exist in `/crops`, plus `irrigation_method` and `water_source` (add to
     `getProfitReport` in api.js). If not irrigated send `irrigation_method: 'none'`;
   - use `Promise.allSettled` so one failure doesn't hide the other engine's result.
4. **Results**: one list per field — `report.summary` as the headline, the top-5
   `report.options` each joined by crop id with its insights candidate (fit %, planting
   window as dates, water in inches = mm/25.4, rotation flags). Show `report.region_warning`
   and `options[].data_notes` (the template wrongly reads `report.data_notes`).
5. **Mascot everywhere**: Ethan wants the line-drawn potato (paths in WelcomeScreen.vue /
   favicon.svg) as a reusable component used in loading states, status banners, empty
   states and the results headline.
6. Still-open review items: maize silently rewritten to corn_silage (FieldInfoPage
   `normalizeCropId`), stale recommendations after history edits.

## Ethan's open questions (not answered yet)
- Other NASA data worth using: SMAP soil moisture, GRACE-FO groundwater trend (well
  reliability), MODIS/VIIRS NDVI (already on the map via GIBS), GPM IMERG rainfall,
  ECOSTRESS/OpenET ET, SNOTEL/SWE already used.
- Price of water in the economics: currently not modelled. Idea: add a per-acre-foot water
  cost by source (district assessment for canal, pumping energy for wells) to
  `cost_per_acre` in /report. Needs real sourced numbers — ask Santi.

## Locks held on the hub (release when you take over)
`app/src/components/ResourcesPage.vue`, `app/engine.py`.
