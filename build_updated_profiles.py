"""
build_updated_profiles.py — Assemble the updated NYC Community District Profiles.

Takes the original cd_profiles_clean.csv as a base (to preserve column structure
and all non-updated fields) and overlays:

  ACS 2020-2024       (fetch_acs_2024_tracts.py) → ACS demographic columns
  PLUTO 25v4          (fetch_pluto_2025.py)       → land-use columns
  FacDB Oct 2025      (fetch_facdb_2025.py)       → all 70 facility categories
  NYPD 2024           (fetch_nypd_2024.py)        → crime columns
  Zoning 2025         (fetch_zoning_2025.py)      → zoning district columns (new)

Columns NOT updated (kept from v202402 original):
  • pop_2000 / pop_2010 / pop_change_00_10 — Decennial Census 2010 (spatial)
  • fp_* (floodplain) — still 2007 FEMA FIRMs (spatial)
  • pct_clean_strts — DSNY scorecard suspended FY2023
  • *_boro benchmarks — borough-level ACS (not re-fetched)
  • son_issue_* — Community Board Needs (PDF only)
  • Geography/admin fields — unchanged

Writes:
  data/cd_profiles_updated.csv  — original columns + new facility/zoning columns
"""

import sys
import pandas as pd
from pathlib import Path

DATA_DIR = Path("data")

# ── Load all source files ─────────────────────────────────────────────────────

def require(path: Path) -> pd.DataFrame:
    if not path.exists():
        sys.exit(
            f"\nMissing: {path}\n"
            "Run the corresponding fetch_*.py script first."
        )
    return pd.read_csv(path)


print("Loading source files ...")
orig   = require(DATA_DIR / "cd_profiles_clean.csv")
acs    = require(DATA_DIR / "acs_2024_raw.csv")
pluto  = require(DATA_DIR / "pluto_2025_raw.csv")
facdb  = require(DATA_DIR / "facdb_2025_raw.csv")
nypd   = require(DATA_DIR / "nypd_2024_raw.csv")
zoning = require(DATA_DIR / "zoning_2025_raw.csv")
income = require(DATA_DIR / "acs_2024_income.csv")
print(f"  orig  : {orig.shape[0]} rows × {orig.shape[1]} cols")
print(f"  acs   : {acs.shape[0]} rows  |  pluto:  {pluto.shape[0]} rows")
print(f"  facdb : {facdb.shape[0]} rows  |  nypd:   {nypd.shape[0]} rows")
print(f"  zoning: {zoning.shape[0]} rows  |  income: {income.shape[0]} rows")

# ── Index all update sources on borocd ───────────────────────────────────────
acs_idx    = acs.set_index("borocd")
pluto_idx  = pluto.set_index("borocd")
facdb_idx  = facdb.set_index("borocd")
nypd_idx   = nypd.set_index("borocd")
zoning_idx = zoning.set_index("borocd")
income_idx = income.set_index("borocd")

# ── Start from original; overlay updated columns ──────────────────────────────
df = orig.copy()

def overlay(source_idx: pd.DataFrame, cols: list[str]) -> None:
    """Replace columns in df with values from source_idx (keyed on borocd)."""
    for col in cols:
        if col not in source_idx.columns:
            print(f"  Warning: '{col}' not found in update source", flush=True)
            continue
        df[col] = df["borocd"].map(source_idx[col])


# ── ACS 2020-2024 ─────────────────────────────────────────────────────────────
print("\nOverlaying ACS 2020-2024 ...")

ACS_SCALAR_COLS = [
    "pop_acs",
    "pct_hispanic", "pct_white_nh", "pct_black_nh", "pct_asian_nh", "pct_other_nh",
    "pct_foreign_born", "moe_foreign_born",
    "unemployment", "moe_unemployment",
    "pct_hh_rent_burd", "moe_hh_rent_burd",
    "mean_commute", "moe_mean_commute",
    "poverty_rate", "moe_poverty_rate",
    "pct_bach_deg", "moe_bach_deg",
    "lep_rate", "moe_lep_rate",
    "under18_rate", "moe_under18_rate",
    "over65_rate", "moe_over65_rate",
]

_AGE_BINS = [
    "under_5", "5_9", "10_14", "15_19", "20_24",
    "25_29", "30_34", "35_39", "40_44", "45_49",
    "50_54", "55_59", "60_64", "65_69", "70_74",
    "75_79", "80_84", "85_over",
]
AGE_COLS = (
    [f"male_{b}"   for b in _AGE_BINS]
    + [f"female_{b}" for b in _AGE_BINS]
)

overlay(acs_idx, ACS_SCALAR_COLS + AGE_COLS)

# Update PUMA code column (now 2020-vintage 5-digit codes)
df["puma"]        = df["borocd"].map(acs_idx["puma_code"])
df["shared_puma"] = df["borocd"].map(acs_idx["shared_puma"])

# Compute shared_puma_cd (the partner CD, if any)
puma_to_cds: dict[str, list[int]] = {}
for _, row in acs.iterrows():
    puma_to_cds.setdefault(row["puma_code"], []).append(int(row["borocd"]))

def partner_cd(borocd: int, puma_code: str) -> str:
    cds = puma_to_cds.get(puma_code, [])
    partners = [c for c in cds if c != borocd]
    return str(partners[0]) if partners else ""

