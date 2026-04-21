"""
fetch_acs_2024_income.py — Compute median household income estimates for all
59 NYC Community Districts from ACS 2020-2024.

Two estimates are produced for each CD:

  mdn_hh_inc_puma    — Census-published PUMA-level median (B19013_001E),
                       assigned to CDs via puma_code.

  mdn_hh_inc_interp  — CD-level median interpolated from tract-level B19001
                       bracket counts aggregated to Community Districts using
                       the PLUTO tract→CD crosswalk.

The published PUMA median will still match within shared-PUMA pairs. The
interpolated median will be distinct for all 59 CDs because it is computed
after tract aggregation to the CD geography.

Interpolation formula (grouped-data linear):
  median = L + ((n/2 − F) / f) × w
  where L = lower bound, w = width, F = cumulative before bracket,
  f = count in bracket.

For the open-ended $200k+ bracket (Pareto tail):
  α = log((f16 + f17) / f17) / log(200000 / 150000)
  m = 200000 / (1 − rem/f17)^(1/α)

Writes:
  data/acs_2024_income_raw.csv  — cached tract-level B19001 bracket counts
  data/acs_2024_income.csv      — one row per CD, 6 columns

Usage:
  python fetch_acs_2024_income.py          # normal run
  python fetch_acs_2024_income.py --test   # run unit tests only
"""

import sys
import math
import time
import argparse
import requests
import numpy as np
import pandas as pd
from pathlib import Path

CENSUS_URL = "https://api.census.gov/data/2024/acs/acs5"
PLUTO_URL  = "https://data.cityofnewyork.us/resource/64uk-42ks.json"
STATE_FIPS = "36"
DATA_DIR   = Path("data")
RAW_CACHE  = DATA_DIR / "acs_2024_income_raw.csv"
CROSSWALK_CACHE = DATA_DIR / "pluto_tract_crosswalk.csv"

NYC_COUNTIES = ["005", "047", "061", "081", "085"]
COUNTY_TO_BORO = {"005": "2", "047": "3", "061": "1", "081": "4", "085": "5"}

_VALID_CDS = {
    *[f"1{n:02d}" for n in range(1, 13)],
    *[f"2{n:02d}" for n in range(1, 13)],
    *[f"3{n:02d}" for n in range(1, 19)],
    *[f"4{n:02d}" for n in range(1, 15)],
    *[f"5{n:02d}" for n in range(1, 4)],
}

# ── Income bracket definitions ─────────────────────────────────────────────────
# (lower_bound, width) for each of the 16 B19001 bracket variables (_002E–_017E)
# Bracket 17 ($200k+) is open-ended: width=None → Pareto tail applied.
BRACKETS = [
    (0,        10_000),   # _002E: < $10,000
    (10_000,    5_000),   # _003E: $10,000–$14,999
    (15_000,    5_000),   # _004E: $15,000–$19,999
    (20_000,    5_000),   # _005E: $20,000–$24,999
    (25_000,    5_000),   # _006E: $25,000–$29,999
    (30_000,    5_000),   # _007E: $30,000–$34,999
    (35_000,    5_000),   # _008E: $35,000–$39,999
    (40_000,    5_000),   # _009E: $40,000–$44,999
    (45_000,    5_000),   # _010E: $45,000–$49,999
    (50_000,   10_000),   # _011E: $50,000–$59,999
    (60_000,   15_000),   # _012E: $60,000–$74,999
    (75_000,   25_000),   # _013E: $75,000–$99,999
    (100_000,  25_000),   # _014E: $100,000–$124,999
    (125_000,  25_000),   # _015E: $125,000–$149,999
    (150_000,  50_000),   # _016E: $150,000–$199,999
    (200_000,  None),     # _017E: $200,000 or more (open-ended)
]

B19001_TOTAL = "B19001_001E"
B19001_VARS  = [f"B19001_{str(i).zfill(3)}E" for i in range(2, 18)]  # _002E–_017E


# ── Interpolation ─────────────────────────────────────────────────────────────

