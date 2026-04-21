"""
fetch_acs_2024.py — Pull ACS 2020-2024 (5-year) demographic variables for all
NYC Community Districts from the Census Bureau API.

Uses the same 2020-vintage PUMA→CD crosswalk as fetch_acs.py.
Output columns match the names used in cd_profiles_clean.csv for easy
side-by-side comparison.

3 API batches (Census max is 50 variables per call, including NAME):
  Batch 1 — pop, race, nativity, employment, rent burden, commute,
             poverty, education  (47 vars)
  Batch 2 — age pyramid B01001_001E-049E  (49 vars)
  Batch 3 — LEP estimates + MOEs via B16004  (49 vars)

Writes:
  data/acs_2024_raw.csv  — one row per CD, 59 rows
"""

import re
import sys
import time
import requests
import numpy as np
import pandas as pd
from pathlib import Path

CENSUS_URL = "https://api.census.gov/data/2024/acs/acs5"
STATE_FIPS = "36"   # New York
DATA_DIR = Path("data")

BOROUGH_CODES = {
    "Manhattan": 1, "Bronx": 2, "Brooklyn": 3, "Queens": 4, "Staten Island": 5,
}

AGE_BINS = [
    "under_5", "5_9", "10_14", "15_19", "20_24",
    "25_29", "30_34", "35_39", "40_44", "45_49",
    "50_54", "55_59", "60_64", "65_69", "70_74",
    "75_79", "80_84", "85_over",
]

# ── Census variable batches ───────────────────────────────────────────────────

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
    "B17001_001E", "B17001_002E",                           # poverty (total, below)
    "B17001_001M", "B17001_002M",                           # poverty MOE
    "B15003_001E", "B15003_001M",                           # education denom (pop 25+)
    "B15003_022E", "B15003_023E", "B15003_024E", "B15003_025E",  # bach/masters/prof/doctoral
    "B15003_022M", "B15003_023M", "B15003_024M", "B15003_025M",  # education MOE
])  # 47 vars + NAME = 48 ✓

# B01001: Sex by Age (1=total, 2=male, 3-25=male bins, 26=female, 27-49=female bins)
BATCH2_VARS = ",".join(
    f"B01001_{str(i).zfill(3)}E" for i in range(1, 50)
)  # 49 vars + NAME = 50 ✓

# B16004: Age by Language Spoken at Home by Ability to Speak English (pop 5+)
# Selecting "speak English not well" + "speak English not at all" across all language
# groups and age brackets (5-17, 18-64, 65+) × 4 language groups.
_LEP_E_VARS = [
    # Age 5–17
    "B16004_006E", "B16004_007E", "B16004_011E", "B16004_012E",
    "B16004_016E", "B16004_017E", "B16004_021E", "B16004_022E",
    # Age 18–64
    "B16004_028E", "B16004_029E", "B16004_033E", "B16004_034E",
    "B16004_038E", "B16004_039E", "B16004_043E", "B16004_044E",
    # Age 65+
    "B16004_050E", "B16004_051E", "B16004_055E", "B16004_056E",
    "B16004_060E", "B16004_061E", "B16004_065E", "B16004_066E",
]
_LEP_M_VARS = [v.replace("_0", "_0").replace("E", "M") for v in _LEP_E_VARS]

BATCH3_VARS = ",".join(
    ["B16004_001E"] + _LEP_E_VARS + _LEP_M_VARS
)  # 1 + 24 + 24 = 49 vars + NAME = 50 ✓


# ── API helper ────────────────────────────────────────────────────────────────

