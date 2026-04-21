"""
fetch_acs_2024_tracts.py — Compute ACS 2020-2024 demographics for all 59 NYC
Community Districts using census-tract-level aggregation.

DCP's original cd_profiles methodology aggregated from 2020 census tracts, NOT
from PUMAs. The PUMA-level script (fetch_acs_2024.py) therefore produces
identical values for the 8 CDs that share a PUMA (4 pairs). This script
replicates the tract-level approach so every CD gets distinct, accurate values.

Method:
  1. PLUTO 25v4 (64uk-42ks) → 2020 census tract (bct2020) → borocd crosswalk,
     weighted by lot area so each tract is assigned to its primary CD.
  2. ACS 2020-2024 (5-yr) raw counts at the census-tract level for all 5 NYC
     counties (3 API batches × 5 counties = 15 calls).
  3. Aggregate: sum E vars (raw counts); sqrt-sum-sq for M vars (MOE of a sum).
  4. Compute derived rates from CD-level aggregates using the same formulas as
     fetch_acs_2024.py.

Overwrites:
  data/acs_2024_raw.csv  — same column schema as the PUMA-based version
"""

import sys
import time
import requests
import numpy as np
import pandas as pd
from pathlib import Path

CENSUS_URL = "https://api.census.gov/data/2024/acs/acs5"
PLUTO_URL  = "https://data.cityofnewyork.us/resource/64uk-42ks.json"
STATE_FIPS = "36"
DATA_DIR   = Path("data")

# NYC county FIPS codes
NYC_COUNTIES = ["005", "047", "061", "081", "085"]  # Bronx, Brooklyn, Manh, Queens, SI

# County FIPS → borough digit used in PLUTO bct2020 (first character)
COUNTY_TO_BORO = {"005": "2", "047": "3", "061": "1", "081": "4", "085": "5"}

BORO_NAMES = {
    1: "Manhattan", 2: "Bronx", 3: "Brooklyn", 4: "Queens", 5: "Staten Island"
}

_VALID_CDS = {
    *[f"1{n:02d}" for n in range(1, 13)],
    *[f"2{n:02d}" for n in range(1, 13)],
    *[f"3{n:02d}" for n in range(1, 19)],
    *[f"4{n:02d}" for n in range(1, 15)],
    *[f"5{n:02d}" for n in range(1, 4)],
}

AGE_BINS = [
    "under_5", "5_9", "10_14", "15_19", "20_24",
    "25_29", "30_34", "35_39", "40_44", "45_49",
    "50_54", "55_59", "60_64", "65_69", "70_74",
    "75_79", "80_84", "85_over",
]

# ── Variable batches (≤49 vars each so NAME + vars ≤ 50) ─────────────────────

BATCH1_VARS = ",".join([
    "B01003_001E", "B01003_001M",                           # total pop
    "B03002_001E", "B03002_003E", "B03002_004E",            # race denom, NH White, NH Black
    "B03002_006E", "B03002_012E",                           # NH Asian, Hispanic
    "B05002_001E", "B05002_013E",                           # nativity total, foreign-born
    "B05002_001M", "B05002_013M",                           # nativity MOE
    "B23025_003E", "B23025_005E",                           # labor force, unemployed
    "B23025_003M", "B23025_005M",                           # employment MOE
    "B25070_001E", "B25070_007E", "B25070_008E",            # rent burden
    "B25070_009E", "B25070_010E", "B25070_011E",
    "B25070_001M", "B25070_007M", "B25070_008M",            # rent burden MOE
    "B25070_009M", "B25070_010M", "B25070_011M",
    "B08136_001E", "B08136_001M",                           # aggregate commute minutes
    "B08301_001E", "B08301_021E",                           # total workers, WFH
    "B08301_001M", "B08301_021M",                           # workers MOE
    "B17001_001E", "B17001_002E",                           # poverty total, below
    "B17001_001M", "B17001_002M",                           # poverty MOE
    "B15003_001E", "B15003_001M",                           # education denom (pop 25+)
    "B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E",  # bach/masters/prof/doc
    "B15003_022M", "B15003_023M", "B15003_024M", "B15003_025M",  # education MOE
])  # 47 vars + NAME = 48 ✓

