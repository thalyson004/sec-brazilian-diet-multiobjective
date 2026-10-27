"""Validate saved SEC runs against the frozen matrix and local instances."""

from __future__ import annotations

import argparse
import json
import math
import sys
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import numpy as np
from pymoo.indicators.hv import HV

from .source_checks import input_info
from .instances import read_json, write_json
from .model import DietModel, nondominated_indices
from .runner import load_context


EXPECTED_FILES = (
    "config.json", "evaluated-solutions.jsonl", "final-population.jsonl",
    "front.jsonl", "metrics.json", "resources.json", "run.log",
)


def read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def same_numbers(actual: dict, expected: dict, path: str = "") -> None:
    if actual.keys() != expected.keys():
        raise ValueError(f"Different fields at {path}")
    for key in expected:
        a, e = actual[key], expected[key]
        label = f"{path}.{key}" if path else key
        if isinstance(e, dict):
            same_numbers(a, e, label)
        elif isinstance(e, (float, int)) and not isinstance(e, bool):
            if not math.isclose(float(a), float(e), rel_tol=1e-10, abs_tol=1e-10):
                raise ValueError(f"Different numeric value at {label}")
        elif a != e:
            raise ValueError(f"Different value at {label}")


def check_one(directory: Path, row: dict, model: DietModel, design: dict,
              expected_provenance: dict | None = None, expected_code_revision: str | None = None) -> dict:
    missing = [name for name in EXPECTED_FILES if not (directory / name).is_file()]
    if missing:
        return {"run_id": row["run_id"], "state": "missing_files", "missing": missing}
    config, metrics = read_json(directory / "config.json"), read_json(directory / "metrics.json")
    if config["run"] != row or config["design"] != design or metrics["run_id"] != row["run_id"]:
        raise ValueError("Saved configuration differs from frozen matrix or design")
    if expected_code_revision and config["code_revision"] != expected_code_revision:
        raise ValueError("Saved code revision differs from selected campaign")
    if expected_provenance:
        for name, expected in expected_provenance.items():
            if config["provenance"].get(name) != expected:
                raise ValueError(f"Saved {name} provenance differs from input manifests")
    candidates = read_jsonl(directory / "evaluated-solutions.jsonl")
    subset = tuple(row["objective_subset"].split(","))
    for i, candidate in enumerate(candidates, start=1):
        if candidate["ordinal"] != i:
            raise ValueError(f"Nonsequential evaluation ordinal {i}")
        same_numbers(candidate["evaluation"], model.evaluate(np.asarray(candidate["x_g"], dtype=float)))
    if metrics["actual_evaluations"] != len(candidates):
        raise ValueError("Metric evaluation count differs from saved candidates")
    expected_front = [candidates[i] for i in nondominated_indices(candidates, subset)]
    front = read_jsonl(directory / "front.jsonl")
    if front != expected_front or metrics["front_size"] != len(front):
        raise ValueError("Saved front differs from independently rebuilt feasible Pareto front")
    evaluated_vectors = {tuple(candidate["x_g"]) for candidate in candidates}
    for candidate in read_jsonl(directory / "final-population.jsonl"):
        same_numbers(candidate["evaluation"], model.evaluate(np.asarray(candidate["x_g"], dtype=float)))
        if tuple(candidate["x_g"]) not in evaluated_vectors:
            raise ValueError("Final population contains a diet absent from evaluated solutions")
    if front:
        point = np.full(len(subset), design["objectives"]["metric_reference_point_normalized"])
        values = np.asarray([[candidate["evaluation"]["normalized"][name] for name in subset] for candidate in front])
        hv = float(HV(ref_point=point)(values))
    else:
        hv = 0.0
    if not math.isclose(hv, metrics["hypervolume"], rel_tol=1e-10, abs_tol=1e-10):
        raise ValueError("Saved hypervolume differs from recomputation")
    if metrics["feasible_evaluations"] != sum(c["evaluation"]["feasible"] for c in candidates):
        raise ValueError("Feasible evaluation count differs from saved candidates")
    # Completion depends on saved evaluations and interruptions. The original
    # campaign used an earlier label for its evaluation-count stopping reason.
    # Its records remain readable without rewriting their original logs.
    complete = (len(candidates) == int(row["planned_evaluations"])
                and metrics["stop_reason"].startswith("evaluation_"))
    if metrics["complete"] != complete:
        raise ValueError("Completion flag differs from saved evaluation count and stop reason")
    resources = read_json(directory / "resources.json")
    if resources["run_id"] != row["run_id"]:
        raise ValueError("Resource record has a different run ID")
    for key in ("wall_seconds", "cpu_seconds", "peak_python_traced_bytes"):
        value = resources[key]
        if not isinstance(value, (float, int)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"Invalid resource field {key}")
    log = (directory / "run.log").read_text(encoding="utf-8")
    if f"run_id={row['run_id']}\n" not in log or f"stop_reason={metrics['stop_reason']}\n" not in log:
        raise ValueError("Run log disagrees with metrics")
    return {"run_id": row["run_id"], "state": "complete" if complete else "incomplete",
            "evaluations": len(candidates), "hypervolume": hv}


