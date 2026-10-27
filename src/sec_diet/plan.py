"""Expand the frozen SEC design into one planned row per stochastic run."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

from .source_checks import input_info

FIELDNAMES = (
    "run_id", "person_day_id", "age_band", "sex_code", "day", "food_occasion_variables",
    "objective_subset", "n_objectives", "algorithm", "replicate_id", "seed",
    "population_size", "planned_evaluations", "run_directory",
)


def seed_for(study: str, instance_id: str, subset: str, replicate: int) -> int:
    content = f"{study}|{instance_id}|{subset}|{replicate}".encode("ascii")
    return int.from_bytes(hashlib.sha256(content).digest()[:4], "big") or 1


def rows_for(design: dict, cohort: dict) -> list[dict]:
    instances = cohort["cohort"]["selected_instances"]
    expected = design["benchmark"]["instances"]
    if len(instances) != expected or len({row["person_day_id"] for row in instances}) != expected:
        raise ValueError("Cohort manifest does not contain the expected distinct benchmark instances")
    for kind in ("pof", "footprints"):
        observed = cohort["inputs"][kind]["sha256"]
        if observed != design["source_sha256"][kind]:
            raise ValueError(f"{kind} hash differs from the frozen design")
    subsets = design["objectives"]["pairs"] + design["objectives"]["triples"]
    algorithms = design["algorithms"]
    n_replicates = design["runs"]["replicates_per_cell"]
    result = []
    run_ids = set()
    for instance in instances:
        identifier = instance["person_day_id"]
        for subset in subsets:
            dimensions = subset.split(",")
            if len(dimensions) not in {2, 3} or len(dimensions) != len(set(dimensions)):
                raise ValueError(f"Invalid objective subset {subset}")
            for algorithm in algorithms:
                for replicate in range(1, n_replicates + 1):
                    seed = seed_for(design["study_id"], identifier, subset, replicate)
                    identity = f"{identifier}|{subset}|{algorithm}|{replicate}".encode("ascii")
                    run_id = hashlib.sha256(identity).hexdigest()[:24]
                    if run_id in run_ids:
                        raise ValueError(f"Duplicate run ID {run_id}")
                    run_ids.add(run_id)
                    result.append({
                        "run_id": run_id,
                        "person_day_id": identifier,
                        "age_band": instance["age_band"],
                        "sex_code": instance["sex_code"],
                        "day": instance["day"],
                        "food_occasion_variables": instance["food_occasion_variables"],
                        "objective_subset": subset,
                        "n_objectives": len(dimensions),
                        "algorithm": algorithm,
                        "replicate_id": replicate,
                        "seed": seed,
                        "population_size": design["implementation"]["population_size"],
                        "planned_evaluations": design["runs"]["objective_evaluations_including_initial_population"],
                        "run_directory": f"results/runs/{run_id}",
                    })
    total = expected * len(subsets) * len(algorithms) * n_replicates
    if len(result) != total:
        raise ValueError(f"Expected {total} matrix rows; found {len(result)}")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args(argv)
    for name in ("design", "cohort"):
        if not getattr(args, name).is_file():
            parser.error(f"{name} input not found: {getattr(args, name)}")
    if args.matrix.resolve() == args.manifest.resolve():
        parser.error("Matrix and manifest paths must differ")
    design = json.loads(args.design.read_text(encoding="utf-8"))
    cohort = json.loads(args.cohort.read_text(encoding="utf-8"))
    rows = rows_for(design, cohort)
    args.matrix.parent.mkdir(parents=True, exist_ok=True)
    with args.matrix.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=FIELDNAMES, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    manifest = {
        "schema_version": "1.0",
        "generated_on": date.today().isoformat(),
        "design": input_info(args.design),
        "cohort": input_info(args.cohort),
        "matrix": input_info(args.matrix),
        "instances": design["benchmark"]["instances"],
        "objective_subsets": len(design["objectives"]["pairs"] + design["objectives"]["triples"]),
        "algorithms": len(design["algorithms"]),
        "replicates_per_cell": design["runs"]["replicates_per_cell"],
        "planned_runs": len(rows),
        "planned_objective_evaluations": len(rows) * design["runs"]["objective_evaluations_including_initial_population"],
        "expected_run_outputs": ["config.json", "evaluated-solutions.jsonl", "final-population.jsonl", "front.jsonl", "metrics.json", "resources.json", "run.log"],
        "note": "This matrix schedules work. It is not a record of completed experiments.",
    }
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {len(rows)} planned runs to {args.matrix}")
    print(f"Wrote matrix manifest to {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