def interpolate_median(counts: list) -> tuple:
    """
    Compute median household income from bracket counts using Pareto-linear
    interpolation.

    Parameters
    ----------
    counts : list of 16 numeric values
        Household counts for B19001 brackets _002E through _017E (16 items).

    Returns
    -------
    (median, bracket_index)
        median        — interpolated median income in dollars
        bracket_index — 0-based index of the median bracket (0 = < $10k),
                        or -1 if data is invalid / all zeros.
    """
    counts = [max(0.0, c) for c in counts]
    n = sum(counts)
    if n == 0:
        return (float("nan"), -1)

    half = n / 2.0
    cumulative = 0.0
    for i, (cnt, (L, w)) in enumerate(zip(counts, BRACKETS)):
        cumulative += cnt
        if cumulative >= half:
            F = cumulative - cnt   # cumulative count before this bracket
            f = cnt
            if f == 0:
                return (float("nan"), -1)

            if w is not None:
                # Standard grouped-data linear interpolation
                median = L + ((half - F) / f) * w
            else:
                # Pareto tail for the open-ended $200k+ bracket
                f16 = counts[14]   # $150k–$199k (index 14 = bracket 16)
                f17 = counts[15]   # $200k+       (index 15 = bracket 17)
                rem = half - F     # HHs remaining above $200k
                if f17 <= 0 or f16 <= 0:
                    return (float("nan"), -1)
                try:
                    alpha = math.log((f16 + f17) / f17) / math.log(200_000 / 150_000)
                    if alpha <= 0:
                        return (float("nan"), -1)
                    median = 200_000 / (1.0 - rem / f17) ** (1.0 / alpha)
                    median = min(median, 500_000)  # sanity cap
                except (ValueError, ZeroDivisionError):
                    return (float("nan"), -1)

            return (round(median, 2), i)

    return (float("nan"), -1)


# ── Census API ────────────────────────────────────────────────────────────────

def fetch_puma_income() -> pd.DataFrame:
    """
    Fetch B19013 (published median) and B19001 (bracket counts) at PUMA level
    for all NY state PUMAs in one API call.

    Returns DataFrame with columns:
      puma_code_5, mdn_hh_inc_puma, mdn_hh_inc_puma_moe,
      B19001_001E, B19001_002E … B19001_017E
    """
    # 17 B19001 vars + 2 B19013 vars + NAME = 20 total (well under 50-var limit)
    variables = ",".join(
        ["B19013_001E", "B19013_001M", B19001_TOTAL] + B19001_VARS
    )
    print("Fetching B19013 + B19001 at PUMA level (1 API call) ...")
    params = {
        "get": f"NAME,{variables}",
        "for": "public use microdata area:*",
        "in":  f"state:{STATE_FIPS}",
    }
    resp = requests.get(CENSUS_URL, params=params, timeout=60)
    if resp.status_code != 200:
        sys.exit(
            f"Census API failed ({resp.status_code}): {resp.text[:200]}"
        )

    data = resp.json()
    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.rename(columns={
        "public use microdata area": "puma_code_5",
        "B19013_001E": "mdn_hh_inc_puma",
        "B19013_001M": "mdn_hh_inc_puma_moe",
    })
    df["puma_code_5"] = df["puma_code_5"].str.zfill(5)

    num_cols = ["mdn_hh_inc_puma", "mdn_hh_inc_puma_moe", B19001_TOTAL] + B19001_VARS
    for col in num_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Census suppression flag (-666666666) → NaN
    df.loc[df["mdn_hh_inc_puma"]     < 0, "mdn_hh_inc_puma"]     = float("nan")
    df.loc[df["mdn_hh_inc_puma_moe"] < 0, "mdn_hh_inc_puma_moe"] = float("nan")
    for col in [B19001_TOTAL] + B19001_VARS:
        df.loc[df[col] < 0, col] = 0

    print(f"  {len(df)} NY state PUMAs fetched")
    return df


