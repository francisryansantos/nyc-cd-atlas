"""
fetch_zoning_2025.py — Aggregate PLUTO 25v4 zoning district data by NYC CD.

Source: NYC Open Data dataset 64uk-42ks (MapPLUTO / PLUTO, version 25v4).
Uses the zonedist1 field (primary zoning district) for each tax lot.

Zoning categories (based on zonedist1):
  residential    — R districts  (R1-1 through R10H)
  commercial     — C districts  (C1-1 through C8-4)
  manufacturing  — M districts  (M1-1 through M3-2, incl. mixed MX zones)
  park           — PARK
  other          — BPC and other non-R/C/M special designations
  unzoned        — null zonedist1 (streets, water, unassigned lots)

For each category, outputs:
  lot_area_zoned_{cat}      — total lot area in sq ft
  lots_zoned_{cat}          — number of tax lots
  pct_lot_area_zoned_{cat}  — share of total lot area (%)

Also records the most common specific zoning district per CD
(the mode of zonedist1 by lot area within each CD).

Writes:
  data/zoning_2025_raw.csv  — one row per CD, 59 rows
"""

import sys
import requests
import pandas as pd
from pathlib import Path

PLUTO_URL = "https://data.cityofnewyork.us/resource/64uk-42ks.json"
DATA_DIR  = Path("data")

_VALID_CDS = {
    *[f"1{n:02d}" for n in range(1, 13)],
    *[f"2{n:02d}" for n in range(1, 13)],
    *[f"3{n:02d}" for n in range(1, 19)],
    *[f"4{n:02d}" for n in range(1, 15)],
    *[f"5{n:02d}" for n in range(1, 4)],
}

ZONE_CATS = ["residential", "commercial", "manufacturing", "park", "other", "unzoned"]


def categorize_zone(z) -> str:
    """Map a zonedist1 value to one of 5 zoning categories."""
    if pd.isna(z) or str(z).strip() == "":
        return "unzoned"
    z = str(z).strip().upper()
    if z == "PARK":
        return "park"
    if z.startswith("R"):
        return "residential"
    if z.startswith("C"):
        return "commercial"
    if z.startswith("M"):
        return "manufacturing"
    return "other"  # BPC and other special designations


def fetch_pluto_by_zone() -> pd.DataFrame:
    """
    Query PLUTO grouped by cd × zonedist1, returning lot area and count.
    Handles pagination — PLUTO has many unique zonedist1 × cd combinations.
    """
    print("  Fetching PLUTO lot area by cd × zonedist1 ...")
    all_rows = []
    offset = 0
    limit  = 50000

    while True:
        resp = requests.get(PLUTO_URL, params={
            "$select": "cd, zonedist1, sum(lotarea) as lot_area, count(*) as lot_count",
            "$group":  "cd, zonedist1",
            "$where":  "cd IS NOT NULL",
            "$limit":  str(limit),
            "$offset": str(offset),
        }, timeout=120)
        if resp.status_code != 200:
            sys.exit(f"PLUTO API failed ({resp.status_code}): {resp.text[:200]}")

        batch = resp.json()
        if not batch:
            break
        all_rows.extend(batch)
        print(f"    fetched {len(all_rows):,} rows so far ...")
        if len(batch) < limit:
            break
        offset += limit

    df = pd.DataFrame(all_rows)
    df = df[df["cd"].isin(_VALID_CDS)].copy()
    df["lot_area"]  = pd.to_numeric(df["lot_area"],  errors="coerce").fillna(0)
    df["lot_count"] = pd.to_numeric(df["lot_count"], errors="coerce").fillna(0)
    print(f"    {len(df):,} cd × zonedist1 combinations")
    return df


def build_zoning_table(raw: pd.DataFrame) -> pd.DataFrame:
    """Categorize, aggregate by CD, compute percentages."""
    raw = raw.copy()
    raw["zone_cat"] = raw["zonedist1"].apply(categorize_zone)

    # Aggregate lot area and count by cd × zone_cat
    agg = (
        raw.groupby(["cd", "zone_cat"], as_index=False)
        .agg(lot_area=("lot_area", "sum"), lot_count=("lot_count", "sum"))
    )

    # Pivot to wide
    area_wide  = agg.pivot(index="cd", columns="zone_cat", values="lot_area").fillna(0)
    count_wide = agg.pivot(index="cd", columns="zone_cat", values="lot_count").fillna(0)

    # Rename columns
    area_wide.columns  = [f"lot_area_zoned_{c}"  for c in area_wide.columns]
    count_wide.columns = [f"lots_zoned_{c}"       for c in count_wide.columns]

    wide = area_wide.join(count_wide).reset_index()

    # Ensure all 5 categories present
    for cat in ZONE_CATS:
        for prefix in ("lot_area_zoned_", "lots_zoned_"):
            col = f"{prefix}{cat}"
            if col not in wide.columns:
                wide[col] = 0

    # Total lot area (across all categories, same as PLUTO total_lot_area)
    area_cols = [f"lot_area_zoned_{c}" for c in ZONE_CATS]
    wide["total_lot_area_zoned"] = wide[area_cols].sum(axis=1)

    # Percentage columns
    for cat in ZONE_CATS:
        wide[f"pct_lot_area_zoned_{cat}"] = (
            wide[f"lot_area_zoned_{cat}"]
            / wide["total_lot_area_zoned"].replace(0, float("nan"))
            * 100
        ).round(4)

    # Most common specific zoning district per CD (by lot area)
    dominant = (
        raw[raw["zone_cat"] != "unzoned"]
        .sort_values("lot_area", ascending=False)
        .groupby("cd")["zonedist1"]
        .first()
        .rename("dominant_zone")
    )
    wide = wide.merge(dominant, on="cd", how="left")

    wide["borocd"] = wide["cd"].astype(int)
    wide["zoning_vintage"] = "PLUTO 25v4"
    return wide.sort_values("borocd").reset_index(drop=True)


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    print("Aggregating PLUTO 25v4 zoning data by Community District ...")

    raw   = fetch_pluto_by_zone()
    table = build_zoning_table(raw)

    area_cols = [f"lot_area_zoned_{c}"     for c in ZONE_CATS]
    pct_cols  = [f"pct_lot_area_zoned_{c}" for c in ZONE_CATS]
    lots_cols = [f"lots_zoned_{c}"         for c in ZONE_CATS]

    out_cols = (
        ["borocd"]
        + area_cols + pct_cols + lots_cols
        + ["total_lot_area_zoned", "dominant_zone", "zoning_vintage"]
    )

    out_path = DATA_DIR / "zoning_2025_raw.csv"
    table[out_cols].to_csv(out_path, index=False)

    print(f"\nSaved {len(table)} CD rows → {out_path}")
    print()
    print(
        table[["borocd"] + pct_cols + ["dominant_zone"]]
        .rename(columns={
            "pct_lot_area_zoned_residential":    "res%",
            "pct_lot_area_zoned_commercial":     "com%",
            "pct_lot_area_zoned_manufacturing":  "mfg%",
            "pct_lot_area_zoned_other":          "oth%",
            "pct_lot_area_zoned_unzoned":        "unzoned%",
        })
        .to_string(index=False)
    )
