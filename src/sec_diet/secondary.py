"""Pooled IGD+ and dietary summaries from complete saved Pareto fronts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from .analysis import ALGORITHMS, digest


OBJECTIVES = ("N", "C", "W", "D")


def first_front(values: np.ndarray) -> np.ndarray:
    """Exact two/three-dimensional minimization skyline, including ties once."""
    values = np.unique(values, axis=0)
    if not len(values):
        return values
    order = np.lexsort(tuple(values[:, k] for k in range(values.shape[1] - 1, -1, -1)))
    sorted_values = values[order]
    if values.shape[1] == 2:
        keep, minimum = [], np.inf
        for point in sorted_values:
            if point[1] < minimum:
                keep.append(point)
                minimum = point[1]
        return np.asarray(keep)
    y = np.unique(sorted_values[:, 1])
    tree = np.full(len(y) + 1, np.inf)
    keep = []
    for point in sorted_values:
        index = int(np.searchsorted(y, point[1])) + 1
        j, minimum = index, np.inf
        while j:
            minimum = min(minimum, tree[j])
            j -= j & -j
        if point[2] < minimum:
            keep.append(point)
        j = index
        while j < len(tree):
            tree[j] = min(tree[j], point[2])
            j += j & -j
    return np.asarray(keep)


def igd_plus(reference: np.ndarray, candidates: np.ndarray) -> float | None:
    if not len(reference) or not len(candidates):
        return None
    total = 0.0
    for block in np.array_split(reference, max(1, (len(reference) + 63) // 64)):
        delta = np.maximum(candidates[None, :, :] - block[:, None, :], 0.0)
        total += np.sqrt(np.min(np.sum(delta * delta, axis=2), axis=1)).sum()
    return float(total / len(reference))


def group_analysis(task: tuple[str, str, list[dict], Path, Path]) -> dict:
    person, subset, rows, root, instances = task
    dimensions = tuple(subset.split(","))
    instance = json.loads((instances / (person + ".json")).read_text(encoding="utf-8"))
    baseline = np.asarray([row["baseline_g"] for row in instance["variables"]], dtype=float)
    occasions = np.asarray([row["occasion_code"] for row in instance["variables"]])
    occasion_groups = [(occasions == code) for code in sorted(set(occasions))]
    runs = []
    for row in rows:
        front = []
        vectors_g = []
        with (root / row["run_id"] / "front.jsonl").open(encoding="utf-8") as stream:
            for line in stream:
                item = json.loads(line)
                front.append(item["evaluation"])
                vectors_g.append(item["x_g"])
        vectors = np.asarray([[item["normalized"][name] for name in dimensions] for item in front], dtype=float).reshape(-1, len(dimensions))
        if len(vectors) != len(front):
            raise ValueError("Front size mismatch")
        runs.append((row["algorithm"], vectors, front))
    pooled = first_front(np.concatenate([item[1] for item in runs]))
    leaveout = {}
    for algorithm in ALGORITHMS:
        leaveout[algorithm] = first_front(np.concatenate([r[1] for r in runs if r[0] != algorithm]))
    outputs = []
    for algorithm, vectors, front in runs:
        if not len(front):
            outputs.append({"algorithm": algorithm, "igd_plus": None, "leaveout_igd_plus": None, "front_size": 0})
            continue
        quantities = {name: float(np.median([item["raw"][name] for item in front])) for name in OBJECTIVES}
        quantities["fiber_g"] = float(np.median([item["nutrients"]["FIBRA"] for item in front]))
        quantities["sodium_mg"] = float(np.median([item["nutrients"]["SODIO"] for item in front]))
        quantities["energy_kcal"] = float(np.median([item["nutrients"]["ENERGIA_KCAL"] for item in front]))
        quantities["both_nutrient_aspirations_fraction"] = float(np.mean([
            item["nutrients"]["FIBRA"] >= 25 and item["nutrients"]["SODIO"] <= 2000 for item in front
        ]))
        grams = np.asarray(vectors_g, dtype=float)
        if grams.shape[1] != len(baseline):
            raise ValueError("Front quantities differ from local instance")
        quantities["food_combination_retention_fraction"] = float(np.median(np.mean(grams >= .1 * baseline, axis=1)))
        occasion_changes = np.column_stack([
            np.abs(grams[:, group].sum(axis=1) - baseline[group].sum()) / baseline[group].sum()
            for group in occasion_groups
        ])
        quantities["mean_occasion_mass_change"] = float(np.median(occasion_changes.mean(axis=1)))
        outputs.append({"algorithm": algorithm, "igd_plus": igd_plus(pooled, vectors),
                        "leaveout_igd_plus": igd_plus(leaveout[algorithm], vectors),
                        "front_size": len(front), **quantities})
    return {"person": person, "subset": subset, "pooled_size": len(pooled), "runs": outputs}


def analyze(matrix: Path, validation: Path, root: Path, instances: Path, workers: int) -> dict:
    report = json.loads(validation.read_text(encoding="utf-8"))
    if not report["complete_matrix"] or report["counts"]["complete"] != 19200 or any(
        value for key, value in report["counts"].items() if key != "complete"
    ) or report["matrix"]["sha256"] != digest(matrix):
        raise ValueError("Complete matching validation required")
    groups = defaultdict(list)
    with matrix.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            groups[(row["person_day_id"], row["objective_subset"])].append(row)
    if len(groups) != 240 or any(len(group) != 80 for group in groups.values()):
        raise ValueError("Unexpected group size")
    tasks = [(person, subset, rows, root, instances) for (person, subset), rows in sorted(groups.items())]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(group_analysis, tasks))
    aggregates = []
    for subset in ["N,C", "N,W", "N,D", "C,W", "C,D", "W,D", "N,C,W", "N,C,D", "N,W,D", "C,W,D"]:
        for algorithm in ALGORITHMS:
            matched = [run for result in results if result["subset"] == subset for run in result["runs"] if run["algorithm"] == algorithm]
            entry = {"subset": subset, "dimension": len(subset.split(",")), "algorithm": algorithm, "runs": len(matched)}
            for key in ("igd_plus", "leaveout_igd_plus", "N", "C", "W", "D", "fiber_g", "sodium_mg", "energy_kcal", "both_nutrient_aspirations_fraction", "food_combination_retention_fraction", "mean_occasion_mass_change"):
                values = [r[key] for r in matched if r.get(key) is not None]
                entry[key + "_run_median"] = float(np.median(values)) if values else None
                entry[key + "_instance_median_mean"] = float(np.mean([
                    np.median([r[key] for result in results if result["subset"] == subset and result["person"] == person
                               for r in result["runs"] if r["algorithm"] == algorithm and r.get(key) is not None])
                    for person in sorted({result["person"] for result in results if result["subset"] == subset})
                ])) if values else None
            aggregates.append(entry)
    return {"schema_version": "1.0", "study_id": "sec2026-pof-person-day-v1",
            "input_sha256": {"matrix": digest(matrix), "full_validation": digest(validation)},
            "pooled_igd_reference": "unique feasible nondominated union of all 80 saved fronts for each respondent/subset",
            "leaveout_reference": "unique feasible nondominated union of the other three algorithms' 60 saved fronts",
            "food_retention_rule": "optimized food/preparation/occasion quantity is at least 10 percent of its observed mass",
            "occasion_change_rule": "for each diet, mean over observed occasions of absolute occasion mass difference divided by observed occasion mass; then median across the run front",
            "group_count": len(results), "run_count": sum(len(r["runs"]) for r in results),
            "pooled_front_size_median": float(np.median([r["pooled_size"] for r in results])),
            "aggregates": aggregates}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--validation", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--instances-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args(argv)
    result = analyze(args.matrix, args.validation, args.output_root, args.instances_dir, args.workers)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"groups": result["group_count"], "runs": result["run_count"],
                      "pooled_front_size_median": result["pooled_front_size_median"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
