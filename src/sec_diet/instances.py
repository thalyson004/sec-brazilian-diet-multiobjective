"""Rebuild local SEC benchmark instances from pinned public input files."""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import load_workbook

from .source_checks import FOOTPRINT_SHEET, consumption_lines, input_info
from .cohort import FIXED_TAP_WATER_KEY, MODEL_NUTRIENTS, nutrient_value
from .extract import person_day_id
from .layout import MIN_RECORD_LENGTH, VALID_DAYS, code, field
from .model import DietModel, nonnegative_finite, positive_finite


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def environmental_coefficients(path: Path) -> tuple[dict, set[str]]:
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        if FOOTPRINT_SHEET not in book.sheetnames:
            raise ValueError(f"Missing workbook sheet {FOOTPRINT_SHEET}")
        values = {}
        preparations = defaultdict(set)
        for row in book[FOOTPRINT_SHEET].iter_rows(min_row=4, values_only=True):
            if not row or not isinstance(row[0], (int, float)):
                continue
            food, preparation = code(row[0]), code(row[2] if len(row) > 2 else None)
            if food is None or preparation is None:
                raise ValueError("Environmental row has an invalid food/preparation key")
            key = (food, preparation)
            if key in values:
                raise ValueError(f"Duplicate environmental key {key}")
            carbon = nonnegative_finite(row[4], "carbon coefficient")
            water = nonnegative_finite(row[5], "water coefficient")
            values[key] = (carbon / 100.0, water / 100.0)
            preparations[food].add(preparation)
        if values.get(FIXED_TAP_WATER_KEY) != (0.0, 0.0):
            raise ValueError("Expected fixed tap water to have assigned zero workbook coefficients")
        additions = {food for food, prep in preparations.items() if prep == {"99"}}
        return values, additions
    finally:
        book.close()


