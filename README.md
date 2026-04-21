# NYC Community District Profiles — Updated Dataset

## Overview

This project downloads, updates, and documents the NYC Department of City Planning
**Community District Profiles** dataset. The original source (`community_district_profiles_v202402`)
was last refreshed in February 2024 with data as old as 2018. This project replaces
the core demographic, land-use, facility, and crime columns with the most current
publicly available data while preserving the original column layout.

The result is `data/cd_profiles_updated.csv`: 59 rows (one per NYC Community District),
272 columns — the original 182-column schema updated with newer data and extended with
71 facility counts (all FacDB categories), 17 zoning columns, and 6 median household
income columns that were not in the original.

---

## Community Districts

New York City has **59 residential Community Districts** across 5 boroughs:

| Borough | CDs | borocd range |
|---|---|---|
| Manhattan | 12 | 101–112 |
| Bronx | 12 | 201–212 |
| Brooklyn | 18 | 301–318 |
| Queens | 14 | 401–414 |
| Staten Island | 3 | 501–503 |

Each CD is governed by a Community Board and corresponds to a set of neighborhoods.
Community Districts are **not** a standard Census geography — they are NYC-specific
administrative units defined by the city.

---

## Data Sources

### 1. American Community Survey 2020–2024 (5-Year Estimates)

**Source:** U.S. Census Bureau, ACS 5-Year Estimates
**API endpoint:** `https://api.census.gov/data/2024/acs/acs5`
**Geography:** 2020 Census tracts, aggregated to Community Districts
**Script:** `fetch_acs_2024_tracts.py`
**Output:** `data/acs_2024_raw.csv`

#### Variables collected

| Column | Description | Census table(s) |
|---|---|---|
| `pop_acs` | Total population | B01003 |
| `pct_hispanic` | % Hispanic or Latino (any race) | B03002 |
| `pct_white_nh` | % Non-Hispanic White alone | B03002 |
| `pct_black_nh` | % Non-Hispanic Black or African American alone | B03002 |
| `pct_asian_nh` | % Non-Hispanic Asian alone | B03002 |
| `pct_other_nh` | % Non-Hispanic all other races/multiracial | B03002 |
| `pct_foreign_born` | % foreign-born | B05002 |
| `moe_foreign_born` | Margin of error for `pct_foreign_born` (90%) | B05002 |
| `unemployment` | % of civilian labour force that is unemployed | B23025 |
| `moe_unemployment` | Margin of error for `unemployment` (90%) | B23025 |
| `pct_hh_rent_burd` | % of renter households paying ≥30% of income on rent | B25070 |
| `moe_hh_rent_burd` | Margin of error for `pct_hh_rent_burd` (90%) | B25070 |
| `mean_commute` | Mean commute time in minutes (non-WFH workers only) | B08136, B08301 |
| `moe_mean_commute` | Margin of error for `mean_commute` (90%) | B08136, B08301 |
| `poverty_rate` | % of population below the federal poverty level | B17001 |
| `moe_poverty_rate` | Margin of error for `poverty_rate` (90%) | B17001 |
| `pct_bach_deg` | % of population 25+ with a bachelor's degree or higher | B15003 |
| `moe_bach_deg` | Margin of error for `pct_bach_deg` (90%) | B15003 |
| `lep_rate` | % of population 5+ who speak English "not well" or "not at all" | B16004 |
| `moe_lep_rate` | Margin of error for `lep_rate` (90%) | B16004 |
| `under18_rate` | % of population under 18 years old | B01001 |
| `over65_rate` | % of population 65 years and older | B01001 |
| `male_under_5` … `male_85_over` | Male population count in each 5-year age bin (18 bins) | B01001 |
| `female_under_5` … `female_85_over` | Female population count in each 5-year age bin (18 bins) | B01001 |

**Age bins** (18 per sex): `under_5`, `5_9`, `10_14`, `15_19`, `20_24`, `25_29`, `30_34`,
`35_39`, `40_44`, `45_49`, `50_54`, `55_59`, `60_64`, `65_69`, `70_74`, `75_79`, `80_84`, `85_over`.