# B01001: Sex by Age (no M vars needed; age-bin MOEs will remain NaN)
BATCH2_VARS = ",".join(
    f"B01001_{str(i).zfill(3)}E" for i in range(1, 50)
)  # 49 vars + NAME = 50 ✓

_LEP_E_VARS = [
    # Age 5–17: speak English "not well" + "not at all" × 4 language groups
    "B16004_006E", "B16004_007E", "B16004_011E", "B16004_012E",
    "B16004_016E", "B16004_017E", "B16004_021E", "B16004_022E",
    # Age 18–64
    "B16004_028E", "B16004_029E", "B16004_033E", "B16004_034E",
    "B16004_038E", "B16004_039E", "B16004_043E", "B16004_044E",
    # Age 65+
    "B16004_050E", "B16004_051E", "B16004_055E", "B16004_056E",
    "B16004_060E", "B16004_061E", "B16004_065E", "B16004_066E",
]
_LEP_M_VARS = [v.replace("E", "M") for v in _LEP_E_VARS]

BATCH3_VARS = ",".join(
    ["B16004_001E"] + _LEP_E_VARS + _LEP_M_VARS
)  # 1 + 24 + 24 = 49 vars + NAME = 50 ✓


# ── PLUTO crosswalk ───────────────────────────────────────────────────────────

def fetch_pluto_crosswalk() -> pd.DataFrame:
    """
    Query PLUTO for bct2020 × cd grouped by lot area.
    Returns DataFrame[bct2020, borocd] — one row per unique 2020 tract,
    assigned to the CD that contains the most lot area.
    """
    print("Building 2020 census tract → CD crosswalk from PLUTO ...")
    resp = requests.get(PLUTO_URL, params={
        "$select": "bct2020, cd, sum(lotarea) as lot_area",
        "$group":  "bct2020, cd",
        "$where":  "bct2020 IS NOT NULL AND cd IS NOT NULL",
        "$limit":  "50000",
    }, timeout=120)
    if resp.status_code != 200:
        sys.exit(f"PLUTO API failed ({resp.status_code}): {resp.text[:200]}")

    df = pd.DataFrame(resp.json())
    df["lot_area"] = pd.to_numeric(df["lot_area"], errors="coerce").fillna(0)
    df["cd"] = df["cd"].astype(str).str.strip()

    # Keep only residential CDs
    df = df[df["cd"].isin(_VALID_CDS)].copy()

    # Assign each bct2020 to the CD with the largest lot area
    idx = df.groupby("bct2020")["lot_area"].idxmax()
    xwalk = df.loc[idx, ["bct2020", "cd"]].copy()
    xwalk["borocd"] = xwalk["cd"].astype(int)
    xwalk = xwalk[["bct2020", "borocd"]].reset_index(drop=True)

    print(f"  {len(xwalk)} 2020 census tracts assigned to {xwalk['borocd'].nunique()} CDs")

    # Cache the crosswalk so fetch_acs_2024_income.py can reuse it without PLUTO
    cache = DATA_DIR / "pluto_tract_crosswalk.csv"
    xwalk.to_csv(cache, index=False)
    print(f"  Crosswalk cached → {cache}")
    return xwalk


# ── Census API helpers ────────────────────────────────────────────────────────

