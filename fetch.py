"""
fetch.py — Download community_district_profiles_v202402 from planninglabs.carto.com.

Writes:
  data/cd_profiles_raw.csv    — full table (210 cols, unmodified)
  data/cd_profiles_clean.csv  — 28 junk/constant columns dropped (182 cols)
  data/cd_profiles_schema.csv — column names + dtypes + null counts (for clean file)
"""

import sys
import requests
import pandas as pd
from pathlib import Path

CARTO_URL = "https://planninglabs.carto.com/api/v2/sql"
TABLE = "community_district_profiles_v202402"
DATA_DIR = Path("data")


def fetch_csv(sql: str, dest: Path, label: str) -> None:
    print(f"Fetching {label} ...")
    resp = requests.get(CARTO_URL, params={"q": sql, "format": "csv"}, stream=True)
    if resp.status_code != 200:
        print(f"ERROR {resp.status_code}:", file=sys.stderr)
        print(resp.text, file=sys.stderr)
        sys.exit(1)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("wb") as f:
        for chunk in resp.iter_content(chunk_size=65536):
            f.write(chunk)
    print(f"  Saved -> {dest}")


def build_schema_csv(raw_csv: Path, dest: Path) -> None:
    """Derive schema from the downloaded CSV rather than information_schema (which is blocked)."""
    df = pd.read_csv(raw_csv, nrows=0)  # headers only
    schema = pd.DataFrame({
        "column_name": df.columns,
        "ordinal_position": range(1, len(df.columns) + 1),
    })
    schema.to_csv(dest, index=False)
    print(f"  Schema ({len(schema)} columns) saved -> {dest}")


DROP_COLS = [
    # geometry blobs
    "the_geom", "the_geom_webmercator",
    # internal / constant
    "cartodb_id", "city",
    # UI tooltip strings
    "acs_tooltip", "acs_tooltip_2", "acs_tooltip_3",
    # empty junk columns
    "column_1656438761471", "column_1656438763135", "column_1656438763354",
]


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)

    raw_csv = DATA_DIR / "cd_profiles_raw.csv"
    fetch_csv(f"SELECT * FROM {TABLE}", raw_csv, "full table")

    df = pd.read_csv(raw_csv)

    # Drop junk + constant NYC benchmark columns
    nyc_cols = [c for c in df.columns if c.endswith("_nyc")]
    to_drop = [c for c in DROP_COLS + nyc_cols if c in df.columns]
    clean = df.drop(columns=to_drop)
    clean_csv = DATA_DIR / "cd_profiles_clean.csv"
    clean.to_csv(clean_csv, index=False)
    print(f"  Cleaned ({len(df.columns)} -> {len(clean.columns)} cols) saved -> {clean_csv}")

    # Schema based on the clean file
    schema = pd.DataFrame({
        "column_name": clean.columns,
        "pandas_dtype": [str(dt) for dt in clean.dtypes],
        "null_count": clean.isnull().sum().values,
        "ordinal_position": range(1, len(clean.columns) + 1),
    })
    schema_csv = DATA_DIR / "cd_profiles_schema.csv"
    schema.to_csv(schema_csv, index=False)
    print(f"  Schema ({len(schema)} columns) saved -> {schema_csv}")

    print("\nDone. Run explore.py to inspect the data.")
