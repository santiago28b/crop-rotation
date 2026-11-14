"""
Download daily NASA POWER data for a farm location and save it as a CSV.

NASA POWER = free NASA weather/climate data for any lat/lon, no login needed.
Docs: https://power.larc.nasa.gov/docs/services/api/temporal/daily/

Usage:
    python scripts/fetch_power.py                       # default: Nampa, ID (Treasure Valley farmland)
    python scripts/fetch_power.py --lat 43.6 --lon -116.2 --name boise
    python scripts/fetch_power.py --start 2001 --end 2025
"""

import argparse
from pathlib import Path

import pandas as pd
import requests

API_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"

# What each parameter means (all from NASA POWER, "AG" community units)
PARAMETERS = {
    "T2M": "avg air temp (C)",
    "T2M_MAX": "max air temp (C)",
    "T2M_MIN": "min air temp (C)",
    "PRECTOTCORR": "precipitation (mm/day)",
    "RH2M": "relative humidity (%)",
    "WS2M": "wind speed at 2m (m/s)",
    "ALLSKY_SFC_SW_DWN": "sunlight / solar radiation (MJ/m^2/day)",
    "GWETTOP": "surface soil wetness (0-1)",
    "GWETROOT": "root-zone soil wetness (0-1)",
}

FILL_VALUE = -999  # NASA uses this for "no data"


def fetch_power(lat: float, lon: float, start_year: int, end_year: int) -> pd.DataFrame:
    params = {
        "parameters": ",".join(PARAMETERS),
        "community": "AG",
        "latitude": lat,
        "longitude": lon,
        "start": f"{start_year}0101",
        "end": f"{end_year}1231",
        "format": "JSON",
    }
    print(f"Requesting NASA POWER data for ({lat}, {lon}) {start_year}-{end_year} ...")
    resp = requests.get(API_URL, params=params, timeout=120)
    resp.raise_for_status()
    data = resp.json()

    # Shape: data["properties"]["parameter"]["T2M"] = {"20240101": 1.2, ...}
    raw = data["properties"]["parameter"]
    df = pd.DataFrame(raw)
    df.index = pd.to_datetime(df.index, format="%Y%m%d")
    df.index.name = "date"
    df = df.astype(float).replace(FILL_VALUE, float("nan"))
    return df


def main():
    parser = argparse.ArgumentParser(description="Download NASA POWER daily data")
    parser.add_argument("--lat", type=float, default=43.58)    # Nampa, ID
    parser.add_argument("--lon", type=float, default=-116.56)
    parser.add_argument("--name", default="nampa")
    parser.add_argument("--start", type=int, default=2001)
    parser.add_argument("--end", type=int, default=2025)
    args = parser.parse_args()

    df = fetch_power(args.lat, args.lon, args.start, args.end)

    out_dir = Path(__file__).resolve().parent.parent / "data" / "raw"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"power_{args.name}_{args.start}_{args.end}.csv"
    df.to_csv(out_file)

    print(f"Saved {len(df)} days to {out_file}")
    print(df.tail())


if __name__ == "__main__":
    main()
