"""
fetch_nypd_2024.py — Count NYPD 7 major felony complaints in 2024 by NYC CD.

Source: NYC Open Data qgea-i56i (NYPD Complaint Data Historic).

The "7 major felony offenses" (ky_cd 101,104,105,106,107,109,110) match the
same offense category used in the original DCP cd_profiles_v202402:
  101 — Murder & Non-Negligent Manslaughter
  104 — Rape
  105 — Robbery
  106 — Felony Assault
  107 — Burglary
  109 — Grand Larceny
  110 — Grand Larceny of Motor Vehicle

CD identification uses the Socrata computed region column
`:@computed_region_f5dn_yrer`, which pre-assigns each complaint to the
NYC Community District polygon it falls in (based on the complaint's lat/lon).

crime_per_1000 is computed using ACS 2020-2024 population from
data/acs_2024_raw.csv (produced by fetch_acs_2024.py).

Writes:
  data/nypd_2024_raw.csv  — one row per CD, 59 rows
"""

import sys
import time
import requests
import pandas as pd
from pathlib import Path

NYPD_URL  = "https://data.cityofnewyork.us/resource/qgea-i56i.json"
GEOM_URL  = "https://data.cityofnewyork.us/resource/f5dn-yrer.json"
DATA_DIR  = Path("data")

_VALID_CDS = {
    *[f"1{n:02d}" for n in range(1, 13)],
    *[f"2{n:02d}" for n in range(1, 13)],
    *[f"3{n:02d}" for n in range(1, 19)],
    *[f"4{n:02d}" for n in range(1, 15)],
    *[f"5{n:02d}" for n in range(1, 4)],
}


def fetch_cd_feature_map() -> dict[str, str]:
    """
    Return {feature_id_string → borocd_string} for all residential CDs.
    The Socrata computed-region dataset f5dn-yrer maps spatial feature IDs
    to NYC community district borocd values.
    """
    print("  Fetching community district feature-ID → borocd mapping ...")
    resp = requests.get(GEOM_URL, params={
        "$select": "_feature_id, borocd",
        "$limit": "100",
    }, timeout=30)
    if resp.status_code != 200:
        sys.exit(f"Failed to fetch CD geometry mapping: {resp.text[:200]}")

    mapping = {}
    for row in resp.json():
        fid   = row["_feature_id"]
        borocd = str(int(row["borocd"]))   # strip leading zeros if any
        if borocd in _VALID_CDS:
            mapping[fid] = borocd

    print(f"    {len(mapping)} residential CD features mapped")
    return mapping


def fetch_felony_counts(year: int = 2024) -> dict[str, int]:
    """
    GROUP BY computed-region CD feature ID to count felony complaints in `year`.
    Uses a generous 3-minute timeout since the dataset is very large.
    """
    # 7 major felony offense key codes (matches DCP cd_profiles methodology)
    MAJOR_FELONY_CODES = "101,104,105,106,107,109,110"
    start = f"{year}-01-01T00:00:00"
    end   = f"{year + 1}-01-01T00:00:00"

    for attempt in range(1, 4):
        print(f"  Fetching {year} 7-major-felony counts by CD (attempt {attempt}, may take ~2 min) ...")
        try:
            resp = requests.get(NYPD_URL, params={
                "$select": ":@computed_region_f5dn_yrer as cd_feature_id, count(*) as n",
                "$group":  ":@computed_region_f5dn_yrer",
                "$where":  (
                    f"ky_cd IN ({MAJOR_FELONY_CODES}) "
                    f"AND cmplnt_fr_dt >= '{start}' "
                    f"AND cmplnt_fr_dt < '{end}'"
                ),
                "$limit":  "300",
            }, timeout=200)
            if resp.status_code == 200:
                rows = resp.json()
                counts = {}
                for row in rows:
                    fid = row.get("cd_feature_id")
                    if fid is not None:
                        counts[fid] = int(row["n"])
                print(f"    Received {len(counts)} feature-ID buckets")
                return counts
            print(f"    HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        except Exception as exc:
            print(f"    Error: {exc}", file=sys.stderr)
        if attempt < 3:
            time.sleep(15)

    sys.exit("NYPD API unavailable after 3 attempts. Try again later.")


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)
    print("Fetching NYPD 2024 felony complaint counts by Community District ...")

    cd_map     = fetch_cd_feature_map()          # {feature_id → borocd}
    raw_counts = fetch_felony_counts(2024)        # {feature_id → count}

    # Load ACS 2024 population for crime_per_1000
    pop_path = DATA_DIR / "acs_2024_raw.csv"
    if not pop_path.exists():
        sys.exit("data/acs_2024_raw.csv not found — run fetch_acs_2024.py first.")
    pop_df = pd.read_csv(pop_path, usecols=["borocd", "pop_acs"])
    pop_map = pop_df.set_index("borocd")["pop_acs"].to_dict()  # {borocd_int → pop}

    # Build output
    rows = []
    for borocd_str in sorted(_VALID_CDS, key=int):
        borocd_int  = int(borocd_str)
        crime_count = 0

        for fid, bc in cd_map.items():
            if bc == borocd_str and fid in raw_counts:
                crime_count += raw_counts[fid]

        pop = pop_map.get(borocd_int, 0)
        crime_per_1000 = (crime_count / pop * 1000) if pop > 0 else None

        rows.append({
            "borocd":         borocd_int,
            "crime_count":    crime_count,
            "crime_per_1000": round(crime_per_1000, 2) if crime_per_1000 is not None else None,
            "crime_vintage":  "NYPD 2024 (7 major felonies)",
            "crime_note": (
                "7 major felony complaint counts (ky_cd 101,104,105,106,107,109,110) "
                "geocoded to Community Districts via Socrata spatial computed region "
                "(f5dn-yrer). Matches the offense category used in DCP cd_profiles_v202402."
            ),
        })

    df = pd.DataFrame(rows)

    out = DATA_DIR / "nypd_2024_raw.csv"
    df.to_csv(out, index=False)

    print(f"\nSaved {len(df)} CD rows → {out}")
    print(f"  Total 2024 felonies assigned to residential CDs: {df['crime_count'].sum():,}")
    print()
    print(df[["borocd", "crime_count", "crime_per_1000"]].to_string(index=False))
