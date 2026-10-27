"""Validate adult POF person-days and select reproducible benchmark instances.

Only aggregate diagnostics and opaque person-day identifiers are exported.
Nutrient and environmental coefficients are never written by this command.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from openpyxl import load_workbook

from .source_checks import FOOTPRINT_SHEET, FOOTPRINT_URL, POF_DATA_URL, consumption_lines, input_info, numeric_coefficient
from .extract import person_day_id
from .layout import MIN_RECORD_LENGTH, NUTRIENT_FIELDS, NUTRIENT_START, NUTRIENT_WIDTH, VALID_DAYS, code, field

AGE_MIN = 19
AGE_MAX = 59
MIN_FOOD_OCCASION_KEYS = 5
MIN_OCCASIONS = 2
PER_STRATUM = 6
MODEL_NUTRIENTS = ("ENERGIA_KCAL", "FIBRA", "SODIO")
NUTRIENT_INDEX = {name: NUTRIENT_FIELDS.index(name) for name in MODEL_NUTRIENTS}
FIXED_TAP_WATER_KEY = ("8216301", "99")


def residents_from_zip(path: Path) -> tuple[dict[tuple[str, ...], tuple[int, str]], dict]:
    if path.suffix.lower() != ".zip":
        raise ValueError("The cohort validation requires the official POF data ZIP with MORADOR.txt")
    residents: dict[tuple[str, ...], tuple[int, str]] = {}
    counts: Counter = Counter()
    with zipfile.ZipFile(path) as archive:
        members = [name for name in archive.namelist() if Path(name).name.upper() == "MORADOR.TXT"]
        if len(members) != 1:
            raise ValueError(f"Expected one MORADOR.txt member; found {len(members)}")
        with archive.open(members[0]) as stream:
            for raw in stream:
                counts["records"] += 1
                record = raw.rstrip(b"\r\n").decode("latin-1")
                if len(record) < 36:
                    counts["short_records"] += 1
                    continue
                identity = tuple(field(record, name) for name in ("UF", "COD_UPA", "NUM_DOM", "NUM_UC", "COD_INFORMANTE"))
                if any(not part for part in identity):
                    counts["incomplete_identity_records"] += 1
                    continue
                age_raw, sex = record[32:35].strip(), record[35:36].strip()
                if not age_raw.isdigit() or sex not in {"1", "2"}:
                    counts["invalid_age_or_sex_records"] += 1
                    continue
                person = (int(age_raw), sex)
                if identity in residents:
                    if residents[identity] != person:
                        raise ValueError("Conflicting MORADOR age/sex values for a respondent key")
                    counts["duplicate_respondent_key_records"] += 1
                residents[identity] = person
    return residents, dict(sorted(counts.items()))


def positive_footprint_keys(path: Path) -> tuple[set[tuple[str, str]], set[str], dict]:
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        if FOOTPRINT_SHEET not in book.sheetnames:
            raise ValueError(f"Missing workbook sheet {FOOTPRINT_SHEET}")
        keys: dict[tuple[str, str], tuple[str, str]] = {}
        preparations: dict[str, set[str]] = defaultdict(set)
        duplicates: set[tuple[str, str]] = set()
        for row in book[FOOTPRINT_SHEET].iter_rows(min_row=4, values_only=True):
            if not row or not isinstance(row[0], (int, float)):
                continue
            food, preparation = code(row[0]), code(row[2] if len(row) > 2 else None)
            if food is None or preparation is None:
                continue
            key = (food, preparation)
            preparations[food].add(preparation)
            if key in keys:
                duplicates.add(key)
            else:
                keys[key] = (numeric_coefficient(row[4]), numeric_coefficient(row[5]))
        positive = {key for key, status in keys.items() if status == ("positive", "positive") and key not in duplicates}
        if keys.get(FIXED_TAP_WATER_KEY) != ("zero", "zero") or FIXED_TAP_WATER_KEY in duplicates:
            raise ValueError("Expected the documented tap-water key to have unique zero carbon and water coefficients")
        additions = {food for food, prep in preparations.items() if prep == {"99"} and (food, "99") in positive}
        return positive, additions, {
            "positive_food_preparation_keys": len(positive),
            "blank_addition_foods_with_unique_positive_99_crosswalk": len(additions),
            "duplicate_food_preparation_keys": len(duplicates),
            "fixed_tap_water_key": "8216301#99",
        }
    finally:
        book.close()


def nutrient_value(record: str, name: str) -> float:
    start = NUTRIENT_START + NUTRIENT_INDEX[name] * NUTRIENT_WIDTH
    return float(record[start : start + NUTRIENT_WIDTH])


def inspect_days(path: Path, positive_keys: set[tuple[str, str]], addition_foods: set[str]) -> tuple[dict, dict]:
    days: dict[tuple[str, ...], dict] = {}
    tbca_by_food: dict[tuple[str, str | None], set[str]] = defaultdict(set)
    first_ratio: dict[str, dict[tuple[str, str | None], float]] = {name: {} for name in MODEL_NUTRIENTS}
    variable_keys: dict[str, set[tuple[str, str | None]]] = {name: set() for name in MODEL_NUTRIENTS}
    zero_disagreement_keys: dict[str, set[tuple[str, str | None]]] = {name: set() for name in MODEL_NUTRIENTS}
    counts: Counter = Counter()
    with consumption_lines(path) as lines:
        for raw in lines:
            counts["source_records"] += 1
            record = raw.rstrip(b"\r\n").decode("latin-1")
            if len(record) < MIN_RECORD_LENGTH or field(record, "QUADRO") not in VALID_DAYS:
                counts["invalid_layout_or_day_records"] += 1
                continue
            identity = tuple(field(record, name) for name in ("UF", "COD_UPA", "NUM_DOM", "NUM_UC", "COD_INFORMANTE", "QUADRO"))
            if any(not part for part in identity):
                counts["incomplete_identity_records"] += 1
                continue
            state = days.setdefault(identity, {
                "rows": 0, "environment_complete": True, "food_occasion_keys": set(),
                "occasions": set(), "unknown_occasion": False, "energy_positive": False,
            })
            state["rows"] += 1
            food = code(field(record, "V9001"))
            preparation = code(field(record, "COD_PREPARACAO_FINAL"))
            if (food, preparation) == FIXED_TAP_WATER_KEY:
                counts["fixed_tap_water_records"] += 1
                if nutrient_value(record, "SODIO") > 0:
                    counts["fixed_tap_water_records_with_positive_reported_sodium"] += 1
                continue
            occasion = field(record, "V9017")
            if occasion not in {"1", "2", "3", "4", "5", "6"}:
                state["unknown_occasion"] = True
            else:
                state["occasions"].add(occasion)
            if food is None:
                state["environment_complete"] = False
                counts["invalid_food_records"] += 1
                continue
            state["food_occasion_keys"].add((food, preparation, occasion))
            environmental_key = (food, preparation or "99")
            if preparation is None and food not in addition_foods:
                state["environment_complete"] = False
            elif environmental_key not in positive_keys:
                state["environment_complete"] = False
            raw_quantity = field(record, "QTD")
            try:
                grams = float(raw_quantity)
            except ValueError:
                state["environment_complete"] = False
                counts["invalid_quantity_records"] += 1
                continue
            if not math.isfinite(grams) or grams <= 0:
                state["environment_complete"] = False
                counts["nonpositive_quantity_records"] += 1
                continue
            key = (food, preparation)
            tbca_by_food[key].add(field(record, "COD_TBCA"))
            for name in MODEL_NUTRIENTS:
                try:
                    amount = nutrient_value(record, name)
                except ValueError:
                    state["environment_complete"] = False
                    counts[f"invalid_{name}_records"] += 1
                    continue
                if not math.isfinite(amount) or amount < 0:
                    state["environment_complete"] = False
                    counts[f"invalid_{name}_records"] += 1
                    continue
                if name == "ENERGIA_KCAL" and amount > 0:
                    state["energy_positive"] = True
                ratio = amount * 100.0 / grams
                first = first_ratio[name].setdefault(key, ratio)
                if (first == 0) != (ratio == 0):
                    zero_disagreement_keys[name].add(key)
                elif first and ratio and abs(ratio - first) > 0.05 * max(ratio, first):
                    variable_keys[name].add(key)
    diagnostics = {
        "counts": dict(sorted(counts.items())),
        "distinct_food_preparation_keys_including_blank_additions": len(tbca_by_food),
        "food_preparation_keys_with_multiple_tbca_identifiers": sum(len(ids) > 1 for ids in tbca_by_food.values()),
        "nutrient_coefficient_consistency": {
            name: {
                "keys_with_zero_positive_disagreement": len(zero_disagreement_keys[name]),
                "keys_with_over_five_percent_per_100g_difference": len(variable_keys[name]),
            }
            for name in MODEL_NUTRIENTS
        },
        "note": "Per-100-g consistency is checked within POF food/preparation keys using recorded absolute amounts divided by grams. A five-percent difference is a diagnostic threshold, not an imputation rule. No coefficient values are exported.",
    }
    return days, diagnostics


def select_instances(days: dict, residents: dict) -> dict:
    stages: Counter = Counter()
    first_day_per_respondent: dict[tuple[str, ...], tuple[str, ...]] = {}
    age_bands = ((19, 39), (40, 59))
    for identity in sorted(days):
        stages["person_days_with_records"] += 1
        resident = residents.get(identity[:5])
        if resident is None:
            continue
        stages["matched_resident"] += 1
        age, sex = resident
        if not AGE_MIN <= age <= AGE_MAX:
            continue
        stages["adult_19_to_59"] += 1
        state = days[identity]
        if not state["environment_complete"]:
            continue
        stages["all_environmental_coefficients_strictly_positive"] += 1
        if state["unknown_occasion"]:
            continue
        stages["all_occasion_codes_known"] += 1
        if len(state["occasions"]) < MIN_OCCASIONS:
            continue
        stages["at_least_two_occasions"] += 1
        if len(state["food_occasion_keys"]) < MIN_FOOD_OCCASION_KEYS:
            continue
        stages["at_least_five_food_occasion_keys"] += 1
        if not state["energy_positive"]:
            continue
        stages["positive_observed_energy"] += 1
        first_day_per_respondent.setdefault(identity[:5], identity)
    stages["one_eligible_day_per_respondent"] = len(first_day_per_respondent)

    strata: dict[tuple[str, str], list[tuple[str, ...]]] = defaultdict(list)
    for identity in first_day_per_respondent.values():
        age, sex = residents[identity[:5]]
        band = next(f"{low}-{high}" for low, high in age_bands if low <= age <= high)
        strata[(band, sex)].append(identity)
    selected = []
    available = {}
    for (band, sex), identities in sorted(strata.items()):
        label = f"age_{band}_sex_{sex}"
        available[label] = len(identities)
        if len(identities) < PER_STRATUM:
            raise ValueError(f"Stratum {label} has only {len(identities)} eligible respondents")
        identities.sort(key=lambda parts: hashlib.sha256(("sec2026-benchmark-v1|" + "|".join(parts)).encode("ascii")).hexdigest())
        for identity in identities[:PER_STRATUM]:
            selected.append({
                "person_day_id": person_day_id(identity),
                "age_band": band,
                "sex_code": sex,
                "day": int(VALID_DAYS[identity[5]]),
                "food_occasion_variables": len(days[identity]["food_occasion_keys"]),
            })
    if len(selected) != 4 * PER_STRATUM:
        raise ValueError(f"Expected {4 * PER_STRATUM} selected instances; found {len(selected)}")
    return {
        "ordered_filter_counts": dict(stages),
        "eligible_respondents_by_stratum": available,
        "selected_instances": selected,
        "selection": {
            "population": "POF respondents aged 19-59 with sex code 1 or 2 in MORADOR.txt",
            "environment": "Every optimized food line has strictly positive carbon and water coefficients; blank addition lines use the unique preparation-99 workbook row. Public tap water 8216301#99 is fixed outside the decision vector and excluded from the departure denominator. Its reported nutrient contribution remains in modeled daily totals.",
            "occasions": "All occasion codes are 1-6, at least two distinct occasions",
            "minimum_variables": MIN_FOOD_OCCASION_KEYS,
            "observed_energy": "At least one positive ENERGIA_KCAL amount",
            "repeated_days": "First eligible QUADRO in code order, 72 then 73, per respondent",
            "sampling": "Six lowest SHA-256 ranks of sec2026-benchmark-v1| plus the six-part source key in each sex-by-age stratum",
            "strata": ["age 19-39, sex 1", "age 19-39, sex 2", "age 40-59, sex 1", "age 40-59, sex 2"],
        },
        "note": "The 24 days form an algorithm benchmark, not a probability sample for Brazilian population estimates. The manifest publishes no food or nutrient quantities.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pof", type=Path, required=True, help="Official Dados_20230713.zip")
    parser.add_argument("--footprints", type=Path, required=True, help="OSF environmental workbook")
    parser.add_argument("--output", type=Path, required=True, help="Aggregate cohort validation and opaque benchmark identifiers")
    args = parser.parse_args(argv)
    for name in ("pof", "footprints"):
        if not getattr(args, name).is_file():
            parser.error(f"{name} input not found: {getattr(args, name)}")
    residents, resident_diagnostics = residents_from_zip(args.pof)
    positive, additions, environmental_diagnostics = positive_footprint_keys(args.footprints)
    days, consumption_diagnostics = inspect_days(args.pof, positive, additions)
    report = {
        "schema_version": "1.0",
        "validation_date": date.today().isoformat(),
        "inputs": {
            "pof": input_info(args.pof, POF_DATA_URL),
            "footprints": input_info(args.footprints, FOOTPRINT_URL),
        },
        "residents": resident_diagnostics,
        "environment": environmental_diagnostics,
        "consumption": consumption_diagnostics,
        "cohort": select_instances(days, residents),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote cohort validation to {args.output}")
    print(f"Eligible respondents: {report['cohort']['ordered_filter_counts']['one_eligible_day_per_respondent']}")
    print(f"Selected benchmark instances: {len(report['cohort']['selected_instances'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
