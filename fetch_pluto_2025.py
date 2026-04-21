"""
fetch_pluto_2025.py — Aggregate PLUTO 25v4 land-use data by NYC Community District.

Source: NYC Open Data dataset 64uk-42ks (MapPLUTO / PLUTO, version 25v4).

Land-use code → column-name mapping matches the DCP cd_profiles_v202402 convention:
  1  → res_1_2_family_bldg
  2  → res_multifamily_walkup
  3  → res_multifamily_elevator
  4  → mixed_use
  5  → commercial_office
  6  → industrial_manufacturing
  7  → transportation_utility
  8  → public_facility_institution
  9  → open_space
  10 → parking
  11 → vacant
  null/other → other_no_data

Writes:
  data/pluto_2025_raw.csv  — one row per CD, 59 rows
"""

import sys
import requests
import pandas as pd
from pathlib import Path

SOCRATA_URL = "https://data.cityofnewyork.us/resource/64uk-42ks.json"
DATA_DIR = Path("data")

# All 59 valid NYC borocd values (as strings matching the PLUTO cd field)
_VALID_CDS = {
    *[f"1{n:02d}" for n in range(1, 13)],   # Manhattan 101-112
    *[f"2{n:02d}" for n in range(1, 13)],   # Bronx 201-212
    *[f"3{n:02d}" for n in range(1, 19)],   # Brooklyn 301-318
    *[f"4{n:02d}" for n in range(1, 15)],   # Queens 401-414
    *[f"5{n:02d}" for n in range(1, 4)],    # Staten Island 501-503
}

# PLUTO land-use code → column-name suffix
LANDUSE_MAP = {
    "1":  "res_1_2_family_bldg",
    "2":  "res_multifamily_walkup",
    "3":  "res_multifamily_elevator",
    "4":  "mixed_use",
    "5":  "commercial_office",
    "6":  "industrial_manufacturing",
    "7":  "transportation_utility",
    "8":  "public_facility_institution",
    "9":  "open_space",
    "10": "parking",
    "11": "vacant",
}
LANDUSE_SUFFIX_ORDER = list(LANDUSE_MAP.values()) + ["other_no_data"]


def socrata_get(params: dict, label: str) -> list[dict]:
    """Single Socrata request with error handling."""
    print(f"  Fetching {label} ...")
    resp = requests.get(SOCRATA_URL, params=params, timeout=120)
    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        sys.exit(1)
    return resp.json()


def fetch_by_landuse() -> pd.DataFrame:
    """GROUP BY cd × landuse → lot count + lot area sum."""
    rows = socrata_get({
        "$select": "cd, landuse, count(*) as lot_count, sum(lotarea) as lot_area",
        "$group":  "cd, landuse",
        "$limit":  "10000",
    }, "land-use counts and areas (GROUP BY cd × landuse)")

    df = pd.DataFrame(rows)
    df = df[df["cd"].isin(_VALID_CDS)].copy()
    df["lot_count"] = pd.to_numeric(df["lot_count"])
    df["lot_area"]  = pd.to_numeric(df["lot_area"])
    df["landuse"]   = df["landuse"].fillna("null")   # null → "other_no_data" bucket
    return df


def fetch_totals() -> pd.DataFrame:
    """GROUP BY cd → total buildings + total residential units."""
    rows = socrata_get({
        "$select": "cd, sum(numbldgs) as tot_bldgs, sum(unitsres) as tot_resunits",
        "$group":  "cd",
        "$limit":  "5000",
    }, "building + residential unit totals (GROUP BY cd)")

    df = pd.DataFrame(rows)
    df = df[df["cd"].isin(_VALID_CDS)].copy()
    df["tot_bldgs"]    = pd.to_numeric(df["tot_bldgs"])
    df["tot_resunits"] = pd.to_numeric(df["tot_resunits"])
    return df