def _check_task(directory: Path, row: dict, model: DietModel, design: dict,
                expected_provenance: dict, expected_code_revision: str | None) -> dict:
    try:
        return check_one(directory, row, model, design, expected_provenance, expected_code_revision)
    except Exception as exc:
        return {"run_id": row["run_id"], "state": "invalid", "reason": str(exc)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--matrix-manifest", type=Path, required=True)
    parser.add_argument("--instances-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--run-id", help="Check one run; omit to check the complete matrix")
    parser.add_argument("--workers", type=int, default=1, help="Parallel validation processes, maximum eight")
    parser.add_argument("--expected-code-revision", help="Require this full Git commit in every run config")
    args = parser.parse_args(argv)
    if not 1 <= args.workers <= 8:
        parser.error("--workers must be between one and eight")
    design, matrix_manifest, instance_manifest, rows = load_context(
        args.design, args.matrix, args.matrix_manifest, args.instances_dir)
    if args.run_id:
        rows = [row for row in rows if row["run_id"] == args.run_id]
        if len(rows) != 1:
            parser.error(f"Run ID {args.run_id} not in frozen matrix")
    instance_files = {item["person_day_id"]: item for item in instance_manifest["instances"]}
    results_by_id = {}
    models = {}
    ready = []
    for row in rows:
        directory = args.output_root / row["run_id"]
        if not directory.exists():
            results_by_id[row["run_id"]] = {"run_id": row["run_id"], "state": "missing_directory"}
            continue
        day_id = row["person_day_id"]
        if day_id not in models:
            item = instance_files[day_id]
            path = args.instances_dir / item["file"]
            if input_info(path)["sha256"] != item["sha256"]:
                raise ValueError(f"Instance checksum differs: {path}")
            models[day_id] = DietModel.from_dict(read_json(path), design)
        provenance = {"design": matrix_manifest["design"], "cohort": matrix_manifest["cohort"],
                      "matrix": matrix_manifest["matrix"], "instance": instance_files[day_id]}
        ready.append((directory, row, models[day_id], design, provenance, args.expected_code_revision))
    if args.workers == 1:
        for task in ready:
            result = _check_task(*task)
            results_by_id[result["run_id"]] = result
    else:
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            pending = {}
            remaining = iter(ready)

            def schedule():
                while len(pending) < 2 * args.workers:
                    try:
                        task = next(remaining)
                    except StopIteration:
                        break
                    future = executor.submit(_check_task, *task)
                    pending[future] = task[1]["run_id"]

            schedule()
            checked = 0
            while pending:
                done, _ = wait(pending, return_when=FIRST_COMPLETED)
                for future in done:
                    run_id = pending.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {"run_id": run_id, "state": "invalid", "reason": f"validation worker: {exc}"}
                    results_by_id[run_id] = result
                    checked += 1
                if checked % 1000 < len(done) or checked == len(ready):
                    print(f"Checked {checked}/{len(ready)} run directories", flush=True)
                schedule()
    results = [results_by_id[row["run_id"]] for row in rows]
    counts = {state: sum(item["state"] == state for item in results) for state in
              ("complete", "incomplete", "missing_directory", "missing_files", "invalid")}
    report = {"schema_version": "1.0", "design": matrix_manifest["design"], "matrix": matrix_manifest["matrix"],
              "counts": counts, "runs": results,
              "complete_matrix": len(rows) == matrix_manifest["planned_runs"] and counts["complete"] == len(rows)}
    write_json(args.report, report)
    print(f"Checked {len(rows)} planned runs: {counts}")
    return 0 if counts["complete"] == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
