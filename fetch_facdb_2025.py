"""
fetch_facdb_2025.py — Count facilities by type per NYC Community District.

Sources:
  FacDB  — NYC Open Data ji82-xba5 (Facilities Database, ~Oct 2025)
  Parks  — NYC Open Data enfh-gkve (Parks Properties, ~Mar 2026)

Fetches ALL 70 facsubgrp categories from FacDB plus the Parks Properties
count. Column names are normalized to snake_case with a count_ prefix.
Three legacy names are preserved for backward compatibility:
  count_hosp_clinic     — "HOSPITALS AND CLINICS"
  count_libraries       — "PUBLIC LIBRARIES"
  count_public_schools  — "PUBLIC K-12 SCHOOLS"

Writes:
  data/facdb_2025_raw.csv  — one row per CD, 59 rows
"""

import re
import sys
import requests
import pandas as pd
from pathlib import Path

FACDB_URL = "https://data.cityofnewyork.us/resource/ji82-xba5.json"
PARKS_URL = "https://data.cityofnewyork.us/resource/enfh-gkve.json"
DATA_DIR  = Path("data")

_VALID_CDS = {
    *[f"1{n:02d}" for n in range(1, 13)],
    *[f"2{n:02d}" for n in range(1, 13)],
    *[f"3{n:02d}" for n in range(1, 19)],
    *[f"4{n:02d}" for n in range(1, 15)],
    *[f"5{n:02d}" for n in range(1, 4)],
}

# Backward-compatible column name overrides
SUBGRP_COL_OVERRIDES = {
    "HOSPITALS AND CLINICS": "count_hosp_clinic",
    "PUBLIC LIBRARIES":      "count_libraries",
    "PUBLIC K-12 SCHOOLS":   "count_public_schools",
    # FacDB "PARKS" facsubgrp is distinct from the Parks Properties dataset
    "PARKS":                 "count_parks_facdb",
}


def subgrp_to_col(subgrp: str) -> str:
    """Normalize a FacDB facsubgrp string to a column name."""
    if subgrp in SUBGRP_COL_OVERRIDES:
        return SUBGRP_COL_OVERRIDES[subgrp]
    s = subgrp.lower()
    s = re.sub(r"\band\b|\bor\b", "", s)       # drop conjunctions
    s = re.sub(r"[^a-z0-9]+", "_", s)          # non-alphanumeric → _
    s = re.sub(r"_+", "_", s).strip("_")       # collapse / trim
    if len(s) > 50:
        s = s[:50].rstrip("_")
    return f"count_{s}"


def fetch_all_facdb_counts() -> pd.DataFrame:
    """
    GROUP BY cd × facsubgrp across all facilities.
    Returns a wide DataFrame indexed by CD string (e.g. '101').
    """
    print("  Fetching FacDB counts by facsubgrp × CD ...")
    resp = requests.get(FACDB_URL, params={
        "$select": "cd, facsubgrp, count(*) as n",
        "$group":  "cd, facsubgrp",
        "$where":  "cd IS NOT NULL AND facsubgrp IS NOT NULL",
        "$limit":  "10000",
    }, timeout=60)
    if resp.status_code != 200:
        sys.exit(f"FacDB API failed ({resp.status_code}): {resp.text[:200]}")

    df = pd.DataFrame(resp.json())
    df = df[df["cd"].isin(_VALID_CDS)].copy()
    df["n"] = pd.to_numeric(df["n"])
    df["col"] = df["facsubgrp"].map(subgrp_to_col)

    # Pivot: rows = cd, columns = col, values = n
    wide = df.pivot_table(index="cd", columns="col", values="n",
                          aggfunc="sum", fill_value=0).reset_index()
    wide.columns.name = None
    print(f"    {len(wide)} CDs × {len(wide.columns) - 1} facsubgrp columns")
    return wide


def fetch_parks_count() -> pd.Series:
    """
    Count Parks Properties per CD from the Parks Properties dataset.
    Returns a Series keyed by CD string.
    """
    print("  Fetching Parks Properties counts by CD ...")
    resp = requests.get(PARKS_URL, params={
        "$select": "communityboard, count(*) as n",
        "$group":  "communityboard",
        "$limit":  "5000",
    }, timeout=60)
    if resp.status_code != 200:
        sys.exit(f"Parks API failed ({resp.status_code}): {resp.text[:200]}")

    df = pd.DataFrame(resp.json())
    df = df[df["communityboard"].isin(_VALID_CDS)].copy()
    df["n"] = pd.to_numeric(df["n"])
    print(f"    {len(df)} CDs with park properties")
    return df.set_index("communityboard")["n"]


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    print("Counting facilities by Community District ...")

    facdb_wide = fetch_all_facdb_counts()
    parks_series = fetch_parks_count()

    # Build one row per valid CD
    cd_list = sorted(_VALID_CDS, key=lambda x: int(x))
    out = pd.DataFrame({"cd": cd_list})
    out["borocd"] = out["cd"].astype(int)

    # Merge FacDB counts
    out = out.merge(facdb_wide, on="cd", how="left")

    # Add Parks Properties count (separate from FacDB)
    out["count_parks"] = out["cd"].map(parks_series).fillna(0).astype(int)

    # Fill any missing facsubgrp columns with 0
    facdb_cols = [c for c in out.columns if c.startswith("count_")]
    for col in facdb_cols:
        out[col] = out[col].fillna(0).astype(int)

    out["facdb_vintage"] = "FacDB Oct 2025 / Parks Mar 2026"

    # Print sorted column list for reference
    print("\nFacility count columns generated:")
    for col in sorted(facdb_cols):
        total = out[col].sum()
        print(f"  {col:<55} total={total:>6,}")

    out_cols = (
        ["borocd", "count_parks"]
        + sorted([c for c in facdb_cols if c != "count_parks"])
        + ["facdb_vintage"]
    )
    out_path = DATA_DIR / "facdb_2025_raw.csv"
    out[out_cols].to_csv(out_path, index=False)
    print(f"\nSaved {len(out)} CD rows × {len(out_cols)} cols → {out_path}")
