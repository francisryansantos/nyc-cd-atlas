"""
fetch_acs.py — Pull ACS 2019-2023 (5-year) population estimates for all
NYC Community Districts from the Census Bureau API.

Since CDs are not a Census geography, data is fetched at the 2020-vintage
PUMA level and mapped to CDs using the names embedded in the PUMA labels.

4 PUMAs cover 2 CDs each (shared PUMAs); those rows are duplicated and
flagged with shared_puma=True. Population cannot be split between them.

Writes:
  data/cd_population_acs2023.csv  — one row per CD, 59 rows
"""

import re
import sys
import requests
import pandas as pd
from pathlib import Path

CENSUS_URL = "https://api.census.gov/data/2023/acs/acs5"
STATE_FIPS = "36"  # New York
DATA_DIR = Path("data")

# Variables to pull:
#   B01003_001E  Total population (estimate)
#   B01003_001M  Total population (margin of error)
VARIABLES = "NAME,B01003_001E,B01003_001M"

BOROUGH_CODES = {
    "Manhattan": 1,
    "Bronx": 2,
    "Brooklyn": 3,
    "Queens": 4,
    "Staten Island": 5,
}


def fetch_pumas() -> pd.DataFrame:
    print("Fetching ACS 2019-2023 PUMA data from Census API ...")
    try:
        resp = requests.get(CENSUS_URL, params={
            "get": VARIABLES,
            "for": "public use microdata area:*",
            "in": f"state:{STATE_FIPS}",
        }, timeout=30)
    except Exception as e:
        print(f"  Request failed ({e}). Falling back to cached data.", file=sys.stderr)
        return _cached_pumas()

    if resp.status_code != 200:
        print(f"  HTTP {resp.status_code}: {resp.text[:200]}", file=sys.stderr)
        print("  Falling back to cached data.", file=sys.stderr)
        return _cached_pumas()

    data = resp.json()
    df = pd.DataFrame(data[1:], columns=data[0])
    df = df.rename(columns={
        "public use microdata area": "puma_code",
        "B01003_001E": "pop_2023",
        "B01003_001M": "pop_2023_moe",
    })
    df["pop_2023"] = pd.to_numeric(df["pop_2023"])
    df["pop_2023_moe"] = pd.to_numeric(df["pop_2023_moe"])
    print(f"  {len(df)} NY state PUMAs fetched from Census API")
    return df


