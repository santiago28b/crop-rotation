# Where the crop table numbers come from (data/crops.csv)

Updated 2026-11-14 for the Space Apps submission. Southwest Idaho (Treasure Valley) only.

## water_need_in — seasonal crop water use, inches
USBR **AgriMet**, Parma ID station (PMAI, in the Treasure Valley), seasonal
crop evapotranspiration totals, long-term average 1988-2015.
https://www.usbr.gov/pn/agrimet/ETtotals.html
Alfalfa 39.8 | field corn 25.8 (used for silage) | winter grain 23.4 |
spring grain 25.0 | sugar beets 32.2 | onions 27.6 | dry beans 20.0 |
potatoes 26.1 | peppermint 25.4.
At run time the CURRENT crop's value is replaced by OpenET measured ET for
the farmer's own field when plausible (see README).

## ky — FAO-33 yield response factor
FAO Irrigation & Drainage Paper 33 (Doorenbos & Kassam), standard published
values: alfalfa 1.1, maize 1.25, wheat/barley 1.0, sugar beet 1.0, onion 1.1,
beans 1.15, potato 1.1. Mint is not in FAO-33: 1.1 is our assumption.

## cost_per_acre — University of Idaho / OSU enterprise budgets (total cost per acre)
U of I Idaho AgBiz crop budgets, https://www.uidaho.edu/extension/food/idaho-agbiz/crop-budgets
- Alfalfa hay, SW Idaho 2019: $980.00
- Corn silage, SC Idaho 2019: $1,227.64 (also source of the $35/ton silage price)
- Winter wheat (soft white), SW Idaho 2019: $817.83
- Feed barley, SC Idaho 2019: $767.20
- Sugar beets, SW Idaho 2022: $2,042.73
- Dry (pinto) beans, SC Idaho 2019: $913.90
- Potatoes (Russet Burbank, fumigation), SW Idaho 2019: $3,730.01
- Peppermint (fumigation), SW Idaho 2013: $2,522.05 — OLD, flagged in csv
- Onions: OSU Extension, "Cost of onion production in eastern Oregon and
  Idaho" (2021 season), Idaho field-run WITH storage, no packing:
  $5,806.76/acre — storage cost included because USDA's price received
  reflects storage-season sales.
  https://extension.oregonstate.edu/catalog/cost-onion-production-eastern-oregon-idaho
Years differ by budget (2013-2022, nominal dollars, not inflation-adjusted).

## yield_per_acre and price_per_unit — USDA NASS QuickStats
Idaho state averages 2020-2025/26 (survey), fetched live by the engine when
NASS_API_KEY is set; the CSV holds the same averages so the no-key mode is
also real. Exception: USDA publishes no corn-silage price; the UI 2019
budget's $35/ton is used.

## Still judgment, not measured sources
frost_free_days_needed, heat_sensitivity, soil_score, rotation rules
(avoid_after, no_repeat), and the irrigation assumptions at the top of
app/engine.py (full allotment, efficiency, dry-year cuts).
