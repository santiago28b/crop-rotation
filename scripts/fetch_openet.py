"""
Download monthly crop water use (ET = evapotranspiration) from OpenET for a field.

ET = water that leaves the field through the plants + soil. For irrigated farms
in Idaho this is basically "how much water the crop actually used".

1. Make a free account at https://account.etdata.org and create an API key.
2. Put it in a .env file or your shell:  export OPENET_API_KEY=your_key
3. Run:
    python scripts/fetch_openet.py                          # default: Nampa, ID
    python scripts/fetch_openet.py --lat 43.6 --lon -116.4 --name meridian

Docs: https://openet.gitbook.io/docs/reference/api-reference/raster
"""

import argparse
import os
from pathlib import Path

import pandas as pd
import requests

API_URL = "https://openet-api.org/raster/timeseries/point"


def fetch_openet(lat, lon, start, end, variable="ET", api_key=None):
    body = {
        "date_range": [start, end],
        "interval": "monthly",
        "geometry": [lon, lat],          # OpenET wants [longitude, latitude]
        "model": "Ensemble",             # average of 6 satellite models
        "variable": variable,            # "ET" (actual) or "ETo" (reference / max demand)
        "reference_et": "gridMET",
        "units": "mm",
        "file_format": "JSON",
    }
    resp = requests.post(API_URL, json=body, headers={"Authorization": api_key}, timeout=120)
    if resp.status_code != 200:
        raise SystemExit(f"OpenET error {resp.status_code}: {resp.text[:300]}")

    df = pd.DataFrame(resp.json())
    # first column is the date, second is the value (names can vary a bit)
    df.columns = ["date", variable.lower()] + list(df.columns[2:])
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date")


def main():
    parser = argparse.ArgumentParser(description="Download OpenET monthly ET")
    parser.add_argument("--lat", type=float, default=43.58)   # Nampa, ID
    parser.add_argument("--lon", type=float, default=-116.56)
    parser.add_argument("--name", default="nampa")
    parser.add_argument("--start", default="2016-01-01")
    parser.add_argument("--end", default="2025-12-31")
    args = parser.parse_args()

    api_key = os.environ.get("OPENET_API_KEY")
    if not api_key:
        raise SystemExit("Set OPENET_API_KEY first (free key at https://account.etdata.org)")

    et = fetch_openet(args.lat, args.lon, args.start, args.end, "ET", api_key)
    eto = fetch_openet(args.lat, args.lon, args.start, args.end, "ETo", api_key)
    df = et.join(eto, how="outer")

    out_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"openet_{args.name}_{args.start[:4]}_{args.end[:4]}.csv"
    df.to_csv(out_file)

    print(f"Saved {len(df)} months to {out_file}")
    yearly = df.groupby(df.index.year).sum(numeric_only=True).round(0)
    print("\nYearly totals (mm):")
    print(yearly)


if __name__ == "__main__":
    main()