# Cached from Census API call on 2026-04-16 (ACS 2019-2023, B01003_001E).
# Used as fallback when the API is unavailable.
_NYC_PUMA_CACHE = [
    ("NYC-Manhattan Community District 3--Lower East Side & Chinatown PUMA; New York", 153288, "04103"),
    ("NYC-Manhattan Community District 4--Chelsea & Hell's Kitchen PUMA; New York", 117099, "04104"),
    ("NYC-Manhattan Community District 7--Upper West Side PUMA; New York", 218761, "04107"),
    ("NYC-Manhattan Community District 8--Upper East Side & Roosevelt Island PUMA; New York", 212308, "04108"),
    ("NYC-Manhattan Community District 9--Morningside Heights & Hamilton Heights PUMA; New York", 112774, "04109"),
    ("NYC-Manhattan Community District 10--Harlem PUMA; New York", 134893, "04110"),
    ("NYC-Manhattan Community District 11--East Harlem PUMA; New York", 124499, "04111"),
    ("NYC-Manhattan Community District 12--Washington Heights & Inwood PUMA; New York", 199120, "04112"),
    ("NYC-Manhattan Community Districts 1 & 2--Financial District & Greenwich Village PUMA; New York", 158067, "04121"),
    ("NYC-Manhattan Community Districts 5 & 6--Midtown, East Midtown, & Flatiron PUMA; New York", 196979, "04165"),
    ("NYC-Bronx Community District 4--Highbridge & Concourse PUMA; New York", 149631, "04204"),
    ("NYC-Bronx Community District 5--Morris Heights & Mount Hope PUMA; New York", 133897, "04205"),
    ("NYC-Bronx Community District 7--Fordham, Bedford Park, & Norwood PUMA; New York", 132733, "04207"),
    ("NYC-Bronx Community District 8--Riverdale, Kingsbridge, & Marble Hill PUMA; New York", 98696, "04208"),
    ("NYC-Bronx Community District 9--Soundview & Parkchester PUMA; New York", 170654, "04209"),
    ("NYC-Bronx Community District 10--Co-op City & Throgs Neck PUMA; New York", 128419, "04210"),
    ("NYC-Bronx Community District 11--Pelham Parkway & Morris Park PUMA; New York", 113982, "04211"),
    ("NYC-Bronx Community District 12--Wakefield, Williamsbridge, & Eastchester PUMA; New York", 160621, "04212"),
    ("NYC-Bronx Community Districts 1 & 2--Melrose, Mott Haven, Longwood, & Hunts Point PUMA; New York", 155574, "04221"),
    ("NYC-Bronx Community Districts 3 & 6--Morrisania, Tremont, Belmont, & West Farms PUMA; New York", 175043, "04263"),
    ("NYC-Brooklyn Community District 1--Williamsburg & Greenpoint PUMA; New York", 203002, "04301"),
    ("NYC-Brooklyn Community District 2--Downtown Brooklyn & Fort Greene PUMA; New York", 125637, "04302"),
    ("NYC-Brooklyn Community District 3--Bedford-Stuyvesant PUMA; New York", 180283, "04303"),
    ("NYC-Brooklyn Community District 4--Bushwick PUMA; New York", 111975, "04304"),
    ("NYC-Brooklyn Community District 5--East New York & Cypress Hills PUMA; New York", 201036, "04305"),
    ("NYC-Brooklyn Community District 6--Park Slope & Carroll Gardens PUMA; New York", 121009, "04306"),
    ("NYC-Brooklyn Community District 7--Sunset Park & Windsor Terrace PUMA; New York", 120253, "04307"),
    ("NYC-Brooklyn Community District 8--Crown Heights (North) PUMA; New York", 109719, "04308"),
    ("NYC-Brooklyn Community District 9--Crown Heights (South) PUMA; New York", 97675, "04309"),
    ("NYC-Brooklyn Community District 10--Bay Ridge & Dyker Heights PUMA; New York", 125053, "04310"),
    ("NYC-Brooklyn Community District 11--Bensonhurst & Bath Beach PUMA; New York", 182754, "04311"),
    ("NYC-Brooklyn Community District 12--Borough Park & Kensington PUMA; New York", 194695, "04312"),
    ("NYC-Brooklyn Community District 13--Coney Island & Brighton Beach PUMA; New York", 110145, "04313"),
    ("NYC-Brooklyn Community District 14--Flatbush & Midwood PUMA; New York", 159561, "04314"),
    ("NYC-Brooklyn Community District 15--Sheepshead Bay & Gravesend (East) PUMA; New York", 156462, "04315"),
    ("NYC-Brooklyn Community District 16--Ocean Hill & Brownsville PUMA; New York", 100787, "04316"),
    ("NYC-Brooklyn Community District 17--East Flatbush PUMA; New York", 153538, "04317"),
    ("NYC-Brooklyn Community District 18--Canarsie & Flatlands PUMA; New York", 192722, "04318"),
    ("NYC-Queens Community District 1--Astoria & Queensbridge PUMA; New York", 175516, "04401"),
    ("NYC-Queens Community District 2--Long Island City, Sunnyside, & Woodside PUMA; New York", 123823, "04402"),
    ("NYC-Queens Community District 3--Jackson Heights & East Elmhurst PUMA; New York", 161945, "04403"),
    ("NYC-Queens Community District 4--Elmhurst & Corona PUMA; New York", 168616, "04404"),
    ("NYC-Queens Community District 5--Ridgewood, Maspeth, & Middle Village PUMA; New York", 181189, "04405"),
    ("NYC-Queens Community District 6--Forest Hills & Rego Park PUMA; New York", 121131, "04406"),
    ("NYC-Queens Community District 7--Flushing, Murray Hill, & Whitestone PUMA; New York", 246517, "04407"),
    ("NYC-Queens Community District 8--Fresh Meadows, Hillcrest, & Briarwood PUMA; New York", 154886, "04408"),
    ("NYC-Queens Community District 9--Kew Gardens, Richmond Hill, & Woodhaven PUMA; New York", 149365, "04409"),
    ("NYC-Queens Community District 10--South Ozone Park & Howard Beach PUMA; New York", 135400, "04410"),
    ("NYC-Queens Community District 11--Auburndale, Bayside, & Douglaston PUMA; New York", 121282, "04411"),
    ("NYC-Queens Community District 12--Jamaica, St. Albans, & Hollis PUMA; New York", 254693, "04412"),
    ("NYC-Queens Community District 13--Queens Village, Bellerose, & Rosedale PUMA; New York", 205191, "04413"),
    ("NYC-Queens Community District 14--The Rockaways PUMA; New York", 130570, "04414"),
    ("NYC-Staten Island Community District 1--North Shore PUMA; New York", 181349, "04501"),
    ("NYC-Staten Island Community District 2--Mid-Island PUMA; New York", 142656, "04502"),
    ("NYC-Staten Island Community District 3--South Shore PUMA; New York", 168729, "04503"),
]


