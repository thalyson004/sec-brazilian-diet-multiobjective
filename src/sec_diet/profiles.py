"""Describe exact-age dietary profiles without exporting individual records."""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path

from .cohort import FIXED_TAP_WATER_KEY, positive_footprint_keys, residents_from_zip
from .instances import read_json, write_json
from .layout import MIN_RECORD_LENGTH, NUTRIENT_FIELDS, NUTRIENT_START, NUTRIENT_WIDTH, VALID_DAYS, code, field
from .source_checks import consumption_lines, input_info


def profile_lookup(catalogue: dict) -> dict[tuple[int, str], str]:
    if catalogue.get("schema_version") not in {"1.0", "3.0"}:
        raise ValueError("Unsupported dietary-profile catalogue schema")
    lookup, ids = {}, set()
    for profile in catalogue["profiles"]:
        age, sex, identifier = profile["age_years"], profile["sex_code"], profile["profile_id"]
        if not isinstance(age, int) or isinstance(age, bool) or age < 19 or sex not in {"1", "2"}:
            raise ValueError("A profile needs a valid adult age and POF sex code")
        if not isinstance(identifier, str) or not identifier or identifier in ids or (age, sex) in lookup:
            raise ValueError("Profile identifiers and age/sex definitions must be unique")
        lookup[(age, sex)] = identifier
        ids.add(identifier)
    if not lookup:
        raise ValueError("No dietary profiles were defined")
    return lookup


def describe(pof: Path, footprints: Path, catalogue_path: Path) -> dict:
    catalogue = read_json(catalogue_path)
    lookup = profile_lookup(catalogue)
    residents, resident_diagnostics = residents_from_zip(pof)
    positive, additions, footprint_diagnostics = positive_footprint_keys(footprints)
    person_profiles = {identity: lookup[demographics] for identity, demographics in residents.items()
                       if demographics in lookup}
    days, row_counts = {}, Counter()
    nutrient_status = {identifier: {name: Counter() for name in NUTRIENT_FIELDS}
                       for identifier in lookup.values()}
    with consumption_lines(pof) as lines:
        for raw in lines:
            row_counts["source_consumption_rows"] += 1
            record = raw.rstrip(b"\r\n").decode("latin-1")
            if len(record) < MIN_RECORD_LENGTH:
                raise ValueError("A POF consumption record is shorter than the official layout")
            identity = tuple(field(record, name) for name in ("UF", "COD_UPA", "NUM_DOM", "NUM_UC", "COD_INFORMANTE"))
            identifier = person_profiles.get(identity)
            if identifier is None:
                continue
            row_counts["rows_in_requested_profiles"] += 1
            day = field(record, "QUADRO")
            if day not in VALID_DAYS:
                raise ValueError("Unknown day code in a requested profile")
            state = days.setdefault((identity, day), {
                "profile_id": identifier, "valid_quantity": True, "complete_numeric_nutrients": True,
                "environment_complete": True, "known_occasions": True, "occasions": set(),
                "variables": set(), "energy_kcal": 0.0,
            })
            try:
                grams = float(field(record, "QTD"))
            except ValueError:
                grams = math.nan
            state["valid_quantity"] &= math.isfinite(grams) and grams > 0
            for index, name in enumerate(NUTRIENT_FIELDS):
                start = NUTRIENT_START + index * NUTRIENT_WIDTH
                try:
                    value = float(record[start:start + NUTRIENT_WIDTH])
                except ValueError:
                    value = math.nan
                valid = math.isfinite(value) and value >= 0
                status = "positive" if valid and value > 0 else "zero" if valid else "missing_or_invalid"
                nutrient_status[identifier][name][status] += 1
                state["complete_numeric_nutrients"] &= valid
                if name == "ENERGIA_KCAL" and valid:
                    state["energy_kcal"] += value
            food, preparation = code(field(record, "V9001")), code(field(record, "COD_PREPARACAO_FINAL"))
            if (food, preparation) == FIXED_TAP_WATER_KEY:
                continue
            occasion = field(record, "V9017")
            state["known_occasions"] &= occasion in {"1", "2", "3", "4", "5", "6"}
            state["occasions"].add(occasion)
            state["variables"].add((food, preparation, occasion))
            state["environment_complete"] &= food is not None and (food, preparation or "99") in positive
            state["environment_complete"] &= preparation is not None or food in additions

    summaries = []
    for profile in catalogue["profiles"]:
        identifier = profile["profile_id"]
        observed = [(key, state) for key, state in days.items() if state["profile_id"] == identifier]
        eligible = [(key, state) for key, state in observed
                    if all(state[name] for name in ("valid_quantity", "complete_numeric_nutrients",
                                                    "environment_complete", "known_occasions"))
                    and len(state["occasions"]) >= 2 and len(state["variables"]) >= 5 and state["energy_kcal"] > 0]
        summaries.append({
            "profile_id": identifier, "age_years": profile["age_years"], "sex_code": profile["sex_code"],
            "residents_of_requested_age_and_sex": sum(p == identifier for p in person_profiles.values()),
            "respondents_with_consumption": len({key[0] for key, _ in observed}),
            "observed_days": len(observed), "eligible_days": len(eligible),
            "respondents_with_eligible_days": len({key[0] for key, _ in eligible}),
            "eligible_food_preparation_occasion_combinations": len(set().union(*(s["variables"] for _, s in eligible))),
            "nutrient_record_status": {name: {status: nutrient_status[identifier][name][status]
                                               for status in ("positive", "zero", "missing_or_invalid")}
                                      for name in NUTRIENT_FIELDS},
        })
    return {
        "schema_version": "1.0", "study_id": catalogue["study_id"],
        "inputs": {"pof": input_info(pof), "footprints": input_info(footprints), "catalogue": input_info(catalogue_path)},
        "source_counts": dict(row_counts), "resident_checks": resident_diagnostics,
        "footprint_checks": footprint_diagnostics, "profiles": summaries,
        "selection": "Exact age and recorded sex. Counts include both recorded days; eligible respondents count each person once. No age-band widening or anthropometric imputation.",
        "interpretation": "Numerical presence of nutrient values is not confirmation that every reported zero is a measured absence. This characterization does not define nutrient targets or run optimization.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pof", type=Path, required=True)
    parser.add_argument("--footprints", type=Path, required=True)
    parser.add_argument("--catalogue", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    for name in ("pof", "footprints", "catalogue"):
        if not getattr(args, name).is_file():
            parser.error(f"Missing {name} input")
    result = describe(args.pof, args.footprints, args.catalogue)
    write_json(args.output, result)
    print(json.dumps({"profiles": [{k: row[k] for k in ("profile_id", "eligible_days", "respondents_with_eligible_days")}
                                  for row in result["profiles"]]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
