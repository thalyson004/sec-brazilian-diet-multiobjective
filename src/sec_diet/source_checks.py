"""Validate POF consumption records and environmental coefficient coverage.

This command writes aggregate diagnostics only. It never exports respondent
records, food-level nutrient values, or environmental coefficients.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
import zipfile
from collections import Counter
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Iterator

from openpyxl import load_workbook

from .layout import MIN_RECORD_LENGTH, NUTRIENT_FIELDS, NUTRIENT_START, NUTRIENT_WIDTH, VALID_DAYS, code, field

POF_DATA_URL = (
    "https://ftp.ibge.gov.br/Orcamentos_Familiares/"
    "Pesquisa_de_Orcamentos_Familiares_2017_2018/Microdados/Dados_20230713.zip"
)
POF_DOCUMENTATION_URL = (
    "https://ftp.ibge.gov.br/Orcamentos_Familiares/"
    "Pesquisa_de_Orcamentos_Familiares_2017_2018/Microdados/Documentacao_20230713.zip"
)
FOOTPRINT_URL = "https://osf.io/download/fv3tx/"
FOOTPRINT_SHEET = "Tab_Preparacoes_100g_2018"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def input_info(path: Path, url: str | None = None) -> dict:
    info = {"filename": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
    if url:
        info["source_url"] = url
    return info


@contextmanager
def consumption_lines(path: Path) -> Iterator[Iterator[bytes]]:
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as archive:
            members = [name for name in archive.namelist() if Path(name).name.upper() == "CONSUMO_ALIMENTAR.TXT"]
            if len(members) != 1:
                raise ValueError(f"Expected one CONSUMO_ALIMENTAR.txt member; found {len(members)}")
            with archive.open(members[0]) as stream:
                yield stream
    else:
        with path.open("rb") as stream:
            yield stream


def validation_consumption(path: Path) -> tuple[dict, Counter, Counter]:
    counts: Counter = Counter()
    day_rows: Counter = Counter()
    occasion_rows: Counter = Counter()
    quantity_bins: Counter = Counter()
    food_rows: Counter = Counter()
    blank_addition_rows: Counter = Counter()
    nutrient_status: dict[str, Counter] = {name: Counter() for name in NUTRIENT_FIELDS}
    person_days: set[tuple[str, ...]] = set()
    respondents: set[tuple[str, ...]] = set()
    line_digests: set[bytes] = set()
    max_grams = 0.0
    min_positive_grams = math.inf

    with consumption_lines(path) as lines:
        for raw_line in lines:
            counts["records"] += 1
            record = raw_line.rstrip(b"\r\n").decode("latin-1")
            if len(record) < MIN_RECORD_LENGTH:
                counts["short_records"] += 1
                continue

            digest = hashlib.blake2b(raw_line, digest_size=16).digest()
            if digest in line_digests:
                counts["exact_duplicate_lines"] += 1
            else:
                line_digests.add(digest)

            quadro = field(record, "QUADRO")
            day_rows[quadro or "blank"] += 1
            if quadro not in VALID_DAYS:
                counts["invalid_day_rows"] += 1
                continue

            identity = tuple(field(record, name) for name in ("UF", "COD_UPA", "NUM_DOM", "NUM_UC", "COD_INFORMANTE"))
            if any(not part for part in identity):
                counts["incomplete_respondent_key_rows"] += 1
                continue
            respondents.add(identity)
            person_days.add((*identity, quadro))

            food = code(field(record, "V9001"))
            preparation_raw = field(record, "COD_PREPARACAO_FINAL")
            preparation = code(preparation_raw)
            if food is None:
                counts["invalid_food_code_rows"] += 1
            if not preparation_raw:
                counts["blank_preparation_rows"] += 1
            elif preparation is None:
                counts["invalid_preparation_rows"] += 1
            if not field(record, "COD_TBCA"):
                counts["blank_tbca_identifier_rows"] += 1

            occasion = field(record, "V9017")
            occasion_rows[occasion or "blank"] += 1
            if not field(record, "V9015"):
                counts["blank_time_rows"] += 1

            quantity_raw = field(record, "QTD")
            if not quantity_raw:
                counts["blank_quantity_rows"] += 1
                continue
            try:
                grams = float(quantity_raw)
            except ValueError:
                counts["invalid_quantity_rows"] += 1
                continue
            if not math.isfinite(grams):
                counts["nonfinite_quantity_rows"] += 1
                continue
            if grams <= 0:
                counts["nonpositive_quantity_rows"] += 1
                continue

            counts["positive_quantity_rows"] += 1
            complete_embedded_nutrients = True
            for index, name in enumerate(NUTRIENT_FIELDS):
                start = NUTRIENT_START + index * NUTRIENT_WIDTH
                status = numeric_coefficient(record[start : start + NUTRIENT_WIDTH])
                nutrient_status[name][status] += 1
                complete_embedded_nutrients &= status in {"zero", "positive"}
            if complete_embedded_nutrients:
                counts["rows_with_all_embedded_nutrients_numeric"] += 1
            max_grams = max(max_grams, grams)
            min_positive_grams = min(min_positive_grams, grams)
            if grams > 5000:
                quantity_bins[">5000 g"] += 1
            elif grams > 1000:
                quantity_bins["1000-5000 g"] += 1
            elif grams > 500:
                quantity_bins["500-1000 g"] += 1
            else:
                quantity_bins["<=500 g"] += 1

            if food is not None and preparation is not None:
                food_rows[(food, preparation)] += 1
            elif food is not None and not preparation_raw:
                blank_addition_rows[food] += 1
            else:
                counts["positive_rows_without_full_food_key"] += 1

    summary = {
        "counts": dict(sorted(counts.items())),
        "records_by_quadro": dict(sorted(day_rows.items())),
        "records_by_eating_occasion": dict(sorted(occasion_rows.items())),
        "respondents_with_records": len(respondents),
        "person_days_with_records": len(person_days),
        "distinct_food_preparation_keys_with_positive_quantity": len(food_rows),
        "distinct_food_codes_with_blank_preparation": len(blank_addition_rows),
        "quantity_diagnostics": {
            "unit": "g per consumption record, as labeled in the IBGE dictionary",
            "min_positive_g": None if min_positive_grams == math.inf else min_positive_grams,
            "max_positive_g": max_grams if counts["positive_quantity_rows"] else None,
            "bins": dict(sorted(quantity_bins.items())),
            "note": "The 1000 g and 5000 g thresholds flag records for review; no records are excluded by them.",
        },
        "embedded_nutrients": {
            "source": "Absolute nutrient quantities in each IBGE CONSUMO_ALIMENTAR record, not independently verified per-100-g composition coefficients",
            "fields": {name: dict(sorted(status.items())) for name, status in nutrient_status.items()},
            "note": "The IBGE dictionary warns that some zero nutrient values can mean near zero or not examined. Numeric coverage does not establish a valid coefficient for a candidate food or permission to redistribute TBCA-derived values. No nutrient amounts are exported.",
        },
        "selection": "All valid respondent-day records with positive numeric QTD are checked. No age, meal, or nutrient filter has been applied.",
    }
    return summary, food_rows, blank_addition_rows


def numeric_coefficient(value: object) -> str:
    if value is None or str(value).strip() == "":
        return "missing"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "invalid"
    if not math.isfinite(number) or number < 0:
        return "invalid"
    return "zero" if number == 0 else "positive"


def validation_footprints(path: Path, food_rows: Counter, blank_addition_rows: Counter) -> tuple[dict, dict, set[str]]:
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        if FOOTPRINT_SHEET not in book.sheetnames:
            raise ValueError(f"Missing sheet {FOOTPRINT_SHEET!r}; available: {book.sheetnames}")
        sheet = book[FOOTPRINT_SHEET]
        counts: Counter = Counter()
        keys: dict[tuple[str, str], tuple[str, str]] = {}
        preparations_by_food: dict[str, set[str]] = {}
        duplicate_keys: set[tuple[str, str]] = set()
        for row in sheet.iter_rows(min_row=4, values_only=True):
            if not row or not isinstance(row[0], (int, float)):
                continue
            counts["data_rows"] += 1
            food = code(row[0])
            preparation = code(row[2] if len(row) > 2 else None)
            if food is None or preparation is None:
                counts["rows_without_full_food_key"] += 1
                continue
            key = (food, preparation)
            preparations_by_food.setdefault(food, set()).add(preparation)
            if key in keys:
                duplicate_keys.add(key)
                counts["duplicate_key_rows"] += 1
                continue
            carbon = numeric_coefficient(row[4] if len(row) > 4 else None)
            water = numeric_coefficient(row[5] if len(row) > 5 else None)
            keys[key] = (carbon, water)
            counts[f"carbon_{carbon}_rows"] += 1
            counts[f"water_{water}_rows"] += 1

        coverage: Counter = Counter()
        unmatched_keys: list[str] = []
        for key, consumption_count in food_rows.items():
            if key in duplicate_keys:
                status = "ambiguous_key"
            elif key not in keys:
                status = "unmatched_key"
                unmatched_keys.append(f"{key[0]}#{key[1]}")
            else:
                carbon, water = keys[key]
                status = "carbon_and_water_available" if carbon == water == "positive" else "incomplete_or_zero_coefficient"
                coverage[f"carbon_{carbon}_records"] += consumption_count
                coverage[f"water_{water}_records"] += consumption_count
            coverage[f"{status}_keys"] += 1
            coverage[f"{status}_records"] += consumption_count
        crosswalk_foods: set[str] = set()
        for food, consumption_count in blank_addition_rows.items():
            candidate = (food, "99")
            if preparations_by_food.get(food) == {"99"} and candidate not in duplicate_keys:
                crosswalk_foods.add(food)
                carbon, water = keys[candidate]
                coverage["blank_addition_codes_with_unique_99_crosswalk"] += 1
                coverage["blank_addition_records_with_unique_99_crosswalk"] += consumption_count
                coverage[f"blank_addition_carbon_{carbon}_records"] += consumption_count
                coverage[f"blank_addition_water_{water}_records"] += consumption_count
            else:
                coverage["blank_addition_codes_without_unique_99_crosswalk"] += 1
                coverage["blank_addition_records_without_unique_99_crosswalk"] += consumption_count
        summary = {
            "sheet": FOOTPRINT_SHEET,
            "coefficient_units_per_100g": {"carbon": "g CO2e", "water": "L"},
            "counts": dict(sorted(counts.items())),
            "coverage_of_positive_consumption_rows": dict(sorted(coverage.items())),
            "unmatched_food_preparation_keys": sorted(unmatched_keys),
            "note": "Blank preparation marks addition lines in the IBGE dictionary. The 99 crosswalk is reported separately and is possible only when that food has exactly one workbook preparation, 99. It is not silently applied to exact-key coverage. Zero, missing, and invalid coefficients remain distinct. No food-description matching is used.",
        }
        return summary, {key: value for key, value in keys.items() if key not in duplicate_keys}, crosswalk_foods
    finally:
        book.close()


def validation_person_day_coverage(path: Path, coefficients: dict, crosswalk_foods: set[str]) -> dict:
    """Count whole person-days covered, keeping zero and positive values apart."""
    days: dict[tuple[str, ...], list[bool]] = {}
    with consumption_lines(path) as lines:
        for raw_line in lines:
            record = raw_line.rstrip(b"\r\n").decode("latin-1")
            if len(record) < MIN_RECORD_LENGTH or field(record, "QUADRO") not in VALID_DAYS:
                continue
            identity = tuple(field(record, name) for name in ("UF", "COD_UPA", "NUM_DOM", "NUM_UC", "COD_INFORMANTE", "QUADRO"))
            if any(not part for part in identity):
                continue
            try:
                grams = float(field(record, "QTD"))
            except ValueError:
                continue
            if not math.isfinite(grams) or grams <= 0:
                continue
            flags = days.setdefault(identity, [True, True, True, True])
            food = code(field(record, "V9001"))
            raw_preparation = field(record, "COD_PREPARACAO_FINAL")
            preparation = code(raw_preparation)
            if not raw_preparation and food in crosswalk_foods:
                preparation = "99"
            pair = coefficients.get((food, preparation))
            if pair is None:
                flags[:] = [False, False, False, False]
                continue
            carbon, water = pair
            flags[0] &= carbon in {"zero", "positive"}
            flags[1] &= water in {"zero", "positive"}
            flags[2] &= carbon == "positive"
            flags[3] &= water == "positive"
    return {
        "person_days": len(days),
        "all_rows_carbon_numeric_including_zero": sum(flags[0] for flags in days.values()),
        "all_rows_water_numeric_including_zero": sum(flags[1] for flags in days.values()),
        "all_rows_both_numeric_including_zero": sum(flags[0] and flags[1] for flags in days.values()),
        "all_rows_both_strictly_positive": sum(flags[2] and flags[3] for flags in days.values()),
        "note": "Includes the documented blank-addition crosswalk. A zero coefficient is counted as numeric but still requires source-specific interpretation before optimization.",
    }


def validation_nutrients(path: Path, food_rows: Counter) -> dict:
    required = {"food_code", "preparation_code"}
    counts: Counter = Counter()
    keys: set[tuple[str, str]] = set()
    duplicate_keys: set[tuple[str, str]] = set()
    incomplete_keys: set[tuple[str, str]] = set()
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or [])
        if not required <= columns:
            raise ValueError(f"Nutrient CSV needs columns {sorted(required)}")
        nutrient_columns = sorted(c for c in columns if c.endswith("_per_100g"))
        if not nutrient_columns:
            raise ValueError("Nutrient CSV needs at least one column ending in _per_100g")
        for row in reader:
            counts["rows"] += 1
            food = code(row["food_code"])
            preparation = code(row["preparation_code"])
            if food is None or preparation is None:
                counts["rows_without_full_food_key"] += 1
                continue
            key = (food, preparation)
            if key in keys:
                duplicate_keys.add(key)
                counts["duplicate_key_rows"] += 1
            else:
                keys.add(key)
            if any(numeric_coefficient(row[name]) in {"missing", "invalid"} for name in nutrient_columns):
                counts["rows_with_missing_or_invalid_coefficient"] += 1
                incomplete_keys.add(key)
    covered = sum(
        number for key, number in food_rows.items()
        if key in keys and key not in duplicate_keys and key not in incomplete_keys
    )
    return {
        "status": "provided_local_file_checked",
        "columns": nutrient_columns,
        "counts": dict(sorted(counts.items())),
        "matched_positive_consumption_records_with_complete_numeric_row": covered,
        "note": "Coverage alone does not establish source permission, scientific suitability, or nutrient validity. No coefficient values are exported.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pof", type=Path, required=True, help="Official Dados_20230713.zip or extracted CONSUMO_ALIMENTAR.txt")
    parser.add_argument("--documentation", type=Path, help="Official Documentacao_20230713.zip for provenance")
    parser.add_argument("--footprints", type=Path, help="OSF environmental workbook")
    parser.add_argument("--nutrients", type=Path, help="Locally obtained, non-redistributed per-100-g coefficient CSV")
    parser.add_argument("--output", type=Path, required=True, help="Aggregate JSON validation output")
    args = parser.parse_args(argv)

    for name in ("pof", "documentation", "footprints", "nutrients"):
        value = getattr(args, name)
        if value is not None and not value.is_file():
            parser.error(f"{name} input not found: {value}")

    report = {
        "schema_version": "1.0",
        "validation_date": date.today().isoformat(),
        "inputs": {"pof": input_info(args.pof, POF_DATA_URL if args.pof.suffix.lower() == ".zip" else None)},
    }
    if args.documentation:
        report["inputs"]["documentation"] = input_info(args.documentation, POF_DOCUMENTATION_URL)
    consumption, food_rows, blank_addition_rows = validation_consumption(args.pof)
    report["consumption"] = consumption

    if args.footprints:
        report["inputs"]["footprints"] = input_info(args.footprints, FOOTPRINT_URL)
        footprint_summary, coefficients, crosswalk_foods = validation_footprints(args.footprints, food_rows, blank_addition_rows)
        footprint_summary["person_day_coverage"] = validation_person_day_coverage(args.pof, coefficients, crosswalk_foods)
        report["footprints"] = footprint_summary
    else:
        report["footprints"] = {"status": "not_supplied"}

    if args.nutrients:
        report["inputs"]["nutrients"] = input_info(args.nutrients)
        report["nutrients"] = validation_nutrients(args.nutrients, food_rows)
    else:
        report["nutrients"] = {"status": "not_supplied", "note": "Nutrient linkage and its permission remain unresolved."}

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote aggregate validation to {args.output}")
    print(f"Records: {consumption['counts']['records']}; person-days: {consumption['person_days_with_records']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