df["shared_puma_cd"] = [
    partner_cd(int(bc), pc)
    for bc, pc in zip(df["borocd"], df["puma"])
]

print(f"  {len(ACS_SCALAR_COLS) + len(AGE_COLS)} ACS columns updated")

# ── PLUTO 25v4 ────────────────────────────────────────────────────────────────
print("Overlaying PLUTO 25v4 ...")

_LU_SUFFIXES = [
    "res_1_2_family_bldg", "res_multifamily_walkup", "res_multifamily_elevator",
    "mixed_use", "commercial_office", "industrial_manufacturing",
    "transportation_utility", "public_facility_institution",
    "open_space", "parking", "vacant", "other_no_data",
]
PLUTO_COLS = (
    [f"lot_area_{s}"     for s in _LU_SUFFIXES]
    + [f"pct_lot_area_{s}" for s in _LU_SUFFIXES]
    + ["total_lot_area"]
    + [f"lots_{s}"         for s in _LU_SUFFIXES]
    + ["lots_total", "cd_tot_bldgs", "cd_tot_resunits"]
)
overlay(pluto_idx, PLUTO_COLS)
print(f"  {len(PLUTO_COLS)} PLUTO columns updated")

# ── FacDB Oct 2025 / Parks Mar 2026 ──────────────────────────────────────────
print("Overlaying FacDB + Parks counts ...")

# All count_* columns in the facdb file (includes legacy 4 + all 70 facsubgrp)
FACDB_COLS = [c for c in facdb_idx.columns if c.startswith("count_")]
overlay(facdb_idx, FACDB_COLS)
print(f"  {len(FACDB_COLS)} FacDB/Parks columns updated")

# ── Zoning 2025 (new columns — not in original schema) ───────────────────────
print("Overlaying zoning district data ...")

_ZONE_CATS = ["residential", "commercial", "manufacturing", "park", "other", "unzoned"]
ZONING_COLS = (
    [f"lot_area_zoned_{c}"     for c in _ZONE_CATS]
    + [f"pct_lot_area_zoned_{c}" for c in _ZONE_CATS]
    + [f"lots_zoned_{c}"         for c in _ZONE_CATS]
    + ["total_lot_area_zoned", "dominant_zone"]
)
overlay(zoning_idx, ZONING_COLS)
print(f"  {len(ZONING_COLS)} zoning columns added")

# ── NYPD 2024 ─────────────────────────────────────────────────────────────────
print("Overlaying NYPD 2024 crime counts ...")

NYPD_COLS = ["crime_count", "crime_per_1000"]
overlay(nypd_idx, NYPD_COLS)
print(f"  {len(NYPD_COLS)} NYPD columns updated")

# ── Median household income (ACS 2020-2024) ───────────────────────────────────
print("Overlaying median household income ...")

INCOME_COLS = [
    "mdn_hh_inc_puma", "mdn_hh_inc_puma_moe",
    "mdn_hh_inc_interp",
    "total_households", "median_bracket",
]
overlay(income_idx, INCOME_COLS)
print(f"  {len(INCOME_COLS)} income columns added")

# ── Version tags ──────────────────────────────────────────────────────────────
df["v_acs"]       = "ACS 2020-2024"
df["v_pluto"]     = "25v4"
df["v_facdb"]     = "FacDB Oct 2025"
df["v_crime"]     = "NYPD 2024"
df["v_parks"]     = "Parks Mar 2026"
df["v_poverty"]   = "ACS 2020-2024"
df["v_income"]    = "ACS 2020-2024 (B19001 interpolated)"
# Keep original for fields not updated:
#   v_decennial → Decennial 2010 (unchanged)
#   v_sanitation → DSNY (suspended FY2023, not updated)
#   v_geo → geography (unchanged)
#   v_cdneeds → Community Board Needs (PDFs, not updated)

# ── Write output ──────────────────────────────────────────────────────────────
out = DATA_DIR / "cd_profiles_updated.csv"
df.to_csv(out, index=False)

updated_count = (
    len(ACS_SCALAR_COLS) + len(AGE_COLS) + 3   # ACS + puma/shared cols
    + len(PLUTO_COLS)
    + len(FACDB_COLS)
    + len(ZONING_COLS)
    + len(NYPD_COLS)
    + len(INCOME_COLS)
    + 7   # version tags
)

print(f"\nSaved {len(df)} rows × {len(df.columns)} cols → {out}")
print(f"  ~{updated_count} columns updated out of {len(df.columns)}")
print()

# ── Quick comparison summary ─────────────────────────────────────────────────
old = orig.set_index("borocd")
new = df.set_index("borocd")

compare_cols = [
    ("pop_acs",             "ACS population"),
    ("unemployment",        "Unemployment %"),
    ("poverty_rate",        "Poverty rate %"),
    ("pct_bach_deg",        "Bach. degree %"),
    ("mdn_hh_inc_interp",  "Median HH income"),
    ("crime_per_1000",      "Crime per 1,000"),
    ("total_lot_area",      "Total lot area"),
]

print("Change summary (citywide medians):")
print(f"{'Metric':<22} {'Old (v202402)':>16} {'New (updated)':>16}")
print("-" * 58)
for col, label in compare_cols:
    if col in old.columns and col in new.columns:
        old_med = old[col].median()
        new_med = new[col].median()
        print(f"  {label:<20} {old_med:>16.1f} {new_med:>16.1f}")
