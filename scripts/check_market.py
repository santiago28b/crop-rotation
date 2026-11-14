"""
Check which crops USDA QuickStats has yields and prices for in a state.

    export NASS_API_KEY=your_key      (free: https://quickstats.nass.usda.gov/api)
    python scripts/check_market.py ID
    python scripts/check_market.py --point 43.58 -116.56     # also tests the state lookup

For anything MISSING it prints the data item names USDA does have, so the
names in app/market.py (NASS_ITEMS) can be corrected.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.market import NASS_ITEMS, locate, pick_average, query_nass  # noqa: E402


def main():
    args = sys.argv[1:]
    if args[:1] == ["--point"]:
        place = locate(float(args[1]), float(args[2]))
        print("Location:", place)
        state = place["state"]
    else:
        state = (args[0] if args else "ID").upper()

    key = os.environ.get("NASS_API_KEY")
    if not key:
        raise SystemExit("Set NASS_API_KEY first (free key at https://quickstats.nass.usda.gov/api)")

    print(f"\nUSDA NASS QuickStats, state = {state}\n")
    for crop, spec in NASS_ITEMS.items():
        for stat in ("yield", "price"):
            if spec[stat] is None:
                print(f"  {crop:14} {stat:6} (not looked up)")
                continue
            records = query_nass(spec["commodity"], stat, state, key)
            hit = pick_average(records, spec[stat])
            if hit:
                print(f"  {crop:14} {stat:6} {hit['value']:>10}   {hit['years']}   {hit['item']}")
            else:
                print(f"  {crop:14} {stat:6} MISSING. USDA has these items instead:")
                for item in sorted({r["short_desc"] for r in records}):
                    print(f"        {item}")


if __name__ == "__main__":
    main()
