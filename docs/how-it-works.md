# How Patato decides (the algorithms, in order)

Two engines run one after the other. The **agronomy engine** answers "what can
grow on this field?". The **economics engine** answers "which of those makes the
most money, given the water risk?". The farmer's answers steer both.

```
draw field ──► /fields/profile ──► farmer confirms ──► /fields/insights ──► /report ──► top 5
               soil, climate,      history, water,      what fits here       what pays
               crop history,       current crop
               measured water use
```

## Step 1 — What we can see from space (`POST /fields/profile`)

| What | Source | How |
|---|---|---|
| Soil (texture, pH, drainage) | USDA SSURGO (US) / SoilGrids (world) | dominant soil at the field center |
| Climate, 2001-2025 | NASA POWER | daily weather at the field's grid cell; baseline 2001-12 vs recent 2013-25 shows the shift |
| Crop history, 2016-2025 | USDA Cropland Data Layer | 5 sample pixels per year, majority vote, with % agreement |
| Measured water use | OpenET (satellite ET) | Apr-Oct mean of the last 3 years; far above rainfall = "looks irrigated" |

The farmer checks all of it and corrects anything wrong. Nothing is used silently.

## Step 2 — What fits this field (`POST /fields/insights`)

For each of 29 crops:
1. **Season fit** — planting window from frost odds (safe date = 10% chance of a
   later killing frost); harvest window from growing degree days. Too short a
   season = rejected, with the reason.
2. **Water need** — FAO-56: crop coefficient x reference evapotranspiration
   (Penman-Monteith from NASA POWER), minus effective rain = irrigation need.
3. **Suitability** — FAO EcoCrop ranges for temperature, rain, soil pH, drainage.
4. **Rotation** — years since the crop (or its family) was last grown, legume
   nitrogen credit, disease-return intervals, from the confirmed history.
5. **Score** — a weighted sum using the farmer's priorities (water, soil, income, risk).

Output: ranked candidates, each with its evidence and its gaps.

## Step 3 — What pays (`POST /report`)

Only crops the agronomy engine kept are compared (sent as `area_crops`).

1. **Odds of a dry / normal / wet year.** The 25 years of NASA POWER
   growing-season rain are ranked and split into thirds. From January on, live
   Boise River snowpack (SNOTEL vs the NRCS median) shifts the odds: under 80%
   of median makes a dry year more likely.
2. **Water available** = irrigation allotment x supply level (full/limited/short)
   x dry-year delivery cut x irrigation efficiency (drip 0.90, sprinkler 0.75,
   flood 0.60) + effective rain. Wells are not cut in a dry year; canals are.
3. **Water needed** per crop: AgriMet (Parma, ID) seasonal crop water use. The
   current crop uses the field's own OpenET measurement when it is plausible.
   Outside southwest Idaho, FAO-56 needs for that location are used instead.
4. **Yield cut** (FAO-33): relative yield loss = Ky x relative water shortfall.
   Ky is the crop's sensitivity (corn 1.25 is sensitive, barley 1.0 less so).
   Extra hot days take a further small cut.
5. **Profit** = yield x price - cost, per year type. Yields and prices are the
   state's USDA NASS averages; costs come from University of Idaho budgets.
6. **Score** = expected profit - 0.5 x (expected profit - dry-year profit).
   Expected profit weights each year type by its odds. The second term
   penalizes a crop that collapses when water is short.
7. **Top 5** = the current crop plus the 4 best scores. Tags say what each is
   best at among those shown (best overall, safest in a dry year, best for soil).
8. **Summary** — two or three plain sentences built from the ranking.

Rotation rules also apply here: a crop that should not follow the current one
(shared disease, or a no-repeat crop) is excluded, with the reason.

## How a decision comes out, in one example

A corn silage field near Caldwell, ID, with a **short** water supply (live run,
2026-11-14):

- OpenET measured this field using 21.2 in per season, so that is corn's need
  (22.9 in in a hot dry year).
- In a dry year (32% odds) only 14.3 in is available: 62% of the need.
- FAO-33 with Ky 1.25: yield loss = 1.25 x 38% shortfall = about 47%. Corn
  drops to 14.4 tons/acre and loses $724/acre.
- Onions: expected profit $2,336/acre, but a dry year loses $256/acre.
  Score = 2,336 - 0.5 x (2,336 - (-256)) = **1,040**. Still the best score, but
  the risk cut it by more than half.
- Dry beans need less water (66% met in the same dry year), so they lose less
  than corn in every year type and rank above it.

That is the whole logic: water risk, priced in dollars.

## What is real and what is judgment

Real, sourced data: climate (NASA POWER), snowpack (SNOTEL), measured water use
(OpenET), crop history (USDA CDL), soil (SSURGO), yields and prices (USDA
NASS), costs (U of Idaho / OSU budgets), water needs (AgriMet, FAO-56), Ky
(FAO-33). Citations: `docs/data-sources.md`.

Judgment, stated in every response under `assumptions`: the 42 in irrigation
allotment, the dry-year delivery cut, the 0.5 risk weight, nitrogen credits,
soil scores, heat sensitivity, and how far snowpack shifts the odds.

## Outside southwest Idaho

Local everywhere: climate and rainfall (NASA POWER, global) and crop water
needs (FAO-56). Local in the US: yields and prices for the field's state, and
crops that state does not report are left out. Still Idaho numbers anywhere
else: costs per acre, the crop list and the irrigation allotment — the report
says so in `region_warning`. Outside the US there are no local prices yet.