def fetch_pluto_crosswalk() -> pd.DataFrame:
    """
    Query PLUTO for bct2020 × cd grouped by lot area, then assign each tract
    to the CD with the most lot area.
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
    df = df[df["cd"].isin(_VALID_CDS)].copy()

    idx = df.groupby("bct2020")["lot_area"].idxmax()
    xwalk = df.loc[idx, ["bct2020", "cd"]].copy()
    xwalk["borocd"] = xwalk["cd"].astype(int)
    xwalk = xwalk[["bct2020", "borocd"]].reset_index(drop=True)
    xwalk.to_csv(CROSSWALK_CACHE, index=False)
    print(f"  {len(xwalk)} tracts assigned and cached → {CROSSWALK_CACHE}")
    return xwalk


def load_crosswalk() -> pd.DataFrame:
    if CROSSWALK_CACHE.exists():
        print(f"Loading tract crosswalk from cache → {CROSSWALK_CACHE}")
        return pd.read_csv(CROSSWALK_CACHE, dtype={"bct2020": str, "borocd": int})
    return fetch_pluto_crosswalk()


def census_get_tract_income(county: str) -> pd.DataFrame:
    variables = ",".join([B19001_TOTAL] + B19001_VARS)
    params = {
        "get": f"NAME,{variables}",
        "for": "tract:*",
        "in": f"state:{STATE_FIPS} county:{county}",
    }
    for attempt in range(1, 4):
        print(f"    [B19001] county={county} attempt {attempt} ...", flush=True)
        try:
            resp = requests.get(CENSUS_URL, params=params, timeout=60)
            if resp.status_code == 200:
                data = resp.json()
                df = pd.DataFrame(data[1:], columns=data[0])
                df["bct2020"] = COUNTY_TO_BORO[county] + df["tract"].str.zfill(6)
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
            time.sleep(10 * attempt)
    sys.exit(f"Census API failed after 3 attempts (county {county})")


def fetch_tract_income() -> pd.DataFrame:
    if RAW_CACHE.exists():
        print(f"Loading tract-level B19001 cache → {RAW_CACHE}")
        return pd.read_csv(RAW_CACHE, dtype={"bct2020": str})

    print("Fetching tract-level B19001 bracket counts (5 county calls) ...")
    frames = [census_get_tract_income(county) for county in NYC_COUNTIES]
    df = pd.concat(frames, ignore_index=True)
    for col in [B19001_TOTAL] + B19001_VARS:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
        df.loc[df[col] < 0, col] = 0
    df.to_csv(RAW_CACHE, index=False)
    print(f"  Cached tract-level income brackets → {RAW_CACHE}")
    return df


# ── Build CD-level table ──────────────────────────────────────────────────────

def build_cd_income(puma_df: pd.DataFrame, tract_income_df: pd.DataFrame, xwalk: pd.DataFrame, acs_path: Path) -> pd.DataFrame:
    """
    Join PUMA-level income data to all 59 CDs via puma_code in acs_2024_raw.csv.
    Computes mdn_hh_inc_interp via bracket interpolation.
    """
    if not acs_path.exists():
        sys.exit(f"Missing: {acs_path}\nRun fetch_acs_2024_tracts.py first.")

    puma_map = pd.read_csv(acs_path, usecols=["borocd", "puma_code"])
    # puma_code stored as int64 (e.g. 4121); zero-pad to 5 chars for join
    puma_map["puma_code_5"] = puma_map["puma_code"].astype(str).str.zfill(5)

    puma_joined = puma_map.merge(puma_df, on="puma_code_5", how="left")

    tract_joined = tract_income_df.merge(xwalk, on="bct2020", how="inner")
    tract_agg = (
        tract_joined.groupby("borocd")[[B19001_TOTAL] + B19001_VARS]
        .sum()
        .reset_index()
    )

    merged = puma_joined.merge(tract_agg, on="borocd", how="left", suffixes=("_puma", ""))

    results = []
    for _, row in merged.iterrows():
        counts = [row.get(v, 0) for v in B19001_VARS]
        counts = [0 if (c != c or c < 0) else c for c in counts]  # NaN / negative → 0
        total  = row.get(B19001_TOTAL, sum(counts))
        if total != total or total < 0:
            total = sum(counts)

        median, bracket_idx = interpolate_median(counts)
        results.append({
            "borocd":              int(row["borocd"]),
            "mdn_hh_inc_puma":     row["mdn_hh_inc_puma"],
            "mdn_hh_inc_puma_moe": row["mdn_hh_inc_puma_moe"],
            "mdn_hh_inc_interp":   median,
            "total_households":    int(max(total, 0)),
            "median_bracket":      bracket_idx,
        })

    return pd.DataFrame(results).sort_values("borocd").reset_index(drop=True)


# ── Validation ────────────────────────────────────────────────────────────────

def validate(df: pd.DataFrame) -> None:
    """Print three diagnostic tables."""
    print()
    print("─" * 65)
    print("Validation")
    print("─" * 65)

    valid = df[df["mdn_hh_inc_puma"].notna() & df["mdn_hh_inc_interp"].notna()].copy()
    valid["pct_diff"] = (
        (valid["mdn_hh_inc_interp"] - valid["mdn_hh_inc_puma"])
        / valid["mdn_hh_inc_puma"].replace(0, np.nan) * 100
    )
    mean_abs = valid["pct_diff"].abs().mean()
    print(f"\n1. Interp vs PUMA — mean absolute % difference: {mean_abs:.2f}%")
    print("   (Expected to be directionally similar; interpolation is now CD-specific)")

    print("\n2. Shared-PUMA pairs (PUMA median matches; interpolated median should differ):")
    pairs = [(101, 102), (105, 106), (201, 202), (203, 206)]
    idx = df.set_index("borocd")
    print(f"   {'Pair':<10} {'CD':>5}  {'interp ($)':>12}  {'puma ($)':>12}")
    print(f"   {'─'*45}")
    for a, b in pairs:
        for cd in (a, b):
            if cd in idx.index:
                r      = idx.loc[cd]
                interp = r["mdn_hh_inc_interp"]
                puma   = r["mdn_hh_inc_puma"]
                i_str  = f"{interp:>12,.0f}" if not math.isnan(interp) else f"{'N/A':>12}"
                p_str  = f"{puma:>12,.0f}"   if not math.isnan(puma)   else f"{'N/A':>12}"
                print(f"   {str(a)+'&'+str(b):<10} {cd:>5}  {i_str}  {p_str}")

    print("\n3. Top 5 / bottom 5 CDs by mdn_hh_inc_interp:")
    ranked = df[df["mdn_hh_inc_interp"].notna()].sort_values(
        "mdn_hh_inc_interp", ascending=False
    )
    print(f"   {'borocd':>8}  {'interp ($)':>12}  {'puma ($)':>12}")
    print(f"   {'─'*36}")
    for _, r in ranked.head(5).iterrows():
        puma_v = r["mdn_hh_inc_puma"]
        p_str  = f"{puma_v:>12,.0f}" if not math.isnan(puma_v) else f"{'N/A':>12}"
        print(f"   {int(r['borocd']):>8}  {r['mdn_hh_inc_interp']:>12,.0f}  {p_str}")
    print(f"   {'...':>8}")
    for _, r in ranked.tail(5).iterrows():
        puma_v = r["mdn_hh_inc_puma"]
        p_str  = f"{puma_v:>12,.0f}" if not math.isnan(puma_v) else f"{'N/A':>12}"
        print(f"   {int(r['borocd']):>8}  {r['mdn_hh_inc_interp']:>12,.0f}  {p_str}")

    print("─" * 65)


# ── Unit tests ────────────────────────────────────────────────────────────────

def run_tests() -> None:
    """Unit tests for interpolate_median()."""
    print("Running unit tests for interpolate_median() ...")
    errors = 0

    def check(counts, lo, hi, label):
        nonlocal errors
        result, bracket = interpolate_median(counts)
        ok = not math.isnan(result) and lo <= result <= hi
        status = "PASS" if ok else "FAIL"
        if ok:
            print(f"  {status} [{label}]: ${result:,.0f} (bracket {bracket})")
        else:
            print(f"  {status} [{label}]: got {result}, expected [{lo:,}–{hi:,}]")
            errors += 1

    c1 = [0, 100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    check(c1, 10_000, 14_999, "all in $10k–$15k")

    c2 = [50, 0, 0, 0, 0, 0, 0, 0, 0, 100, 0, 0, 0, 0, 0, 0]
    check(c2, 50_000, 59_999, "median in $50k–$60k")

    c3 = [100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]
    result3, _ = interpolate_median(c3)
    if abs(result3 - 5_000) > 1:
        print(f"  FAIL [midpoint < $10k]: got ${result3:,.0f}, expected $5,000")
        errors += 1
    else:
        print(f"  PASS [midpoint < $10k]: ${result3:,.0f}")

    c4 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 10, 90]
    result4, bracket4 = interpolate_median(c4)
    if math.isnan(result4) or bracket4 != 15 or result4 < 200_000:
        print(f"  FAIL [Pareto tail]: got ${result4:,.0f} (bracket {bracket4}), expected ≥$200,000")
        errors += 1
    else:
        print(f"  PASS [Pareto tail]: ${result4:,.0f} (bracket {bracket4})")

    c5 = [0] * 16
    result5, _ = interpolate_median(c5)
    if not math.isnan(result5):
        print(f"  FAIL [all zeros]: got {result5}, expected NaN")
        errors += 1
    else:
        print(f"  PASS [all zeros]: returned NaN as expected")

    c6 = [10] * 16
    result6, bracket6 = interpolate_median(c6)
    if math.isnan(result6):
        print(f"  FAIL [uniform]: got NaN")
        errors += 1
    else:
        print(f"  PASS [uniform]: ${result6:,.0f} (bracket {bracket6})")

    print()
    if errors == 0:
        print("All tests passed.")
    else:
        print(f"{errors} test(s) FAILED.")
        sys.exit(1)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Fetch ACS 2020-2024 median HH income for all 59 NYC CDs"
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run unit tests for interpolate_median() and exit",
    )
    args = parser.parse_args()

    if args.test:
        run_tests()
        sys.exit(0)

    DATA_DIR.mkdir(exist_ok=True)

    # ── Step 1: Fetch PUMA published median ───────────────────────────────────
    puma_df = fetch_puma_income()
    print()

    # ── Step 2: Fetch tract-level bracket counts + crosswalk ─────────────────
    xwalk = load_crosswalk()
    print()
    tract_income_df = fetch_tract_income()
    print()

    # ── Step 3: Join to CDs and interpolate ──────────────────────────────────
    print("Joining tract income data to Community Districts ...")
    acs_path = DATA_DIR / "acs_2024_raw.csv"
    cd_df = build_cd_income(puma_df, tract_income_df, xwalk, acs_path)
    valid_count = cd_df["mdn_hh_inc_interp"].notna().sum()
    print(f"  {valid_count} valid interpolated medians for {len(cd_df)} CDs")
    print()

    # ── Step 4: Validate ─────────────────────────────────────────────────────
    validate(cd_df)
    print()

    # ── Step 5: Write output ─────────────────────────────────────────────────
    out_cols = [
        "borocd",
        "mdn_hh_inc_puma", "mdn_hh_inc_puma_moe",
        "mdn_hh_inc_interp",
        "total_households", "median_bracket",
    ]
    out_path = DATA_DIR / "acs_2024_income.csv"
    cd_df[out_cols].to_csv(out_path, index=False)
    print(f"Saved {len(cd_df)} CD rows → {out_path}")
    print()

    interp_med = cd_df["mdn_hh_inc_interp"].median()
    puma_med   = cd_df["mdn_hh_inc_puma"].median()
    print("Citywide summary (CD medians):")
    print(f"  mdn_hh_inc_interp : ${interp_med:>10,.0f}")
    print(f"  mdn_hh_inc_puma   : ${puma_med:>10,.0f}")
    print(f"  Min interp : ${cd_df['mdn_hh_inc_interp'].min():>10,.0f}")
    print(f"  Max interp : ${cd_df['mdn_hh_inc_interp'].max():>10,.0f}")