def census_get(variables: str, label: str) -> pd.DataFrame:
    """Fetch NY PUMA-level ACS 2020-2024 data; retries up to 3 times."""
    params = {
        "get": f"NAME,{variables}",
        "for": "public use microdata area:*",
        "in": f"state:{STATE_FIPS}",
    }
    for attempt in range(1, 4):
        print(f"  [{label}] attempt {attempt} ...")
        try:
            resp = requests.get(CENSUS_URL, params=params, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                df = pd.DataFrame(data[1:], columns=data[0])
                df = df.rename(columns={"public use microdata area": "puma_code"})
                df = df.drop(columns=["state"], errors="ignore")
                for col in df.columns:
                    if col not in ("NAME", "puma_code"):
                        df[col] = pd.to_numeric(df[col], errors="coerce")
                print(f"    OK — {len(df)} PUMAs")
                return df
            print(f"    HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        except Exception as exc:
            print(f"    Error: {exc}", file=sys.stderr)
        if attempt < 3:
            wait = 10 * attempt
            print(f"    Waiting {wait}s ...")
            time.sleep(wait)

    sys.exit(
        f"\nCensus API unavailable after 3 attempts ({label}).\n"
        "Check https://api.census.gov and try again later.\n"
        "If the problem persists, the year=2024 5-year ACS may not yet be\n"
        "available for PUMAs — check the Census API variable list at:\n"
        "https://api.census.gov/data/2024/acs/acs5/variables.html"
    )


# ── Geography helpers ─────────────────────────────────────────────────────────

def filter_nyc(df: pd.DataFrame) -> pd.DataFrame:
    mask = df["NAME"].apply(lambda n: any(k in n for k in BOROUGH_CODES))
    return df[mask].copy()


def parse_cd_mapping(name: str) -> list[dict]:
    """
    Extract borough and CD number(s) from a PUMA name like:
      'NYC-Manhattan Community District 9--Morningside Heights PUMA; New York'
      'NYC-Bronx Community Districts 1 & 2--Melrose, Mott Haven PUMA; New York'
    Returns one dict per CD.
    """
    borough = next((b for b in BOROUGH_CODES if b in name), None)
    if borough is None:
        return []
    match = re.search(r"Community Districts?\s+([\d\s&,]+?)--", name)
    if not match:
        return []
    cd_nums = [int(n) for n in re.findall(r"\d+", match.group(1))]
    return [
        {
            "borough": borough,
            "cd_num": n,
            "borocd": BOROUGH_CODES[borough] * 100 + n,
            "cd_short_title": f"{borough} CD {n}",
        }
        for n in cd_nums
    ]


# ── MOE helpers ───────────────────────────────────────────────────────────────

def prop_moe(num_e: pd.Series, den_e: pd.Series,
             num_m, den_m) -> pd.Series:
    """
    Census standard MOE for a proportion p = num / den.
    Returns MOE of the proportion (multiply by 100 for percentage MOE).
    Falls back to the additive formula when the discriminant is negative.
    """
    p = num_e / den_e.replace(0, np.nan)
    disc = num_m ** 2 - p ** 2 * den_m ** 2
    moe = np.where(
        disc >= 0,
        np.sqrt(np.maximum(disc, 0)) / den_e.replace(0, np.nan),
        np.sqrt(num_m ** 2 + p ** 2 * den_m ** 2) / den_e.replace(0, np.nan),
    )
    return pd.Series(moe, index=num_e.index)


def sqrt_sum_sq(*series) -> pd.Series:
    """MOE of a sum: sqrt(sum of squares of component MOEs)."""
    stacked = pd.concat([s ** 2 for s in series], axis=1)
    return np.sqrt(stacked.sum(axis=1))


# ── Derived column computation ────────────────────────────────────────────────

def build_derived(b1: pd.DataFrame, b2: pd.DataFrame, b3: pd.DataFrame) -> pd.DataFrame:
    """Merge the three batch DataFrames and compute all derived ACS columns."""
    df = (b1
          .merge(b2.drop(columns=["NAME"]), on="puma_code")
          .merge(b3.drop(columns=["NAME"]), on="puma_code"))

    # ── Total population ──────────────────────────────────────────────────────
    df["pop_acs"] = df["B01003_001E"]

    # ── Race / ethnicity ──────────────────────────────────────────────────────
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

    # ── Nativity (foreign-born) ───────────────────────────────────────────────
    df["pct_foreign_born"] = df["B05002_013E"] / df["B05002_001E"] * 100
    df["moe_foreign_born"] = prop_moe(
        df["B05002_013E"], df["B05002_001E"],
        df["B05002_013M"], df["B05002_001M"],
    ) * 100

    # ── Unemployment (% of civilian labour force) ─────────────────────────────
    df["unemployment"] = df["B23025_005E"] / df["B23025_003E"] * 100
    df["moe_unemployment"] = prop_moe(
        df["B23025_005E"], df["B23025_003E"],
        df["B23025_005M"], df["B23025_003M"],
    ) * 100

    # ── Rent burden (% of renter households paying ≥30 % of income on rent) ──
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

    # ── Mean commute (minutes; workers who commuted, i.e. not WFH) ───────────
    commuters = df["B08301_001E"] - df["B08301_021E"]
    df["mean_commute"] = df["B08136_001E"] / commuters.replace(0, np.nan)
    # Delta method: MOE(X/Y) ≈ (X/Y) * sqrt((MOE_X/X)² + (MOE_Y/Y)²)
    agg_t = df["B08136_001E"]
    agg_t_m = df["B08136_001M"]
    commuters_m = sqrt_sum_sq(df["B08301_001M"], df["B08301_021M"])
    df["moe_mean_commute"] = (agg_t / commuters.replace(0, np.nan)) * np.sqrt(
        (agg_t_m / agg_t.replace(0, np.nan)) ** 2
        + (commuters_m / commuters.replace(0, np.nan)) ** 2
    )

    # ── Poverty rate ──────────────────────────────────────────────────────────
    df["poverty_rate"] = df["B17001_002E"] / df["B17001_001E"] * 100
    df["moe_poverty_rate"] = prop_moe(
        df["B17001_002E"], df["B17001_001E"],
        df["B17001_002M"], df["B17001_001M"],
    ) * 100

    # ── Education (% with bachelor's degree or higher, pop 25+) ──────────────
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

    # ── Limited English Proficiency (% of pop 5+ who speak English not well) ──
    lep_num = df[_LEP_E_VARS].sum(axis=1)
    lep_num_moe = sqrt_sum_sq(*[df[v] for v in _LEP_M_VARS])
    lep_den = df["B16004_001E"]
    df["lep_rate"] = lep_num / lep_den * 100
    # Denominator MOE treated as 0 (B16004_001E ≈ total pop 5+, very precise)
    df["moe_lep_rate"] = prop_moe(
        lep_num, lep_den, lep_num_moe,
        pd.Series(0.0, index=df.index),
    ) * 100

    # ── Age pyramid (5-year bins matching DCP column names) ──────────────────
    def v(n: int) -> pd.Series:
        return df[f"B01001_{str(n).zfill(3)}E"]

    # Male
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
    df["male_60_64"]   = v(18) + v(19)          # 60-61 + 62-64
    df["male_65_69"]   = v(20) + v(21)          # 65-66 + 67-69
    df["male_70_74"]   = v(22)
    df["male_75_79"]   = v(23)
    df["male_80_84"]   = v(24)
    df["male_85_over"] = v(25)

    # Female (offset by 24: B01001_027E = female under-5, …, 049E = 85+)
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

    # ── Under-18 and over-65 rates ────────────────────────────────────────────
    # Use the fine-grained B01001 bins before 5-year collapsing:
    #   under 18 = under5 + 5-9 + 10-14 + 15-17 (B01001_006/030)
    #   over  65 = all 65+ bins
    male_u18   = v(3) + v(4) + v(5) + v(6)
    female_u18 = v(27) + v(28) + v(29) + v(30)
    male_o65   = v(20) + v(21) + v(22) + v(23) + v(24) + v(25)
    female_o65 = v(44) + v(45) + v(46) + v(47) + v(48) + v(49)
    tot_pop = df["B01003_001E"].replace(0, np.nan)

    df["under18_rate"] = (male_u18 + female_u18) / tot_pop * 100
    df["over65_rate"]  = (male_o65 + female_o65) / tot_pop * 100
    # Age-bin MOEs not collected (would require 47 additional B01001_*M vars)
    df["moe_under18_rate"] = np.nan
    df["moe_over65_rate"]  = np.nan

    return df


# ── CD table builder ──────────────────────────────────────────────────────────

_DERIVED_SCALAR_COLS = [
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
] + [f"male_{b}" for b in AGE_BINS] + [f"female_{b}" for b in AGE_BINS]

OUTPUT_COLS = (
    ["borocd", "borough", "cd_num", "cd_short_title", "puma_code", "shared_puma"]
    + _DERIVED_SCALAR_COLS
    + ["acs_vintage", "geo_vintage", "note"]
)


def build_cd_table(derived: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, puma_row in derived.iterrows():
        mappings = parse_cd_mapping(puma_row["NAME"])
        shared = len(mappings) > 1
        for cd in mappings:
            row = {
                **cd,
                "puma_code": puma_row["puma_code"],
                "shared_puma": shared,
                **{col: puma_row[col] for col in _DERIVED_SCALAR_COLS},
                "acs_vintage": "2020-2024",
                "geo_vintage": "2020 PUMA",
                "note": (
                    "ACS data is for the full shared PUMA; "
                    "cannot be disaggregated to individual CDs."
                    if shared else ""
                ),
            }
            rows.append(row)
    return pd.DataFrame(rows).sort_values("borocd").reset_index(drop=True)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    print("Fetching ACS 2020-2024 (5-year) PUMA data from Census API (year=2024) ...")

    b1 = census_get(BATCH1_VARS, "demographics")
    b2 = census_get(BATCH2_VARS, "age pyramid B01001")
    b3 = census_get(BATCH3_VARS, "language/LEP B16004")

    # Filter to NYC PUMAs (labeled "NYC-…")
    nyc_b1 = filter_nyc(b1)
    nyc_codes = set(nyc_b1["puma_code"])
    nyc_b2 = b2[b2["puma_code"].isin(nyc_codes)].copy()
    nyc_b3 = b3[b3["puma_code"].isin(nyc_codes)].copy()
    print(f"\n  {len(nyc_b1)} NYC PUMAs identified across all batches")

    derived = build_derived(nyc_b1, nyc_b2, nyc_b3)
    cd_table = build_cd_table(derived)

    out = DATA_DIR / "acs_2024_raw.csv"
    cd_table[OUTPUT_COLS].to_csv(out, index=False)

    print(f"\nSaved {len(cd_table)} CD rows → {out}")
    print(f"  Shared-PUMA CDs: {cd_table['shared_puma'].sum()} "
          f"({cd_table[cd_table['shared_puma']]['cd_short_title'].tolist()})")
    print()
    print(
        cd_table[[
            "borocd", "cd_short_title", "pop_acs",
            "unemployment", "poverty_rate", "shared_puma",
        ]].to_string(index=False)
    )
