"""
explore.py — Summarise community_district_profiles_v202402.

Prints:
  1. Row / column counts
  2. Columns grouped by theme (keyword matching)
  3. Dtypes and null counts per column
  4. Borough distribution from borocd
  5. Transposed sample row for Manhattan CD 9 (borocd = 109)
"""

import pandas as pd
from pathlib import Path

RAW = Path("data/cd_profiles_clean.csv")

# ---------------------------------------------------------------------------
# Theme keyword groups (matched against column names, lower-cased)
# ---------------------------------------------------------------------------
THEMES = {
    "Identity / Geography": [
        "boro", "cd", "gid", "cartodb", "the_geom", "geoid", "fips", "nta",
        "puma", "district", "name", "label",
    ],
    "Demographics": [
        "pop", "age", "race", "white", "black", "asian", "hispanic", "latino",
        "native", "pacific", "multi", "sex", "male", "female", "foreign",
        "born", "citizen", "language", "speak", "household", "hh", "family",
        "poverty", "income", "earn", "wage", "employ", "unemploy", "labor",
        "education", "school", "bachelor", "diploma", "degree", "veteran",
        "disab", "health", "insur",
    ],
    "Housing": [
        "unit", "hous", "rent", "own", "occupy", "vacan", "bedroom", "room",
        "struct", "build", "year_built", "tenure", "crowd", "afford",
        "subsid", "nycha", "hpd", "hvc",
    ],
    "Land Use / Zoning": [
        "lotarea", "bldgarea", "zonedist", "landuse", "res_far", "com_far",
        "manu", "open_space", "park", "lot", "block", "bbl", "zoning",
        "floor", "stories", "facilit",
    ],
    "Transportation": [
        "transit", "subway", "bus", "commut", "travel", "vehicle", "car",
        "bike", "walk", "drive", "parking", "mta",
    ],
    "311 / Quality of Life": [
        "311", "complaint", "noise", "heat", "rodent", "trash", "illegal",
        "request", "service",
    ],
    "Environment / Safety": [
        "flood", "storm", "tree", "green", "climate", "air", "water",
        "crime", "precinct", "arrest", "felony",
    ],
}


def group_columns(cols):
    grouped = {theme: [] for theme in THEMES}
    grouped["Other"] = []
    for col in cols:
        cl = col.lower()
        matched = False
        for theme, keywords in THEMES.items():
            if any(kw in cl for kw in keywords):
                grouped[theme].append(col)
                matched = True
                break
        if not matched:
            grouped["Other"].append(col)
    return grouped


def boro_name(borocd: int) -> str:
    prefix = borocd // 100
    return {1: "Manhattan", 2: "Bronx", 3: "Brooklyn", 4: "Queens", 5: "Staten Island"}.get(prefix, "Unknown")


def main():
    df = pd.read_csv(RAW)

    # 1. Dimensions
    print("=" * 60)
    print("1. DIMENSIONS")
    print("=" * 60)
    print(f"  Rows   : {len(df):,}")
    print(f"  Columns: {len(df.columns):,}")

    # 2. Column groupings
    print("\n" + "=" * 60)
    print("2. COLUMNS BY THEME")
    print("=" * 60)
    grouped = group_columns(df.columns)
    for theme, cols in grouped.items():
        if cols:
            print(f"\n  [{theme}]  ({len(cols)} columns)")
            for c in cols:
                print(f"    {c}")

    # 3. Dtypes and null counts
    print("\n" + "=" * 60)
    print("3. DTYPES & NULL COUNTS")
    print("=" * 60)
    stats = pd.DataFrame({
        "dtype": df.dtypes,
        "nulls": df.isnull().sum(),
        "pct_null": (df.isnull().mean() * 100).round(1),
    })
    # Only show columns that have nulls or are non-numeric for brevity
    print(stats.to_string())

    # 4. Borough distribution
    print("\n" + "=" * 60)
    print("4. BOROUGH DISTRIBUTION (borocd)")
    print("=" * 60)
    id_col = None
    for candidate in ["borocd", "cd", "borocode"]:
        if candidate in df.columns:
            id_col = candidate
            break

    if id_col is None:
        print("  Could not find borocd / cd column — showing first 10 rows of index:")
        print(df.index[:10])
    else:
        df["_boro"] = df[id_col].apply(boro_name)
        dist = df.groupby("_boro")[id_col].count().rename("# CDs")
        print(f"\n  CD identifier column: '{id_col}'")
        print(f"  Total CDs: {len(df)}")
        print()
        print(dist.to_string())
        df.drop(columns=["_boro"], inplace=True)

    # 5. Sample row: Manhattan CD 9 (borocd = 109)
    print("\n" + "=" * 60)
    print("5. SAMPLE ROW — Manhattan CD 9 (borocd = 109)")
    print("=" * 60)
    if id_col and id_col in df.columns:
        row = df[df[id_col] == 109]
        if row.empty:
            print("  borocd 109 not found.")
        else:
            transposed = row.T.rename(columns={row.index[0]: "value"})
            pd.set_option("display.max_rows", 300)
            pd.set_option("display.max_colwidth", 80)
            print(transposed.to_string())
    else:
        print("  Cannot locate borocd column.")


if __name__ == "__main__":
    main()