def _cached_pumas() -> pd.DataFrame:
    rows = [{"NAME": n, "pop_2023": p, "puma_code": c, "pop_2023_moe": None}
            for n, p, c in _NYC_PUMA_CACHE]
    df = pd.DataFrame(rows)
    df["pop_2023"] = pd.to_numeric(df["pop_2023"])
    print(f"  {len(df)} NYC PUMAs loaded from cache (MOE unavailable)")
    return df


def filter_nyc(df: pd.DataFrame) -> pd.DataFrame:
    nyc_keywords = list(BOROUGH_CODES.keys())
    mask = df["NAME"].apply(lambda n: any(k in n for k in nyc_keywords))
    nyc = df[mask].copy()
    print(f"  {len(nyc)} NYC PUMAs identified")
    return nyc


def parse_cd_mapping(name: str) -> list[dict]:
    """
    Extract borough and CD number(s) from a PUMA name like:
      'NYC-Manhattan Community District 9--Morningside Heights PUMA; New York'
      'NYC-Bronx Community Districts 1 & 2--Melrose, Mott Haven PUMA; New York'

    Returns a list of dicts, one per CD covered by this PUMA.
    """
    # Identify borough
    borough = next((b for b in BOROUGH_CODES if b in name), None)
    if borough is None:
        return []

    # Extract CD numbers (handles "District 9" and "Districts 1 & 2")
    match = re.search(r"Community Districts?\s+([\d\s&,]+?)--", name)
    if not match:
        return []

    cd_str = match.group(1)
    cd_nums = [int(n) for n in re.findall(r"\d+", cd_str)]

    return [
        {
            "borough": borough,
            "cd_num": n,
            "borocd": BOROUGH_CODES[borough] * 100 + n,
            "cd_short_title": f"{borough} CD {n}",
        }
        for n in cd_nums
    ]


def build_cd_table(nyc: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, puma_row in nyc.iterrows():
        mappings = parse_cd_mapping(puma_row["NAME"])
        shared = len(mappings) > 1
        for cd in mappings:
            rows.append({
                **cd,
                "puma_code": puma_row["puma_code"],
                "puma_name": puma_row["NAME"],
                "shared_puma": shared,
                "pop_2023": puma_row["pop_2023"],
                "pop_2023_moe": puma_row["pop_2023_moe"],
                "acs_vintage": "2019-2023",
                "geo_vintage": "2020 PUMA",
                "note": (
                    "Population is for the full shared PUMA; "
                    "cannot be disaggregated to individual CDs."
                    if shared else ""
                ),
            })

    df = pd.DataFrame(rows).sort_values("borocd").reset_index(drop=True)
    return df


if __name__ == "__main__":
    DATA_DIR.mkdir(exist_ok=True)

    pumas = fetch_pumas()
    nyc = filter_nyc(pumas)
    cd_table = build_cd_table(nyc)

    out = DATA_DIR / "cd_population_acs2023.csv"
    cd_table.to_csv(out, index=False)

    print(f"\nSaved {len(cd_table)} CD rows -> {out}")
    print(f"  Shared-PUMA CDs: {cd_table['shared_puma'].sum()} "
          f"({cd_table[cd_table['shared_puma']]['cd_short_title'].tolist()})")
    print()
    print(cd_table[["borocd", "cd_short_title", "pop_2023", "pop_2023_moe",
                     "shared_puma"]].to_string(index=False))
