"""Registered aggregate analysis of an independently checked SEC campaign."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import numpy as np


ALGORITHMS = ("NSGA2", "SPEA2", "NSGA3", "SMSEMOA")
SIGN_SEED = 2026100201
BOOT_SEED = 2026100202
N_SIGN = 99_999
N_BOOT = 9_999


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def percentile(values: list[float], p: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), p))


def holm(p_values: list[float]) -> list[float]:
    order = np.argsort(p_values)
    adjusted = [0.0] * len(p_values)
    previous = 0.0
    for rank, index in enumerate(order):
        previous = max(previous, min(1.0, (len(p_values) - rank) * p_values[index]))
        adjusted[int(index)] = previous
    return adjusted


def analyze(matrix: Path, validation: Path, output_root: Path) -> dict:
    report = json.loads(validation.read_text(encoding="utf-8"))
    if not report.get("complete_matrix") or report.get("counts") != {
        "complete": 19200, "incomplete": 0, "invalid": 0,
        "missing_directory": 0, "missing_files": 0,
    }:
        raise ValueError("Full independent validation is required before analysis")
    if report["matrix"]["sha256"] != digest(matrix):
        raise ValueError("Matrix differs from the checked matrix")
    with matrix.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 19200 or len({row["run_id"] for row in rows}) != len(rows):
        raise ValueError("Unexpected matrix size or duplicate run IDs")
    if {x["run_id"] for x in report["runs"]} != {x["run_id"] for x in rows}:
        raise ValueError("Checked IDs differ from matrix IDs")
    groups: dict[tuple[str, str, str], list[dict]] = defaultdict(list)
    resource_summaries = defaultdict(list)
    complete = feasible_runs = feasible_evaluations = 0
    for row in rows:
        directory = output_root / row["run_id"]
        metric = json.loads((directory / "metrics.json").read_text(encoding="utf-8"))
        resource = json.loads((directory / "resources.json").read_text(encoding="utf-8"))
        if metric["run_id"] != row["run_id"] or resource["run_id"] != row["run_id"]:
            raise ValueError("Run ID mismatch")
        if not metric["complete"] or metric["actual_evaluations"] != 1650:
            raise ValueError("Incomplete run in checked campaign")
        complete += 1
        feasible_runs += metric["feasible_evaluations"] > 0
        feasible_evaluations += metric["feasible_evaluations"]
        groups[(row["person_day_id"], row["objective_subset"], row["algorithm"])].append({
            "replicate": int(row["replicate_id"]), "hv": float(metric["hypervolume"]),
            "front": int(metric["front_size"]), "feasible_evaluations": int(metric["feasible_evaluations"]),
            "wall": float(resource["wall_seconds"]), "cpu": float(resource["cpu_seconds"]),
            "peak_python_bytes": int(resource["peak_python_traced_bytes"]),
        })
        resource_summaries[(row["objective_subset"], row["algorithm"])].append(resource["wall_seconds"])
    if len(groups) != 24 * 10 * 4 or any(sorted(r["replicate"] for r in runs) != list(range(1, 21)) for runs in groups.values()):
        raise ValueError("Missing or repeated matched replicates")

    respondents = sorted({key[0] for key in groups})
    profile_by_person = {}
    for row in rows:
        profile = (row["age_band"], row["sex_code"])
        previous = profile_by_person.setdefault(row["person_day_id"], profile)
        if previous != profile:
            raise ValueError("Respondent profile changed across matrix rows")
    subsets = ["N,C", "N,W", "N,D", "C,W", "C,D", "W,D", "N,C,W", "N,C,D", "N,W,D", "C,W,D"]
    # Reuse the same resampling vectors for all registered contrasts.
    signs = np.random.default_rng(SIGN_SEED).choice(np.array([-1, 1], dtype=np.int8), size=(N_SIGN, 24))
    draws = np.random.default_rng(BOOT_SEED).integers(0, 24, size=(N_BOOT, 24))
    contrasts = []
    summaries = []
    instance_medians = {}
    for subset in subsets:
        for algorithm in ALGORITHMS:
            values = np.asarray([np.median([r["hv"] for r in groups[(person, subset, algorithm)]]) for person in respondents])
            instance_medians[(subset, algorithm)] = values
            runs = [r for person in respondents for r in groups[(person, subset, algorithm)]]
            q1, q3 = np.percentile(values, [25, 75])
            outliers = int(np.count_nonzero((values < q1 - 1.5 * (q3 - q1)) | (values > q3 + 1.5 * (q3 - q1))))
            summaries.append({
                "subset": subset, "dimension": len(subset.split(",")), "algorithm": algorithm,
                "respondents": 24, "runs": len(runs),
                "mean_instance_median_hv": float(np.mean(values)),
                "median_instance_median_hv": float(np.median(values)),
                "instance_median_hv_q1": percentile(values.tolist(), 25),
                "instance_median_hv_q3": percentile(values.tolist(), 75),
                "respondent_median_hv_tukey_outlier_count": outliers,
                "run_hv_median": float(np.median([r["hv"] for r in runs])),
                "run_hv_q1": percentile([r["hv"] for r in runs], 25),
                "run_hv_q3": percentile([r["hv"] for r in runs], 75),
                "front_size_median": float(np.median([r["front"] for r in runs])),
                "wall_seconds_median": float(np.median([r["wall"] for r in runs])),
                "cpu_seconds_median": float(np.median([r["cpu"] for r in runs])),
                "python_peak_mb_median": float(np.median([r["peak_python_bytes"] for r in runs]) / 1e6),
                "feasible_run_count": sum(r["feasible_evaluations"] > 0 for r in runs),
            })
        for left, right in combinations(ALGORITHMS, 2):
            difference = instance_medians[(subset, left)] - instance_medians[(subset, right)]
            observed = float(np.mean(difference))
            null = (signs @ difference) / 24
            p = float((1 + np.count_nonzero(np.abs(null) >= abs(observed) - 1e-12)) / (N_SIGN + 1))
            boots = np.mean(difference[draws], axis=1)
            contrasts.append({
                "subset": subset, "dimension": len(subset.split(",")), "left": left, "right": right,
                "mean_paired_hv_difference": observed,
                "ci95_low": percentile(boots.tolist(), 2.5),
                "ci95_high": percentile(boots.tolist(), 97.5),
                "p_unadjusted": p,
                "positive_respondents": int(np.count_nonzero(difference > 0)),
                "negative_respondents": int(np.count_nonzero(difference < 0)),
                "tied_respondents": int(np.count_nonzero(difference == 0)),
            })
    corrected = holm([row["p_unadjusted"] for row in contrasts])
    for row, p in zip(contrasts, corrected):
        row["p_holm"] = p
        row["significant_0_05"] = p < 0.05
    wins_by_dimension = []
    wins_by_profile = []
    seed_stability = []
    for dimension in (2, 3):
        selected = [subset for subset in subsets if len(subset.split(",")) == dimension]
        wins = {algorithm: 0 for algorithm in ALGORITHMS}
        for person in respondents:
            for subset in selected:
                values = {algorithm: instance_medians[(subset, algorithm)][respondents.index(person)] for algorithm in ALGORITHMS}
                winners = [algorithm for algorithm, value in values.items() if value == max(values.values())]
                if len(winners) == 1:
                    wins[winners[0]] += 1
        wins_by_dimension.append({"dimension": dimension, "cells": len(respondents) * len(selected), "unique_wins": wins})
    for age_band, sex_code in sorted(set(profile_by_person.values())):
        persons = [person for person in respondents if profile_by_person[person] == (age_band, sex_code)]
        wins = {algorithm: 0 for algorithm in ALGORITHMS}
        for person in persons:
            for subset in subsets:
                values = {algorithm: instance_medians[(subset, algorithm)][respondents.index(person)] for algorithm in ALGORITHMS}
                winners = [algorithm for algorithm, value in values.items() if value == max(values.values())]
                if len(winners) == 1:
                    wins[winners[0]] += 1
        wins_by_profile.append({"age_band": age_band, "sex_code": sex_code, "respondents": len(persons),
                                "cells": len(persons) * len(subsets), "unique_wins": wins})
    for subset in subsets:
        agreement = []
        for person in respondents:
            median_values = {algorithm: instance_medians[(subset, algorithm)][respondents.index(person)] for algorithm in ALGORITHMS}
            median_winner = max(ALGORITHMS, key=lambda algorithm: median_values[algorithm])
            by_algorithm = {algorithm: {r["replicate"]: r["hv"] for r in groups[(person, subset, algorithm)]} for algorithm in ALGORITHMS}
            agreement.append(sum(max(ALGORITHMS, key=lambda algorithm: by_algorithm[algorithm][replicate]) == median_winner
                                 for replicate in range(1, 21)) / 20)
        seed_stability.append({"subset": subset, "median_fraction_seed_winner_matches_instance_median_winner": float(np.median(agreement)),
                               "min_fraction": float(np.min(agreement)), "max_fraction": float(np.max(agreement))})
    by_dimension = []
    for dimension in (2, 3):
        for algorithm in ALGORITHMS:
            selected = [r for r in summaries if r["dimension"] == dimension and r["algorithm"] == algorithm]
            by_dimension.append({
                "dimension": dimension, "algorithm": algorithm, "subsets": len(selected),
                "median_wall_seconds_across_runs": float(np.median([
                    run["wall"] for (person, subset, method), runs in groups.items()
                    if method == algorithm and len(subset.split(",")) == dimension for run in runs
                ])),
                "median_front_size_across_runs": float(np.median([
                    run["front"] for (person, subset, method), runs in groups.items()
                    if method == algorithm and len(subset.split(",")) == dimension for run in runs
                ])),
            })
    return {
        "schema_version": "1.0", "study_id": "sec2026-pof-person-day-v1",
        "input_sha256": {"matrix": digest(matrix), "full_validation": digest(validation)},
        "analysis_code": "sec_diet.analysis", "rng": "numpy.random.PCG64",
        "sign_flip_seed": SIGN_SEED, "bootstrap_seed": BOOT_SEED,
        "sign_flip_vectors": N_SIGN, "bootstrap_resamples": N_BOOT,
        "runs": complete, "respondents": 24, "feasible_runs": int(feasible_runs),
        "feasible_evaluations": int(feasible_evaluations),
        "summaries": summaries, "contrasts": contrasts, "by_dimension": by_dimension,
        "wins_by_dimension": wins_by_dimension, "wins_by_profile": wins_by_profile,
        "seed_stability": seed_stability,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    result = analyze(args.matrix, args.validation, args.output_root)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"runs": result["runs"], "feasible_runs": result["feasible_runs"],
                      "contrasts": len(result["contrasts"]),
                      "holm_significant": sum(r["significant_0_05"] for r in result["contrasts"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