**Note on margins of error:** MOEs are reported at the 90% confidence level, as published by
the Census Bureau. Race/ethnicity percentages and age-bin counts do not include MOEs because
the input variables were not requested (they would require an additional API batch beyond the
Census limit of 50 variables per call).

---

### 2. PLUTO 25v4 — Primary Land Use Tax Lot Output

**Source:** NYC Department of City Planning, MapPLUTO / PLUTO version 25v4
**NYC Open Data dataset ID:** `64uk-42ks`
**API endpoint:** `https://data.cityofnewyork.us/resource/64uk-42ks.json`
**Aggregation:** Lot-level records grouped by Community District and land-use code
**Script:** `fetch_pluto_2025.py`
**Output:** `data/pluto_2025_raw.csv`

#### Land-use categories

PLUTO assigns each tax lot a land-use code (1–11). The category labels below match
the DCP `cd_profiles` naming convention:

| PLUTO code | Category |
|---|---|
| 1 | `res_1_2_family_bldg` — 1- and 2-family residential buildings |
| 2 | `res_multifamily_walkup` — Multi-family walk-up (3–5+ stories, no elevator) |
| 3 | `res_multifamily_elevator` — Multi-family elevator buildings |
| 4 | `mixed_use` — Mixed residential and commercial use |
| 5 | `commercial_office` — Commercial and office buildings |
| 6 | `industrial_manufacturing` — Industrial and manufacturing |
| 7 | `transportation_utility` — Transportation and utility |
| 8 | `public_facility_institution` — Public facilities and institutions |
| 9 | `open_space` — Open space and outdoor recreation |
| 10 | `parking` — Parking facilities |
| 11 | `vacant` — Vacant land |
| null | `other_no_data` — Missing or unclassified land-use code |

#### Variables collected (per category `{cat}`)

| Column | Description |
|---|---|
| `lot_area_{cat}` | Total lot area (sq ft) for all lots of this land-use type in the CD |
| `pct_lot_area_{cat}` | `lot_area_{cat}` as a percentage of `total_lot_area` |
| `lots_{cat}` | Count of tax lots of this land-use type in the CD |
| `total_lot_area` | Sum of lot area across all land-use types (sq ft) |
| `lots_total` | Total number of tax lots in the CD |
| `cd_tot_bldgs` | Total number of buildings in the CD |
| `cd_tot_resunits` | Total number of residential units in the CD |

**Citywide totals:** 1,087,295 buildings; 3,740,436 residential units across all 59 CDs.

**Note on `total_lot_area`:** PLUTO 25v4 values are substantially larger than those in
the v202402 original (citywide median 64.8M sq ft vs 5.7M sq ft). This reflects differences
in data vintage and likely differences in aggregation methodology between PLUTO versions.
Use the `pct_lot_area_*` proportional columns for cross-vintage comparisons.

---

### 3. NYC Facilities Database (FacDB) Oct 2025 + Parks Mar 2026

**Sources:**
- FacDB: NYC DCP Facilities Database (same data that powers the NYC Facilities Explorer)
  NYC Open Data dataset ID: `ji82-xba5`
- Parks properties: NYC Parks Department
  NYC Open Data dataset ID: `enfh-gkve`

**Script:** `fetch_facdb_2025.py`
**Output:** `data/facdb_2025_raw.csv`

All 70 `facsubgrp` categories in FacDB are counted, producing one `count_*` column per
category. Column names are normalized to `snake_case` with a `count_` prefix. Three
legacy column names are preserved for backward compatibility.

