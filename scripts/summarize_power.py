"""
Turn daily NASA POWER data into simple farm facts per year:
water, heat, frost, and soil moisture. This is what the rotation scoring will use.

Usage:
    python scripts/summarize_power.py data/raw/power_nampa_2001_2025.csv
"""

import argparse
import json
from pathlib import Path

import pandas as pd

GROWING_MONTHS = [4, 5, 6, 7, 8, 9]  # April - September
HOT_DAY_C = 35   # ~95F, crops get heat stressed
FROST_C = 0      # min temp at/below freezing
GDD_BASE_C = 10  # growing degree days base (corn-style)


def yearly_summary(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["year"] = df.index.year
    df["month"] = df.index.month
    df["doy"] = df.index.dayofyear
    df["gdd"] = ((df["T2M_MAX"] + df["T2M_MIN"]) / 2 - GDD_BASE_C).clip(lower=0)

    rows = []
    for year, d in df.groupby("year"):
        season = d[d["month"].isin(GROWING_MONTHS)]
        frost = d[d["T2M_MIN"] <= FROST_C]
        spring_frost = frost[frost["doy"] < 182]["doy"]
        fall_frost = frost[frost["doy"] >= 182]["doy"]

        rows.append({
            "year": year,
            "precip_year_mm": round(d["PRECTOTCORR"].sum(), 1),
            "precip_season_mm": round(season["PRECTOTCORR"].sum(), 1),
            "hot_days": int((season["T2M_MAX"] >= HOT_DAY_C).sum()),
            "gdd_season": round(season["gdd"].sum(), 0),
            "last_spring_frost_doy": int(spring_frost.max()) if len(spring_frost) else None,
            "first_fall_frost_doy": int(fall_frost.min()) if len(fall_frost) else None,
            "root_soil_wetness_summer": round(season[season["month"].isin([7, 8])]["GWETROOT"].mean(), 3),
        })

    out = pd.DataFrame(rows).set_index("year")
    out["frost_free_days"] = out["first_fall_frost_doy"] - out["last_spring_frost_doy"]

    # Label each year dry / normal / wet by growing-season rain (lowest third = dry)
    low, high = out["precip_season_mm"].quantile([1 / 3, 2 / 3])
    out["year_type"] = out["precip_season_mm"].apply(
        lambda p: "dry" if p <= low else ("wet" if p >= high else "normal")
    )
    return out


def overall(summary: pd.DataFrame) -> dict:
    by_type = summary.groupby("year_type").mean(numeric_only=True).round(1)
    return {
        "years": f"{summary.index.min()}-{summary.index.max()}",
        "avg_precip_year_mm": round(summary["precip_year_mm"].mean(), 1),
        "avg_precip_season_mm": round(summary["precip_season_mm"].mean(), 1),
        "avg_hot_days": round(summary["hot_days"].mean(), 1),
        "avg_frost_free_days": round(summary["frost_free_days"].mean(), 1),
        "avg_gdd_season": round(summary["gdd_season"].mean(), 0),
        "dry_years": summary.index[summary["year_type"] == "dry"].tolist(),
        "by_year_type": by_type.to_dict(orient="index"),
        # simple trend: is the season getting hotter / drier? (per decade)
        "trend_hot_days_per_decade": round(_slope(summary["hot_days"]) * 10, 2),
        "trend_season_precip_mm_per_decade": round(_slope(summary["precip_season_mm"]) * 10, 1),
    }


def _slope(series: pd.Series) -> float:
    s = series.dropna()
    x = s.index.to_series().astype(float)
    x = x - x.mean()
    return float((x * (s - s.mean())).sum() / (x ** 2).sum())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csv", help="CSV from fetch_power.py")
    args = parser.parse_args()

    df = pd.read_csv(args.csv, index_col="date", parse_dates=True)
    summary = yearly_summary(df)
    stats = overall(summary)

    out_dir = Path(__file__).resolve().parent.parent / "data" / "processed"
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.csv).stem
    summary.to_csv(out_dir / f"{stem}_yearly.csv")
    (out_dir / f"{stem}_summary.json").write_text(json.dumps(stats, indent=2, default=str))

    print(summary)
    print(json.dumps(stats, indent=2, default=str))


if __name__ == "__main__":
    main()
