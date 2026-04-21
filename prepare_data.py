#!/usr/bin/env python3
"""Prepare a slim browser-friendly JSON bundle for the CD explorer."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from statistics import median


ROOT = Path(__file__).resolve().parent
INPUT_CSV = ROOT / "data" / "cd_profiles_updated.csv"
OUTPUT_JSON = ROOT / "explorer" / "data" / "cd_profiles.json"

AGE_BINS = [
    "under_5",
    "5_9",
    "10_14",
    "15_19",
    "20_24",
    "25_29",
    "30_34",
    "35_39",
    "40_44",
    "45_49",
    "50_54",
    "55_59",
    "60_64",
    "65_69",
    "70_74",
    "75_79",
    "80_84",
    "85_over",
]

PROFILE_FIELDS = [
    "pop_acs",
    "pct_hispanic",
    "pct_white_nh",
    "pct_black_nh",
    "pct_asian_nh",
    "pct_other_nh",
    "pct_foreign_born",
    "lep_rate",
    "under18_rate",
    "over65_rate",
    *[f"male_{age_bin}" for age_bin in AGE_BINS],
    *[f"female_{age_bin}" for age_bin in AGE_BINS],
    "mdn_hh_inc_interp",
    "mdn_hh_inc_puma",
    "total_households",
    "poverty_rate",
    "pct_hh_rent_burd",
    "pct_bach_deg",
    "unemployment",
    "mean_commute",
    "moe_poverty_rate",
    "moe_bach_deg",
    "moe_hh_rent_burd",
    "moe_foreign_born",
    "moe_unemployment",
    "moe_mean_commute",
    "moe_lep_rate",
    "pct_lot_area_res_1_2_family_bldg",
    "pct_lot_area_res_multifamily_walkup",
    "pct_lot_area_res_multifamily_elevator",
    "pct_lot_area_mixed_use",
    "pct_lot_area_commercial_office",
    "pct_lot_area_industrial_manufacturing",
    "pct_lot_area_open_space",
    "pct_lot_area_transportation_utility",
    "pct_lot_area_public_facility_institution",
    "pct_lot_area_parking",
    "pct_lot_area_vacant",
    "pct_lot_area_other_no_data",
    "pct_lot_area_zoned_residential",
    "pct_lot_area_zoned_commercial",
    "pct_lot_area_zoned_manufacturing",
    "pct_lot_area_zoned_park",
    "pct_lot_area_zoned_other",
    "pct_lot_area_zoned_unzoned",
    "dominant_zone",
    "cd_tot_bldgs",
    "cd_tot_resunits",
    "total_lot_area",
    "count_parks",
    "count_public_schools",
    "count_libraries",
    "count_hosp_clinic",
    "count_day_care",
    "count_senior_services",
    "crime_count",
    "crime_per_1000",
    "son_issue_1",
    "son_issue_2",
    "son_issue_3",
]

MEDIAN_FIELDS = [
    "mdn_hh_inc_interp",
    "poverty_rate",
    "pct_hh_rent_burd",
    "pct_bach_deg",
    "pct_foreign_born",
    "lep_rate",
    "over65_rate",
    "mean_commute",
    "unemployment",
    "crime_per_1000",
]

INT_FIELDS = {
    "borocd",
    "cd_num",
    "pop_acs",
    "total_households",
    "cd_tot_bldgs",
    "cd_tot_resunits",
    "count_parks",
    "count_public_schools",
    "count_libraries",
    "count_hosp_clinic",
    "count_day_care",
    "count_senior_services",
    "crime_count",
    *[f"male_{age_bin}" for age_bin in AGE_BINS],
    *[f"female_{age_bin}" for age_bin in AGE_BINS],
}

FLOAT_FIELDS = set(PROFILE_FIELDS) | set(MEDIAN_FIELDS)
FLOAT_FIELDS -= {"dominant_zone", "son_issue_1", "son_issue_2", "son_issue_3"}
FLOAT_FIELDS -= INT_FIELDS

BOROUGH_NAMES = {
    1: "Manhattan",
    2: "Bronx",
    3: "Brooklyn",
    4: "Queens",
    5: "Staten Island",
}


def parse_bool(value: str | None) -> bool:
    return str(value).strip().lower() == "true"


def parse_value(field: str, raw_value: str | None):
    if raw_value in (None, "", "NA", "NaN"):
        return None
    if field in INT_FIELDS:
        return int(round(float(raw_value)))
    if field in FLOAT_FIELDS:
        return round(float(raw_value), 2)
    return raw_value


def profile_name(borocd: int) -> str:
    borough_code = borocd // 100
    return f"{BOROUGH_NAMES[borough_code]} CD {borocd % 100}"


def build_profiles():
    with INPUT_CSV.open(newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    if len(rows) != 59:
        raise ValueError(f"Expected 59 rows, found {len(rows)}")

    profiles = []
    citywide_male = [0] * len(AGE_BINS)
    citywide_female = [0] * len(AGE_BINS)

    for row in rows:
        borocd = int(row["borocd"])
        profile = {
            "borocd": borocd,
            "borough": row["borough"],
            "cd_num": borocd % 100,
            "name": profile_name(borocd),
            "neighborhoods": row["neighborhoods"],
            "shared_puma": parse_bool(row.get("shared_puma")),
            "puma_partner": profile_name(int(row["shared_puma_cd"]))
            if row.get("shared_puma_cd")
            else None,
        }

        for field in PROFILE_FIELDS:
            profile[field] = parse_value(field, row.get(field))

        for idx, age_bin in enumerate(AGE_BINS):
            citywide_male[idx] += profile[f"male_{age_bin}"] or 0
            citywide_female[idx] += profile[f"female_{age_bin}"] or 0

        profiles.append(profile)

    profiles.sort(key=lambda item: item["borocd"])

    medians = {
        field: round(median(profile[field] for profile in profiles if profile[field] is not None), 2)
        for field in MEDIAN_FIELDS
    }

    male_total = sum(citywide_male)
    female_total = sum(citywide_female)
    total_population = male_total + female_total
    medians["citywide_pyramid"] = {
        "male": [round(value / total_population * 100, 2) if total_population else 0 for value in citywide_male],
        "female": [round(value / total_population * 100, 2) if total_population else 0 for value in citywide_female],
    }

    return {"profiles": profiles, "medians": medians}


def main():
    payload = build_profiles()
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"Wrote {len(payload['profiles'])} profiles to {OUTPUT_JSON}")


if __name__ == "__main__":
    main()