def census_get_tracts(variables: str, county: str, label: str) -> pd.DataFrame:
    """
    Fetch all census tracts in one NYC county from ACS 2020-2024.
    Returns a DataFrame with bct2020 key and all requested variables as numerics.
    """
    params = {
        "get": f"NAME,{variables}",
        "for": "tract:*",
        "in":  f"state:{STATE_FIPS} county:{county}",
    }
    for attempt in range(1, 4):
        print(f"    [{label}] county={county} attempt {attempt} ...", flush=True)
        try:
            resp = requests.get(CENSUS_URL, params=params, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                df = pd.DataFrame(data[1:], columns=data[0])
                # Build bct2020: boro_digit + 6-digit tract code
                df["bct2020"] = COUNTY_TO_BORO[county] + df["tract"].str.zfill(6)
                # Convert all variable columns to numeric
                skip = {"NAME", "state", "county", "tract", "bct2020"}
                for col in df.columns:
                    if col not in skip:
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                df = df.drop(columns=["NAME", "state", "county", "tract"], errors="ignore")
                print(f"      OK — {len(df)} tracts")
                return df
            print(f"      HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        except Exception as exc:
            print(f"      Error: {exc}", file=sys.stderr)
        if attempt < 3:
            wait = 10 * attempt
            print(f"      Waiting {wait}s ...")
            time.sleep(wait)
    sys.exit(f"Census API failed after 3 attempts ({label}, county {county})")


def fetch_all_counties(variables: str, label: str) -> pd.DataFrame:
    """Fetch tract-level ACS data for all 5 NYC counties and concatenate."""
    frames = [census_get_tracts(variables, cty, label) for cty in NYC_COUNTIES]
    return pd.concat(frames, ignore_index=True)


# ── MOE helpers ───────────────────────────────────────────────────────────────

def prop_moe(num_e: pd.Series, den_e: pd.Series,
             num_m: pd.Series, den_m: pd.Series) -> pd.Series:
    """MOE of a proportion p = num/den (returns proportion MOE; ×100 for %)."""
    p = num_e / den_e.replace(0, np.nan)
    disc = num_m ** 2 - p ** 2 * den_m ** 2
    moe = np.where(
        disc >= 0,
        np.sqrt(np.maximum(disc, 0)) / den_e.replace(0, np.nan),
        np.sqrt(num_m ** 2 + p ** 2 * den_m ** 2) / den_e.replace(0, np.nan),
    )
    return pd.Series(moe, index=num_e.index)


def sqrt_sum_sq(*series) -> pd.Series:
    """MOE of a sum: sqrt(sum of squared component MOEs)."""
    stacked = pd.concat([s ** 2 for s in series], axis=1)
    return np.sqrt(stacked.sum(axis=1))


# ── Aggregation ───────────────────────────────────────────────────────────────

def aggregate_to_cd(tract_df: pd.DataFrame, xwalk: pd.DataFrame) -> pd.DataFrame:
    """
    Join tract data to the crosswalk and aggregate to CD level.
    E vars: summed directly.
    M vars: aggregated as sqrt(sum of squares) — MOE of a sum.
    Returns DataFrame indexed by borocd.
    """
    merged = tract_df.merge(xwalk, on="bct2020", how="inner")

    e_cols = [c for c in merged.columns if c.endswith("E")]
    m_cols = [c for c in merged.columns if c.endswith("M")]

    # Sum E vars by CD
    e_agg = merged.groupby("borocd")[e_cols].sum()

    # M vars: sum of squares then sqrt
    tmp = merged[["borocd"] + m_cols].copy()
    for col in m_cols:
        tmp[col] = tmp[col] ** 2
    m_agg = np.sqrt(tmp.groupby("borocd")[m_cols].sum())

    return e_agg.join(m_agg)


# ── Derived statistics ────────────────────────────────────────────────────────

def build_derived(cd_agg: pd.DataFrame) -> pd.DataFrame:
    """Compute all derived ACS columns from CD-level aggregated raw counts."""
    df = cd_agg.copy()

    # Population
    df["pop_acs"] = df["B01003_001E"]

    # Race / ethnicity (no MOEs — race margins not collected)
    tot_race = df["B03002_001E"]
    df["pct_hispanic"] = df["B03002_012E"] / tot_race * 100
    df["pct_white_nh"] = df["B03002_003E"] / tot_race * 100
    df["pct_black_nh"] = df["B03002_004E"] / tot_race * 100
    df["pct_asian_nh"] = df["B03002_006E"] / tot_race * 100
    df["pct_other_nh"] = (
        tot_race
        - df["B03002_012E"] - df["B03002_003E"]
        - df["B03002_004E"] - df["B03002_006E"]
    ) / tot_race * 100
    df["pct_other_nh"] = df["pct_other_nh"].clip(lower=0)

    # Nativity
    df["pct_foreign_born"] = df["B05002_013E"] / df["B05002_001E"] * 100
    df["moe_foreign_born"] = prop_moe(
        df["B05002_013E"], df["B05002_001E"],
        df["B05002_013M"], df["B05002_001M"],
    ) * 100

    # Unemployment (% of civilian labour force)
    df["unemployment"] = df["B23025_005E"] / df["B23025_003E"] * 100
    df["moe_unemployment"] = prop_moe(
        df["B23025_005E"], df["B23025_003E"],
        df["B23025_005M"], df["B23025_003M"],
    ) * 100

    # Rent burden (% of renter HHs paying ≥30% of income on rent)
    rent_num = (df["B25070_007E"] + df["B25070_008E"]
                + df["B25070_009E"] + df["B25070_010E"])
    rent_den = df["B25070_001E"] - df["B25070_011E"]  # exclude "not computed"
    df["pct_hh_rent_burd"] = rent_num / rent_den * 100
    rent_num_moe = sqrt_sum_sq(
        df["B25070_007M"], df["B25070_008M"],
        df["B25070_009M"], df["B25070_010M"],
    )
    rent_den_moe = sqrt_sum_sq(df["B25070_001M"], df["B25070_011M"])
    df["moe_hh_rent_burd"] = prop_moe(
        rent_num, rent_den, rent_num_moe, rent_den_moe,
    ) * 100

    # Mean commute (minutes; workers who commuted, i.e. not WFH)
    commuters   = df["B08301_001E"] - df["B08301_021E"]
    agg_t       = df["B08136_001E"]
    agg_t_m     = df["B08136_001M"]
    commuters_m = sqrt_sum_sq(df["B08301_001M"], df["B08301_021M"])
    df["mean_commute"] = agg_t / commuters.replace(0, np.nan)
    df["moe_mean_commute"] = df["mean_commute"] * np.sqrt(
        (agg_t_m / agg_t.replace(0, np.nan)) ** 2
        + (commuters_m / commuters.replace(0, np.nan)) ** 2
    )

    # Poverty rate
    df["poverty_rate"] = df["B17001_002E"] / df["B17001_001E"] * 100
    df["moe_poverty_rate"] = prop_moe(
        df["B17001_002E"], df["B17001_001E"],
        df["B17001_002M"], df["B17001_001M"],
    ) * 100

    # Education: % with bachelor's degree or higher (pop 25+)
    bach_num = (df["B15003_022E"] + df["B15003_023E"]
                + df["B15003_024E"] + df["B15003_025E"])
    bach_num_moe = sqrt_sum_sq(
        df["B15003_022M"], df["B15003_023M"],
        df["B15003_024M"], df["B15003_025M"],
    )
    df["pct_bach_deg"] = bach_num / df["B15003_001E"] * 100
    df["moe_bach_deg"] = prop_moe(
        bach_num, df["B15003_001E"],
        bach_num_moe, df["B15003_001M"],
    ) * 100

    # LEP: % of pop 5+ who speak English "not well" or "not at all"
    lep_num     = df[_LEP_E_VARS].sum(axis=1)
    lep_num_moe = sqrt_sum_sq(*[df[v] for v in _LEP_M_VARS])
    lep_den     = df["B16004_001E"]
    df["lep_rate"] = lep_num / lep_den * 100
    df["moe_lep_rate"] = prop_moe(
        lep_num, lep_den, lep_num_moe,
        pd.Series(0.0, index=df.index),
    ) * 100

    # Age pyramid — direct sum of B01001 bins
    def v(n: int) -> pd.Series:
        return df[f"B01001_{str(n).zfill(3)}E"]

    df["male_under_5"] = v(3)
    df["male_5_9"]     = v(4)
    df["male_10_14"]   = v(5)
    df["male_15_19"]   = v(6)  + v(7)           # 15-17 + 18-19
    df["male_20_24"]   = v(8)  + v(9)  + v(10)  # 20 + 21 + 22-24
    df["male_25_29"]   = v(11)
    df["male_30_34"]   = v(12)
    df["male_35_39"]   = v(13)
    df["male_40_44"]   = v(14)
    df["male_45_49"]   = v(15)
    df["male_50_54"]   = v(16)
    df["male_55_59"]   = v(17)
    df["male_60_64"]   = v(18) + v(19)
    df["male_65_69"]   = v(20) + v(21)
    df["male_70_74"]   = v(22)
    df["male_75_79"]   = v(23)
    df["male_80_84"]   = v(24)
    df["male_85_over"] = v(25)

    df["female_under_5"] = v(27)
    df["female_5_9"]     = v(28)
    df["female_10_14"]   = v(29)
    df["female_15_19"]   = v(30) + v(31)
    df["female_20_24"]   = v(32) + v(33) + v(34)
    df["female_25_29"]   = v(35)
    df["female_30_34"]   = v(36)
    df["female_35_39"]   = v(37)
    df["female_40_44"]   = v(38)
    df["female_45_49"]   = v(39)
    df["female_50_54"]   = v(40)
    df["female_55_59"]   = v(41)
    df["female_60_64"]   = v(42) + v(43)
    df["female_65_69"]   = v(44) + v(45)
    df["female_70_74"]   = v(46)
    df["female_75_79"]   = v(47)
    df["female_80_84"]   = v(48)
    df["female_85_over"] = v(49)

    # Under-18 and over-65 rates (MOEs not collected for age bins)
    male_u18   = v(3)  + v(4)  + v(5)  + v(6)
    female_u18 = v(27) + v(28) + v(29) + v(30)
    male_o65   = v(20) + v(21) + v(22) + v(23) + v(24) + v(25)
    female_o65 = v(44) + v(45) + v(46) + v(47) + v(48) + v(49)
    tot_pop    = df["B01003_001E"].replace(0, np.nan)
    df["under18_rate"]     = (male_u18 + female_u18) / tot_pop * 100
    df["over65_rate"]      = (male_o65 + female_o65) / tot_pop * 100
    df["moe_under18_rate"] = np.nan
    df["moe_over65_rate"]  = np.nan

    return df


# ── Main ──────────────────────────────────────────────────────────────────────

_DERIVED_COLS = [
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
] + [f"male_{b}"   for b in AGE_BINS] + [f"female_{b}" for b in AGE_BINS]

OUTPUT_COLS = (
    ["borocd", "borough", "cd_num", "cd_short_title", "puma_code", "shared_puma"]
    + _DERIVED_COLS
    + ["acs_vintage", "geo_vintage", "note"]
)


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    print("Fetching ACS 2020-2024 at census-tract level for all NYC CDs ...")
    print()

    # ── Step 1: PLUTO crosswalk ───────────────────────────────────────────────
    xwalk = fetch_pluto_crosswalk()
    print()

    # ── Step 2: ACS tract-level data (3 batches × 5 counties) ────────────────
    print("Fetching ACS tract-level data (15 API calls) ...")
    print("  Batch 1: demographics ...")
    b1 = fetch_all_counties(BATCH1_VARS, "demographics")

    print("  Batch 2: age pyramid (B01001) ...")
    b2 = fetch_all_counties(BATCH2_VARS, "age-B01001")

    print("  Batch 3: language/LEP (B16004) ...")
    b3 = fetch_all_counties(BATCH3_VARS, "lep-B16004")
    print()

    # ── Step 3: Merge batches on bct2020 ─────────────────────────────────────
    print("Merging batches ...")
    # Drop columns already in b1 (except bct2020) before joining b2/b3
    b2_new = b2[[c for c in b2.columns if c not in b1.columns or c == "bct2020"]]
    b3_new = b3[[c for c in b3.columns if c not in b1.columns or c == "bct2020"]]
    tract_data = (
        b1.merge(b2_new, on="bct2020", how="inner")
          .merge(b3_new, on="bct2020", how="inner")
    )
    print(f"  {len(tract_data)} tracts with complete data across all 3 batches")
    print()

    # ── Step 4: Aggregate raw counts to CD level ──────────────────────────────
    print("Aggregating tracts → Community Districts ...")
    cd_agg = aggregate_to_cd(tract_data, xwalk)
    print(f"  Aggregated to {len(cd_agg)} CDs")
    print()

    # ── Step 5: Compute derived rates ─────────────────────────────────────────
    print("Computing derived rates and MOEs ...")
    derived = build_derived(cd_agg)  # indexed by borocd

    # ── Step 6: Load puma_code / shared_puma from existing PUMA-based CSV ────
    puma_info: dict[int, dict] = {}
    existing = DATA_DIR / "acs_2024_raw.csv"
    if existing.exists():
        puma_df = pd.read_csv(existing, usecols=["borocd", "puma_code", "shared_puma"])
        for _, row in puma_df.iterrows():
            puma_info[int(row["borocd"])] = {
                "puma_code": str(row["puma_code"]).zfill(5) if pd.notna(row["puma_code"]) else "",
                "shared_puma": bool(row["shared_puma"]),
            }
    else:
        print("  Warning: acs_2024_raw.csv not found; puma_code/shared_puma will be empty")

    # ── Step 7: Build output DataFrame ───────────────────────────────────────
    rows = []
    for borocd_str in sorted(_VALID_CDS, key=int):
        borocd = int(borocd_str)
        boro   = borocd // 100
        cd_num = borocd % 100

        if borocd not in derived.index:
            print(f"  Warning: no tract data found for borocd={borocd}", file=sys.stderr)
            continue

        puma = puma_info.get(borocd, {})
        row = {
            "borocd":         borocd,
            "borough":        BORO_NAMES.get(boro, ""),
            "cd_num":         cd_num,
            "cd_short_title": f"{BORO_NAMES.get(boro, '')} CD {cd_num}",
            "puma_code":      puma.get("puma_code", ""),
            "shared_puma":    puma.get("shared_puma", False),
            **{col: derived.at[borocd, col] for col in _DERIVED_COLS if col in derived.columns},
            "acs_vintage":    "2020-2024",
            "geo_vintage":    "2020 Census Tract",
            "note":           (
                "Tract-level aggregation; distinct values computed for each CD "
                "even when CDs share a PUMA."
            ),
        }
        rows.append(row)

    out_df = pd.DataFrame(rows)

    # ── Step 8: Write output ─────────────────────────────────────────────────
    out = DATA_DIR / "acs_2024_raw.csv"
    out_df[OUTPUT_COLS].to_csv(out, index=False)

    print(f"Saved {len(out_df)} CD rows → {out}")
    print()

    # Quick comparison: shared-PUMA CDs should now differ within each pair
    shared = out_df[out_df["shared_puma"] == True].set_index("borocd")
    pairs = [(101, 102), (105, 106), (201, 202), (203, 206)]
    print("Shared-PUMA pair comparison (poverty_rate, pct_bach_deg, pop_acs):")
    print(f"  {'Pair':<12} {'CD':>5}  {'poverty':>8}  {'bach%':>7}  {'pop':>9}")
    print(f"  {'-'*52}")
    for a, b in pairs:
        for cd in (a, b):
            if cd in shared.index:
                r = shared.loc[cd]
                print(f"  {str(a)+'&'+str(b):<12} {cd:>5}  "
                      f"{r.get('poverty_rate', float('nan')):>8.2f}  "
                      f"{r.get('pct_bach_deg', float('nan')):>7.2f}  "
                      f"{int(r.get('pop_acs', 0)):>9,}")
    print()
    print("Citywide medians (tract-based):")
    print(
        out_df[["borocd", "pop_acs", "unemployment", "poverty_rate",
                "pct_bach_deg", "lep_rate"]].median(numeric_only=True).to_string()
    )