`count_parks` comes from the Parks Properties dataset (more comprehensive for park
parcels than FacDB's own parks category). FacDB's "PARKS" facsubgrp is available
separately as `count_parks_facdb`.

#### Variables collected

**Parks (from NYC Parks Properties dataset)**

| Column | Citywide total |
|---|---|
| `count_parks` | 1,998 |

**Administration of Government**

| Column | Citywide total |
|---|---|
| `count_city_agency_parking` | 174 |
| `count_custodial` | 30 |
| `count_maintenance_garages` | 28 |
| `count_storage` | 169 |
| `count_city_government_offices` | 502 |
| `count_training_testing` | 15 |
| `count_miscellaneous_use` | 19 |

**Core Infrastructure and Transportation**

| Column | Citywide total |
|---|---|
| `count_material_supplies` | 5 |
| `count_wholesale_markets` | 4 |
| `count_dsny_drop_off_facility` | 1,344 |
| `count_solid_waste_processing` | 219 |
| `count_solid_waste_transfer_carting` | 124 |
| `count_telecommunications` | 9 |
| `count_airports_heliports` | 7 |
| `count_bus_depots_terminals` | 143 |
| `count_other_transportation` | 183 |
| `count_parking_lots_garages` | 2,596 |
| `count_ports_ferry_landings` | 67 |
| `count_rail_yards_maintenance` | 352 |
| `count_wastewater_pollution_control` | 158 |

**Education, Child Welfare, and Youth**

| Column | Citywide total |
|---|---|
| `count_adult_immigrant_literacy` | 134 |
| `count_camps` | 319 |
| `count_child_nutrition` | 2,051 |
| `count_day_care` | 2,204 |
| `count_doe_universal_pre_kindergarten` | 1,984 |
| `count_preschools_for_students_with_disabilities` | 85 |
| `count_colleges_universities` | 126 |
| `count_charter_k_12_schools` | 463 |
| `count_ged_alternative_high_school_equivalency` | 103 |
| `count_non_public_k_12_schools` | 952 |
| `count_public_private_special_education_schools` | 65 |
| `count_public_schools` *(legacy name)* | 1,520 |
| `count_proprietary_schools` | 464 |
| `count_after_school_programs` | 1,279 |
| `count_youth_centers_literacy_programs_job_training_servi` | 3,955 |

**Health and Human Services**

| Column | Citywide total |
|---|---|
| `count_health_promotion_disease_prevention` | 6 |
| `count_hosp_clinic` *(legacy name)* | 1,269 |
| `count_mental_health` | 1,254 |
| `count_other_health_care` | 251 |
| `count_residential_health_care` | 172 |
| `count_substance_use_disorder_treatment_programs` | 324 |
| `count_community_centers_community_programs` | 201 |
| `count_financial_assistance_social_services` | 64 |
| `count_immigrant_services` | 55 |
| `count_legal_intervention_services` | 299 |
| `count_non_residential_housing_homeless_services` | 264 |
| `count_programs_for_people_with_disabilities` | 194 |
| `count_senior_services` | 559 |
| `count_soup_kitchens_food_pantries` | 560 |
| `count_workforce_development` | 142 |

**Libraries and Cultural Programs**

| Column | Citywide total |
|---|---|
| `count_historical_societies` | 46 |
| `count_museums` | 122 |
| `count_other_cultural_institutions` | 1,776 |
| `count_academic_special_libraries` | 27 |
| `count_libraries` *(legacy name)* | 224 |

**Parks, Gardens, and Historical Sites**

| Column | Citywide total |
|---|---|
| `count_historical_sites` | 1,027 |
| `count_cemeteries` | 12 |
| `count_gardens` | 350 |
| `count_parks_facdb` | 438 |
| `count_preserves_conservation_areas` | 109 |
| `count_privately_owned_public_space` | 392 |
| `count_recreation_waterfront_sites` | 628 |
| `count_streetscapes_plazas_malls` | 560 |
| `count_undeveloped` | 36 |

**Public Safety, Emergency Services, and Justice**

| Column | Citywide total |
|---|---|
| `count_fire_services` | 217 |
| `count_other_emergency_services` | 34 |
| `count_courthouses_judicial` | 43 |
| `count_detention_correctional` | 19 |
| `count_other_public_safety` | 30 |
| `count_police_services` | 90 |

---

### 4. PLUTO 25v4 — Zoning Districts

**Source:** NYC Department of City Planning, MapPLUTO / PLUTO version 25v4
**NYC Open Data dataset ID:** `64uk-42ks`
**Field used:** `zonedist1` (primary zoning district for each tax lot)
**Script:** `fetch_zoning_2025.py`
**Output:** `data/zoning_2025_raw.csv`

Zoning districts are classified into six categories based on `zonedist1`.
Mixed manufacturing-residential districts (e.g., `M1-2/R6A`) are
classified as manufacturing since M is the primary designation. `PARK`
is split into its own category rather than being folded into `other`.

| Category | zonedist1 values | Description |
|---|---|---|
| `residential` | R1-1 through R10H | All R zoning districts |
| `commercial` | C1-1 through C8-4 | All C zoning districts |
| `manufacturing` | M1-1 through M3-2, MX zones | All M zoning districts including mixed-use MX |
| `park` | PARK | Park-zoned lots |
| `other` | BPC, etc. | Other special purpose designations |
| `unzoned` | null | Streets, water, unassigned lots |

#### Variables collected (per category `{cat}`)

| Column | Description |
|---|---|
| `lot_area_zoned_{cat}` | Total lot area (sq ft) in this zoning category |
| `pct_lot_area_zoned_{cat}` | Share of total lot area (%) |
| `lots_zoned_{cat}` | Number of tax lots in this zoning category |
| `total_lot_area_zoned` | Sum across all zoning categories |
| `dominant_zone` | Most common specific zoning district in the CD by lot area |

---

### 5. NYPD Complaint Data — 2024 Major Felonies

**Source:** NYC Police Department, Complaint Data Historic
**NYC Open Data dataset ID:** `qgea-i56i`
**Script:** `fetch_nypd_2024.py`
**Output:** `data/nypd_2024_raw.csv`

#### Crime types included

Only the **7 major felony offenses** are counted, matching the methodology used in
the original DCP `cd_profiles_v202402`:

| `ky_cd` | Offense type |
|---|---|
| 101 | Murder & Non-Negligent Manslaughter |
| 104 | Rape |
| 105 | Robbery |
| 106 | Felony Assault |
| 107 | Burglary |
| 109 | Grand Larceny |
| 110 | Grand Larceny of Motor Vehicle |

#### Variables collected

| Column | Description |
|---|---|
| `crime_count` | Count of 7 major felony complaints in 2024 |
| `crime_per_1000` | `crime_count` per 1,000 residents (using ACS 2020-2024 population) |

**2024 citywide total (residential CDs):** 119,296 major felony complaints.
**Citywide median:** 12.4 crimes per 1,000 residents.

#### Geographic assignment

The NYPD complaint dataset does not include a Community District field.
Each complaint is geocoded to a CD via the Socrata **computed region**
`:@computed_region_f5dn_yrer`, which spatially pre-joins each complaint's
lat/lon to the NYC Community District polygon it falls within (using dataset
`f5dn-yrer`, which maps spatial feature IDs to `borocd` values).

---

### 6. Median Household Income — ACS 2020-2024

**Source:** U.S. Census Bureau, ACS 5-Year Estimates 2020-2024
**Tables:** B19013 (PUMA-level published median), B19001 (tract-level income brackets)
**API endpoint:** `https://api.census.gov/data/2024/acs/acs5`
**Script:** `fetch_acs_2024_income.py`
**Output:** `data/acs_2024_income.csv`
**Cache:** `data/acs_2024_income_raw.csv` (raw tract B19001 bracket counts)

Two estimates are produced because `B19013` (the Census-published median) is only
available at the PUMA level — which means shared-PUMA CD pairs receive identical
values. The interpolated estimate (`mdn_hh_inc_interp`) uses tract-level data to
produce distinct values for all 59 CDs.

#### Variables collected

| Column | Description |
|---|---|
| `mdn_hh_inc_puma` | Census-published median household income at PUMA level (B19013_001E), assigned to each CD via its PUMA code. Shared-PUMA pairs share the same value. |
| `mdn_hh_inc_puma_moe` | Margin of error for `mdn_hh_inc_puma` (90%), from B19013_001M |
| `mdn_hh_inc_interp` | CD-level median interpolated from B19001 bracket counts aggregated from census tracts (see methodology below). Distinct for all 59 CDs. |
| `total_households` | Total households in the CD from B19001_001E (tract-aggregated) |
| `median_bracket` | 0-based index of the income bracket containing the median (0 = < $10k, 15 = ≥$200k) |

---

## Methodology: Median Household Income Interpolation

Census table B19001 publishes household counts in 16 income brackets for each census
tract. These bracket counts are aggregated to CD level using the same PLUTO `bct2020→cd`
crosswalk as the ACS demographic variables. The CD-level median is then estimated via
**Pareto-linear interpolation**.

### B19001 income brackets

| Variable | Range | Lower bound (L) | Width (w) |
|---|---|---|---|
| B19001_002E | < $10,000 | $0 | $10,000 |
| B19001_003E | $10,000–$14,999 | $10,000 | $5,000 |
| B19001_004E | $15,000–$19,999 | $15,000 | $5,000 |
| B19001_005E | $20,000–$24,999 | $20,000 | $5,000 |
| B19001_006E | $25,000–$29,999 | $25,000 | $5,000 |
| B19001_007E | $30,000–$34,999 | $30,000 | $5,000 |
| B19001_008E | $35,000–$39,999 | $35,000 | $5,000 |
| B19001_009E | $40,000–$44,999 | $40,000 | $5,000 |
| B19001_010E | $45,000–$49,999 | $45,000 | $5,000 |
| B19001_011E | $50,000–$59,999 | $50,000 | $10,000 |
| B19001_012E | $60,000–$74,999 | $60,000 | $15,000 |
| B19001_013E | $75,000–$99,999 | $75,000 | $25,000 |
| B19001_014E | $100,000–$124,999 | $100,000 | $25,000 |
| B19001_015E | $125,000–$149,999 | $125,000 | $25,000 |
| B19001_016E | $150,000–$199,999 | $150,000 | $50,000 |
| B19001_017E | $200,000 or more | $200,000 | open-ended |

### Standard linear interpolation (brackets 1–15)

For the bracket containing the median (the first bracket where cumulative count ≥ n/2):

```
median = L + ((n/2 − F) / f) × w
```

where:
- `n` = total households in the CD
- `F` = cumulative household count before the median bracket
- `f` = household count in the median bracket
- `L` = lower bound of the bracket
- `w` = width of the bracket

### Pareto tail for the open-ended $200,000+ bracket

When the median falls in the $200k+ bracket, a Pareto distribution is fit to the two
largest brackets to estimate the tail shape:

```
α = log((f₁₆ + f₁₇) / f₁₇) / log(200,000 / 150,000)

median = 200,000 / (1 − rem / f₁₇)^(1/α)
```

where:
- `f₁₆` = household count in the $150,000–$199,999 bracket (B19001_016E)
- `f₁₇` = household count in the $200,000+ bracket (B19001_017E)
- `rem = n/2 − F` = households remaining above the $200,000 lower bound

The Pareto shape parameter α is estimated by assuming the same distributional form
applies across both the $150k–$200k bracket and the $200k+ tail.

### Shared-PUMA handling

Both income estimates use the same PLUTO `bct2020→cd` crosswalk as the ACS demographic
variables. `mdn_hh_inc_interp` therefore produces distinct, CD-specific values for all
four shared-PUMA pairs. `mdn_hh_inc_puma` is the Census-published PUMA-level median and
will be identical for the two CDs in each pair.

### API calls

- **B19001** — 5 calls (one per NYC county), fetching 17 bracket variables per tract.
  Results are cached to `data/acs_2024_income_raw.csv` so subsequent runs skip the API.
- **B19013** — 1 call for all NY state PUMAs (`for=public use microdata area:*`),
  filtered to NYC PUMAs via the `puma_code` field in `acs_2024_raw.csv`.

---

## Output File

### `data/cd_profiles_updated.csv`

**59 rows × 272 columns** — the original 182-column schema extended with new
facility, zoning, and income columns:

| Source | Columns | Version tag |
|---|---|---|
| ACS 2020-2024 | 63 demographic columns (updated) | `v_acs = "ACS 2020-2024"` |
| PLUTO 25v4 — land use | 40 land-use columns (updated) | `v_pluto = "25v4"` |
| FacDB Oct 2025 / Parks Mar 2026 | 71 facility count columns (4 updated, 67 new) | `v_facdb = "FacDB Oct 2025"`, `v_parks = "Parks Mar 2026"` |
| NYPD 2024 | 2 crime columns (updated) | `v_crime = "NYPD 2024"` |
| PLUTO 25v4 — zoning | 17 zoning columns (new) | — |
| ACS 2020-2024 — income | 5 income columns (new) | `v_income = "ACS 2020-2024 (B19001 interpolated)"` |

**Columns NOT updated** (retained from the v202402 original):

| Column group | Reason |
|---|---|
| `pop_2000`, `pop_2010`, `pop_change_00_10` | Decennial Census 2010 spatial aggregation (not re-fetched) |
| `fp_*` (floodplain exposure) | Still based on 2007 FEMA FIRMs; no newer spatial dataset |
| `pct_clean_strts` | DSNY street cleanliness scorecard suspended as of FY2023 |
| `*_boro`, `*_nyc` benchmark columns | Borough/citywide ACS summaries (not re-fetched) |
| `son_issue_*` | Community Board State of the Neighborhood issue rankings; last available structured dataset is FY2020 |
| Geography/admin fields (`borocd`, `borough`, `neighborhoods`, `acres`, `cb_email`, etc.) | Unchanged administrative boundaries and contact information |

---

## Methodology: Shared-PUMA Community Districts

### The problem

The Census Bureau's **Public Use Microdata Areas (PUMAs)** are the smallest geography
for which ACS microdata are published. NYC's 55 PUMAs were designed to each contain
roughly 100,000 people, which means some low-population areas require two Community
Districts to be combined into one PUMA.

**Four PUMA pairs** cover two Community Districts each:

| PUMA code | Community Districts |
|---|---|
| 04121 | Manhattan CD 1 (Battery Park City, Tribeca) & CD 2 (Greenwich Village, Soho) |
| 04165 | Manhattan CD 5 (Midtown) & CD 6 (Chelsea, Clinton) |
| 04221 | Bronx CD 1 (Mott Haven, Melrose) & CD 2 (Hunts Point, Longwood) |
| 04263 | Bronx CD 3 (Morrisania, Belmont) & CD 6 (Belmont, East Tremont) |

A naive PUMA-level approach assigns the full PUMA estimate to both CDs in each pair,
producing **identical demographic values** for both districts and **doubling the apparent
population** of each (e.g., both Manhattan CD 1 and CD 2 would show the PUMA's combined
population of ~155,000 rather than their actual ~71,000 and ~85,000 respectively).

This is the approach used by the simpler script `fetch_acs_2024.py`.

### The solution: census tract aggregation

The original DCP `cd_profiles_v202402` resolves this by working at the **2020 census
tract** level — a finer geography where each tract falls entirely within one Community
District. This project replicates that methodology in `fetch_acs_2024_tracts.py`.

#### Step 1 — Build a 2020 census tract → Community District crosswalk

PLUTO 25v4 includes a `bct2020` field (Borough Census Tract 2020) and a `cd` field for
every tax lot in NYC. The crosswalk is built by:

1. Querying PLUTO via Socrata SoQL:
   ```sql
   SELECT bct2020, cd, SUM(lotarea) AS lot_area
   FROM pluto
   WHERE bct2020 IS NOT NULL AND cd IS NOT NULL
   GROUP BY bct2020, cd
   ```
2. For each `bct2020` (2020 census tract), assigning it to the Community District
   with the largest combined lot area. Because NYC census tracts were delineated to
   respect Community District boundaries, each tract falls overwhelmingly (or entirely)
   within a single CD — the lot-area weighting simply resolves any edge cases.

The `bct2020` field is a 7-character code: the first character is the borough digit
(1–5), and the remaining six characters are the zero-padded 2020 Census tract FIPS code.
This directly corresponds to the Census API's `county` + `tract` response fields:

```
bct2020 = COUNTY_TO_BORO[county] + tract.zfill(6)
```

where `COUNTY_TO_BORO` maps NYC county FIPS codes to borough digits:
`{"005": "2", "047": "3", "061": "1", "081": "4", "085": "5"}`.

**Result:** 2,314 unique 2020 census tracts assigned to 59 Community Districts.

#### Step 2 — Fetch ACS 2020-2024 at the census tract level

Raw ACS estimates are fetched from the Census API for all five NYC counties, in three
variable batches (Census API maximum: 50 variables per call, including `NAME`):

| Batch | Variables | Call count |
|---|---|---|
| Batch 1 — demographics | 47 vars: pop, race, nativity, employment, rent burden, commute, poverty, education (E + M) | 5 (one per county) |
| Batch 2 — age pyramid | 49 vars: B01001_001E–049E (Sex by Age, estimate only) | 5 |
| Batch 3 — LEP | 49 vars: B16004_001E + 24 LEP estimates + 24 LEP MOEs | 5 |

**Total: 15 API calls.** The three batches are inner-joined on `bct2020`, keeping only
the 2,327 tracts with complete data across all three batches.

#### Step 3 — Aggregate raw counts from tracts to Community Districts

For each Community District, tracts assigned to it in the crosswalk are aggregated:

- **Estimate variables (`E`):** summed directly.
  `CD_E = Σ tract_E` for all tracts in the CD.

- **Margin-of-error variables (`M`):** aggregated as the square root of the sum of squares
  (the standard Census formula for the MOE of a sum):
  `CD_M = √(Σ tract_M²)` for all tracts in the CD.

This produces CD-level raw counts (numerators and denominators) for every variable.

#### Step 4 — Compute derived rates

All rates and proportions are computed from the aggregated CD-level counts, not from
per-tract rates. This ensures statistical validity:

| Derived variable | Formula |
|---|---|
| `pct_hispanic` | `B03002_012E / B03002_001E × 100` |
| `pct_foreign_born` | `B05002_013E / B05002_001E × 100` |
| `unemployment` | `B23025_005E / B23025_003E × 100` |
| `pct_hh_rent_burd` | `(B25070_007E + 008E + 009E + 010E) / (B25070_001E − B25070_011E) × 100` |
| `mean_commute` | `B08136_001E / (B08301_001E − B08301_021E)` (minutes; excludes WFH workers) |
| `poverty_rate` | `B17001_002E / B17001_001E × 100` |
| `pct_bach_deg` | `(B15003_022E + 023E + 024E + 025E) / B15003_001E × 100` |
| `lep_rate` | `Σ(LEP estimates) / B16004_001E × 100` |
| `under18_rate` | `(male + female under-18 bins) / B01003_001E × 100` |
| `over65_rate` | `(male + female 65+ bins) / B01003_001E × 100` |

**MOEs for proportions** use the standard Census formula:

```
If disc = MOE_num² − p² × MOE_den² ≥ 0:
    MOE_p = √disc / den

Otherwise (additive fallback):
    MOE_p = √(MOE_num² + p² × MOE_den²) / den
```

where `p = num / den`.

#### Results for the shared-PUMA pairs

The following values were computed from the 2020-2024 ACS at the census tract level.
Each row now reflects only the population and characteristics of that specific CD.

| CD | pop_acs | poverty_rate | pct_bach_deg | unemployment | lep_rate |
|---|---|---|---|---|---|
| Manhattan CD 1 | 70,761 | 6.6% | 82.6% | 3.4% | 4.9% |
| Manhattan CD 2 | 84,761 | 8.2% | 85.1% | 5.8% | 4.3% |
| Manhattan CD 5 | 53,570 | 11.9% | 79.0% | 6.1% | 5.8% |
| Manhattan CD 6 | 142,346 | 9.5% | 83.3% | 4.7% | 4.4% |
| Bronx CD 1 | 97,643 | 42.3% | 15.3% | 16.3% | 22.6% |
| Bronx CD 2 | 54,362 | 32.3% | 15.3% | 15.1% | 23.8% |
| Bronx CD 3 | 92,588 | 39.0% | 14.3% | 15.6% | 21.7% |
| Bronx CD 6 | 86,478 | 38.2% | 14.1% | 14.2% | 21.6% |

---

## Scripts

| Script | Purpose | Output |
|---|---|---|
| `fetch.py` | Downloads original DCP v202402 dataset from Carto | `data/cd_profiles_raw.csv` |
| `explore.py` | Explores and documents the original dataset structure | (stdout) |
| `fetch_acs_2024_tracts.py` | **Primary ACS script.** Fetches ACS 2020-2024 at census tract level and aggregates to CD (distinct values for all shared-PUMA pairs) | `data/acs_2024_raw.csv` |
| `fetch_acs_2024.py` | Alternative PUMA-level ACS script (simpler, but produces duplicate values for shared-PUMA pairs) | `data/acs_2024_raw.csv` |
| `fetch_pluto_2025.py` | Aggregates PLUTO 25v4 land-use by CD | `data/pluto_2025_raw.csv` |
| `fetch_facdb_2025.py` | Counts all 70 FacDB facility categories + Parks Properties per CD | `data/facdb_2025_raw.csv` |
| `fetch_zoning_2025.py` | Aggregates PLUTO 25v4 zoning districts (R/C/M/other) by CD | `data/zoning_2025_raw.csv` |
| `fetch_nypd_2024.py` | Counts 2024 7-major-felony complaints per CD | `data/nypd_2024_raw.csv` |
| `fetch_acs_2024_income.py` | Computes two median HH income estimates per CD from B19013 (PUMA) and B19001 (interpolated) | `data/acs_2024_income.csv`, `data/acs_2024_income_raw.csv` |
| `build_updated_profiles.py` | Joins all updated sources into the final output | `data/cd_profiles_updated.csv` |

### Reproduction order

```bash
python3 fetch_acs_2024_tracts.py   # ~2 min (15 Census API calls)
python3 fetch_pluto_2025.py        # ~30 sec
python3 fetch_facdb_2025.py        # ~15 sec
python3 fetch_zoning_2025.py       # ~30 sec
python3 fetch_nypd_2024.py         # ~2 min (large NYPD dataset)
python3 fetch_acs_2024_income.py   # ~1 min (6 Census API calls; cached on re-run)
python3 build_updated_profiles.py  # <5 sec
```

`fetch_acs_2024_tracts.py` reads `data/acs_2024_raw.csv` (if it exists) to carry over
`puma_code` and `shared_puma` metadata, so there is no strict dependency between that
script and the others — they can be run in any order.

---

## Data Files

| File | Rows | Cols | Description |
|---|---|---|---|
| `data/cd_profiles_raw.csv` | 59 | 210 | Original DCP v202402 download (unmodified) |
| `data/cd_profiles_clean.csv` | 59 | 182 | Original with 28 empty/unnamed columns removed |
| `data/acs_2024_raw.csv` | 59 | 69 | ACS 2020-2024 tract-aggregated demographic data |
| `data/pluto_2025_raw.csv` | 59 | 42 | PLUTO 25v4 land-use aggregates |
| `data/facdb_2025_raw.csv` | 59 | 73 | All 70 FacDB facility categories + Parks Properties |
| `data/zoning_2025_raw.csv` | 59 | 19 | Zoning district aggregates (R/C/M/other/unzoned) |
| `data/nypd_2024_raw.csv` | 59 | 5 | NYPD 2024 major felony counts |
| `data/acs_2024_income_raw.csv` | ~2,300 | 18 | Cached tract-level B19001 bracket counts (17 vars + bct2020) |
| `data/acs_2024_income.csv` | 59 | 6 | Median HH income estimates (PUMA-published + interpolated) |
| `data/cd_profiles_updated.csv` | 59 | 272 | **Final output** — original + updated + new columns |

---

## Change Summary vs. Original v202402

Citywide medians across all 59 CDs:

| Metric | Original (v202402) | Updated |
|---|---|---|
| ACS population | 155,000 | 136,000 |
| Unemployment % | 4.3% | 7.7% |
| Poverty rate % | 19.6% | 16.9% |
| Bachelor's degree % | 31.7% | 38.9% |
| Crime per 1,000 residents | 9.4 | 12.4 |

**Note on population:** The median drops from ~155K to ~136K because the PUMA-based
original assigned the full PUMA population to both CDs in each shared pair (inflating
those 8 CDs). The tract-based approach correctly splits population between paired CDs.

**Note on unemployment:** The ACS 2020-2024 period includes the pandemic-era labour
market disruption, raising the citywide median unemployment rate relative to 2014-2018.

**Note on crime:** The 2024 figure (12.4/1,000) reflects 119,296 major felony complaints
versus the original 2019 figure. Both use the same 7 major felony definition.