def build(pof: Path, footprints: Path, design_path: Path, cohort_path: Path, output_dir: Path) -> dict:
    design, cohort = read_json(design_path), read_json(cohort_path)
    if design.get("schema_version") != "1.0" or cohort.get("schema_version") != "1.0":
        raise ValueError("Unsupported design or cohort schema")
    if design["benchmark"]["nutrient_fields"] != list(MODEL_NUTRIENTS):
        raise ValueError("Frozen nutrient fields differ from the parser")
    sources = {"pof": input_info(pof), "footprints": input_info(footprints)}
    for name in sources:
        expected = design["source_sha256"][name]
        if sources[name]["sha256"] != expected or cohort["inputs"][name]["sha256"] != expected:
            raise ValueError(f"{name} checksum differs from frozen design and cohort validation")
    selected = {row["person_day_id"]: row for row in cohort["cohort"]["selected_instances"]}
    if len(selected) != design["benchmark"]["instances"]:
        raise ValueError("Selected instance count differs from frozen design")
    environmental, additions = environmental_coefficients(footprints)
    slopes = defaultdict(lambda: [[0.0, 0.0] for _ in MODEL_NUTRIENTS])
    observed = defaultdict(lambda: {"variables": defaultdict(float), "fixed": [0.0] * len(MODEL_NUTRIENTS), "source_rows": 0})
    with consumption_lines(pof) as lines:
        for raw in lines:
            record = raw.rstrip(b"\r\n").decode("latin-1")
            if len(record) < MIN_RECORD_LENGTH:
                raise ValueError("POF source has a short consumption row")
            identity = tuple(field(record, name) for name in ("UF", "COD_UPA", "NUM_DOM", "NUM_UC", "COD_INFORMANTE", "QUADRO"))
            if any(not part for part in identity) or identity[5] not in VALID_DAYS:
                raise ValueError("POF source has an invalid respondent-day key")
            food = code(field(record, "V9001"))
            preparation = code(field(record, "COD_PREPARACAO_FINAL"))
            if food is None:
                raise ValueError("POF source has an invalid food code")
            grams = positive_finite(field(record, "QTD"), "POF quantity")
            nutrient_amounts = [nonnegative_finite(nutrient_value(record, name), name) for name in MODEL_NUTRIENTS]
            key = (food, preparation)
            for i, amount in enumerate(nutrient_amounts):
                slopes[key][i][0] += grams * amount
                slopes[key][i][1] += grams * grams
            day_id = person_day_id(identity)
            if day_id not in selected:
                continue
            state = observed[day_id]
            state["source_rows"] += 1
            if key == FIXED_TAP_WATER_KEY:
                for i, amount in enumerate(nutrient_amounts):
                    state["fixed"][i] += amount
            else:
                occasion = field(record, "V9017")
                if occasion not in {"1", "2", "3", "4", "5", "6"}:
                    raise ValueError(f"Selected day {day_id} has an invalid occasion")
                state["variables"][(food, preparation, occasion)] += grams
    if set(observed) != set(selected):
        raise ValueError("Some selected person-days are missing from the POF archive")
    if output_dir.exists() and any(output_dir.iterdir()):
        raise ValueError(f"Instance output directory must be empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_rows = []
    for day_id, selection in selected.items():
        state = observed[day_id]
        variables = []
        for (food, preparation, occasion), grams in sorted(state["variables"].items()):
            environmental_key = (food, preparation or "99")
            if preparation is None and food not in additions:
                raise ValueError(f"No unique addition crosswalk for food {food}")
            if environmental_key not in environmental:
                raise ValueError(f"Missing environmental coefficient for {environmental_key}")
            carbon, water = environmental[environmental_key]
            positive_finite(carbon, "carbon coefficient for optimized food")
            positive_finite(water, "water coefficient for optimized food")
            nutrient_coefficients = {}
            for i, name in enumerate(MODEL_NUTRIENTS):
                numerator, denominator = slopes[(food, preparation)][i]
                nutrient_coefficients[name] = nonnegative_finite(numerator / positive_finite(denominator, "coefficient denominator"), name)
            variables.append({
                "food_code": food, "preparation_code": preparation, "occasion_code": occasion,
                "baseline_g": grams, "nutrients_per_g": nutrient_coefficients,
                "carbon_gco2e_per_g": carbon, "water_l_per_g": water,
            })
        if len(variables) != selection["food_occasion_variables"]:
            raise ValueError(f"Selected day {day_id} has unexpected variable count")
        instance = {
            "schema_version": "1.0", "study_id": design["study_id"], "person_day_id": day_id,
            "day": selection["day"], "age_band": selection["age_band"], "sex_code": selection["sex_code"],
            "source_rows": state["source_rows"], "fixed_tap_water_nutrients": dict(zip(MODEL_NUTRIENTS, state["fixed"])),
            "variables": variables,
        }
        model = DietModel.from_dict(instance, design)
        if not model.evaluate(model.baseline)["feasible"]:
            raise ValueError(f"Observed baseline is infeasible on selected day {day_id}")
        path = output_dir / f"{day_id}.json"
        write_json(path, instance)
        manifest_rows.append({"person_day_id": day_id, "file": path.name, **input_info(path)})
    manifest = {
        "schema_version": "1.0", "study_id": design["study_id"], "design": input_info(design_path),
        "cohort": input_info(cohort_path), "sources": sources, "instances": manifest_rows,
        "note": "Local derived coefficients; do not publish this directory or its files.",
    }
    write_json(output_dir / "instances-manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pof", type=Path, required=True)
    parser.add_argument("--footprints", type=Path, required=True)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    for name in ("pof", "footprints", "design", "cohort"):
        if not getattr(args, name).is_file():
            parser.error(f"Missing {name}: {getattr(args, name)}")
    manifest = build(args.pof, args.footprints, args.design, args.cohort, args.output_dir)
    print(f"Built {len(manifest['instances'])} local benchmark instances")
    return 0


if __name__ == "__main__":
    sys.exit(main())