def pivot_landuse(lu_df: pd.DataFrame) -> pd.DataFrame:
    """Pivot long land-use table → wide CD table."""
    # Map landuse codes to suffix names; null → other_no_data
    lu_df = lu_df.copy()
    lu_df["lu_name"] = lu_df["landuse"].map(LANDUSE_MAP).fillna("other_no_data")

    # For rows with the same (cd, lu_name) — e.g. multiple null landuse codes —
    # aggregate again.
    agg = lu_df.groupby(["cd", "lu_name"], as_index=False).agg(
        lot_count=("lot_count", "sum"),
        lot_area=("lot_area", "sum"),
    )

    # Pivot to wide
    lots = agg.pivot(index="cd", columns="lu_name", values="lot_count").reset_index()
    area = agg.pivot(index="cd", columns="lu_name", values="lot_area").reset_index()

    wide = lots.merge(area, on="cd", suffixes=("_lots", "_area"))

    # Rename with explicit prefixes
    for suffix in LANDUSE_SUFFIX_ORDER:
        lots_col = f"{suffix}_lots"
        area_col = f"{suffix}_area"
        if lots_col in wide.columns:
            wide = wide.rename(columns={
                lots_col: f"lots_{suffix}",
                area_col: f"lot_area_{suffix}",
            })
        else:
            # Landuse type absent in this CD — fill with 0
            wide[f"lots_{suffix}"] = 0
            wide[f"lot_area_{suffix}"] = 0

    return wide


def build_cd_table(wide: pd.DataFrame, totals: pd.DataFrame) -> pd.DataFrame:
    df = wide.merge(totals, on="cd")

    # Derived: total lot area and lot count
    lot_area_cols = [f"lot_area_{s}" for s in LANDUSE_SUFFIX_ORDER]
    lots_cols     = [f"lots_{s}"     for s in LANDUSE_SUFFIX_ORDER]

    for col in lot_area_cols + lots_cols:
        df[col] = df[col].fillna(0)

    df["total_lot_area"] = df[lot_area_cols].sum(axis=1)
    df["lots_total"]     = df[lots_cols].sum(axis=1)

    # pct columns
    for suffix in LANDUSE_SUFFIX_ORDER:
        df[f"pct_lot_area_{suffix}"] = (
            df[f"lot_area_{suffix}"] / df["total_lot_area"] * 100
        ).round(4)

    df["borocd"]         = df["cd"].astype(int)
    df["cd_tot_bldgs"]   = df["tot_bldgs"]
    df["cd_tot_resunits"] = df["tot_resunits"]
    df["pluto_vintage"]  = "25v4"

    return df.sort_values("borocd").reset_index(drop=True)


# Ordered output columns (matching cd_profiles_clean.csv names)
OUTPUT_COLS = (
    ["borocd"]
    + [f"lot_area_{s}"     for s in LANDUSE_SUFFIX_ORDER]
    + [f"pct_lot_area_{s}" for s in LANDUSE_SUFFIX_ORDER]
    + ["total_lot_area"]
    + [f"lots_{s}"         for s in LANDUSE_SUFFIX_ORDER]
    + ["lots_total", "cd_tot_bldgs", "cd_tot_resunits", "pluto_vintage"]
)


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    print("Aggregating PLUTO 25v4 land-use data by Community District ...")

    lu_df   = fetch_by_landuse()
    totals  = fetch_totals()
    wide    = pivot_landuse(lu_df)
    cd_tbl  = build_cd_table(wide, totals)

    missing = _VALID_CDS - set(cd_tbl["cd"] if "cd" in cd_tbl.columns else
                                cd_tbl["borocd"].astype(str))
    if missing:
        print(f"  Warning: {len(missing)} CDs missing from PLUTO: {sorted(missing)}",
              file=sys.stderr)

    out = DATA_DIR / "pluto_2025_raw.csv"
    cd_tbl[OUTPUT_COLS].to_csv(out, index=False)

    print(f"\nSaved {len(cd_tbl)} CD rows → {out}")
    print(f"  Columns: {len(OUTPUT_COLS)}")
    print()
    # Quick sanity check
    print(cd_tbl[["borocd", "total_lot_area", "lots_total",
                   "cd_tot_bldgs", "cd_tot_resunits"]].to_string(index=False))
