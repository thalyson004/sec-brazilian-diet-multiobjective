"""Run the frozen comparison and preserve every evaluated candidate."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import subprocess
import sys
import time
import traceback
import tracemalloc
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from pathlib import Path

import numpy as np
import pymoo
import scipy
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.algorithms.moo.nsga3 import NSGA3
from pymoo.algorithms.moo.sms import SMSEMOA, LeastHypervolumeContributionSurvival
from pymoo.algorithms.moo.spea2 import SPEA2, SPEA2Survival
from pymoo.core.problem import Problem
from pymoo.core.sampling import Sampling
from pymoo.indicators.hv import HV
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM
from pymoo.operators.survival.rank_and_crowding.classes import RankAndCrowding
from pymoo.termination.collection import TerminationCollection
from pymoo.termination.max_eval import MaximumFunctionCallTermination
from pymoo.termination.max_time import TimeBasedTermination
from pymoo.util.ref_dirs import get_reference_directions

from .source_checks import input_info
from .instances import read_json, write_json
from .model import DietModel, nondominated_indices
from .stable_spea2 import StableSPEA2Survival


class SharedInitialPopulation(Sampling):
    def __init__(self, points: np.ndarray):
        super().__init__()
        self.points = points.copy()

    def _do(self, problem, n_samples, **kwargs):
        if n_samples != len(self.points):
            raise ValueError("Initial population size differs from frozen design")
        return self.points.copy()


class RecordedProblem(Problem):
    def __init__(self, model: DietModel, subset: tuple[str, ...], stream):
        super().__init__(n_var=model.n_var, n_obj=len(subset), n_ieq_constr=2,
                         xl=np.zeros(model.n_var), xu=model.upper_bounds)
        self.model, self.subset, self.stream = model, subset, stream
        self.rows: list[dict] = []

    def _evaluate(self, X, out, *args, **kwargs):
        fitness, violations = [], []
        for vector in np.atleast_2d(X):
            evaluation = self.model.evaluate(vector)
            row = {"ordinal": len(self.rows) + 1, "x_g": list(map(float, vector)), "evaluation": evaluation}
            self.stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")
            self.stream.flush()
            self.rows.append(row)
            fitness.append([evaluation["normalized"][name] for name in self.subset])
            energy = evaluation["nutrients"]["ENERGIA_KCAL"]
            violations.append([self.model.energy_lower - energy, energy - self.model.energy_upper])
        out["F"] = np.asarray(fitness, dtype=float)
        out["G"] = np.asarray(violations, dtype=float)


def algorithm_for(name: str, design: dict, model: DietModel, subset: tuple[str, ...], initial: np.ndarray, repair=None, crossover=None, mutation=None):
    implementation = design["implementation"]
    population = implementation["population_size"]
    common = dict(
        pop_size=population,
        sampling=SharedInitialPopulation(initial),
        crossover=crossover or SBX(prob=implementation["crossover"]["probability"], eta=implementation["crossover"]["eta"]),
        mutation=mutation or PM(prob=1.0, prob_var=1.0 / model.n_var, eta=implementation["mutation"]["eta"]),
        eliminate_duplicates=implementation["duplicate_elimination"],
        n_offsprings=implementation["offspring_per_step"][name],
    )
    if repair is not None:
        common["repair"] = repair
    if name == "NSGA2":
        return NSGA2(survival=RankAndCrowding(), **common)
    if name == "SPEA2":
        return SPEA2(survival=StableSPEA2Survival() if implementation.get('spea2_constant_coordinate_guard') else SPEA2Survival(normalize=True), **common)
    if name == "SMSEMOA":
        return SMSEMOA(survival=LeastHypervolumeContributionSurvival(), **common)
    if name == "NSGA3":
        partitions = implementation["nsga3_das_dennis_partitions"][str(len(subset))]
        directions = get_reference_directions("das-dennis", len(subset), n_partitions=partitions)
        if len(directions) != population:
            raise ValueError("NSGA-III direction count differs from population")
        return NSGA3(ref_dirs=directions, **common)
    raise ValueError(f"Unsupported algorithm {name}")


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, separators=(",", ":"), allow_nan=False) + "\n")


def versions() -> dict:
    return {
        "python": platform.python_version(), "platform": platform.platform(),
        "pymoo": pymoo.__version__, "numpy": np.__version__, "scipy": scipy.__version__,
    }


def code_revision() -> str:
    repository = Path(__file__).resolve().parents[2]
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=repository, text=True, stderr=subprocess.DEVNULL,
        ).strip()
        dirty = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=repository,
            text=True, stderr=subprocess.DEVNULL,
        ).strip()
        if dirty:
            raise ValueError("Commit local code changes before a matrix run")
    except (OSError, subprocess.CalledProcessError):
        revision = os.environ.get("SEC_CODE_REVISION", "")
    if len(revision) != 40 or any(char not in "0123456789abcdef" for char in revision.lower()):
        raise ValueError("An exact Git commit is required; set SEC_CODE_REVISION for a non-Git installation")
    return revision


def validate_environment(design: dict) -> None:
    expected = design["implementation"]
    actual = versions()
    for name, key in (("pymoo", "version"), ("numpy", "numpy_version"), ("scipy", "scipy_version")):
        if actual[name] != expected[key]:
            raise ValueError(f"{name} version {actual[name]} differs from frozen {expected[key]}")


def run_one(row: dict, design: dict, instance: dict, output_dir: Path, provenance: dict) -> dict:
    model = DietModel.from_dict(instance, design)
    if model.instance_id != row["person_day_id"] or model.n_var != int(row["food_occasion_variables"]):
        raise ValueError("Run row differs from local instance")
    subset = tuple(row["objective_subset"].split(","))
    if row["objective_subset"] not in design["objectives"]["pairs"] + design["objectives"]["triples"]:
        raise ValueError("Run requests an unregistered objective subset")
    seed = int(row["seed"])
    evaluation_limit = design["runs"]["objective_evaluations_including_initial_population"]
    if int(row["planned_evaluations"]) != evaluation_limit:
        raise ValueError("Run evaluation limit differs from design")
    population = design["implementation"]["population_size"]
    if int(row["population_size"]) != population or evaluation_limit < population:
        raise ValueError("Run population or evaluation limit differs from design")
    if output_dir.exists():
        raise ValueError(f"Output directory already exists: {output_dir}")
    output_dir.mkdir(parents=True)
    config = {
        "schema_version": "1.0", "run": row, "design": design, "provenance": provenance,
        "environment": versions(), "code_revision": provenance["code_revision"],
    }
    write_json(output_dir / "config.json", config)
    rng = np.random.default_rng(seed)
    initial = rng.uniform(0.0, model.upper_bounds, size=(population - 1, model.n_var))
    initial = np.vstack((model.baseline, initial))
    tracemalloc.start()
    start_wall, start_cpu = time.perf_counter(), time.process_time()
    error, stop_reason = None, "unknown"
    algorithm = None
    with (output_dir / "evaluated-solutions.jsonl").open("w", encoding="utf-8", newline="\n") as stream:
        problem = RecordedProblem(model, subset, stream)
        try:
            algorithm = algorithm_for(row["algorithm"], design, model, subset, initial)
            termination = TerminationCollection(
                MaximumFunctionCallTermination(evaluation_limit),
                TimeBasedTermination(design["runs"]["wall_time_limit_seconds"]),
            )
            algorithm.setup(problem, termination=termination, seed=seed, verbose=False)
            while algorithm.has_next():
                algorithm.next()
            stop_reason = "evaluation_limit" if algorithm.evaluator.n_eval >= evaluation_limit else "wall_time_limit"
        except Exception:
            error = traceback.format_exc()
            stop_reason = "error"
    actual_evaluations = len(problem.rows)
    if algorithm is not None and algorithm.evaluator.n_eval != actual_evaluations and error is None:
        error = "Evaluator count differs from recorded candidate count"
        stop_reason = "error"
    final_population = []
    if algorithm is not None and algorithm.pop is not None:
        for vector in algorithm.pop.get("X"):
            evaluation = model.evaluate(vector)
            final_population.append({"x_g": list(map(float, vector)), "evaluation": evaluation})
    write_jsonl(output_dir / "final-population.jsonl", final_population)
    front = [problem.rows[i] for i in nondominated_indices(problem.rows, subset)]
    write_jsonl(output_dir / "front.jsonl", front)
    feasible_count = sum(row_["evaluation"]["feasible"] for row_ in problem.rows)
    if front:
        point = np.full(len(subset), design["objectives"]["metric_reference_point_normalized"])
        F = np.asarray([[item["evaluation"]["normalized"][name] for name in subset] for item in front])
        hypervolume = float(HV(ref_point=point)(F))
    else:
        hypervolume = 0.0
    complete = stop_reason == "evaluation_limit" and actual_evaluations == evaluation_limit and error is None
    metrics = {
        "schema_version": "1.0", "run_id": row["run_id"], "complete": complete,
        "stop_reason": stop_reason, "actual_evaluations": actual_evaluations,
        "feasible_evaluations": feasible_count, "front_size": len(front),
        "hypervolume": hypervolume, "igd_plus": None,
        "igd_plus_status": "requires pooled instance/subset reference after confirmatory runs",
    }
    write_json(output_dir / "metrics.json", metrics)
    _, peak_python_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    resource = {
        "schema_version": "1.0", "run_id": row["run_id"],
        "wall_seconds": time.perf_counter() - start_wall,
        "cpu_seconds": time.process_time() - start_cpu,
        "peak_python_traced_bytes": peak_python_bytes,
        "peak_memory_bytes": None,
        "peak_memory_status": "Python-traced peak excludes native allocations; total process peak unavailable",
    }
    write_json(output_dir / "resources.json", resource)
    (output_dir / "run.log").write_text(
        f"run_id={row['run_id']}\nstop_reason={stop_reason}\nactual_evaluations={actual_evaluations}\n"
        + (error or ""), encoding="utf-8", newline="\n")
    return metrics


def load_context(design_path: Path, matrix_path: Path, matrix_manifest_path: Path, instances_dir: Path) -> tuple:
    design, matrix_manifest = read_json(design_path), read_json(matrix_manifest_path)
    instance_manifest = read_json(instances_dir / "instances-manifest.json")
    for name, path in (("design", design_path), ("matrix", matrix_path)):
        if matrix_manifest[name]["sha256"] != input_info(path)["sha256"]:
            raise ValueError(f"{name} checksum differs from run-matrix manifest")
    for name in ("design", "cohort"):
        if instance_manifest[name]["sha256"] != matrix_manifest[name]["sha256"]:
            raise ValueError(f"Instance {name} checksum differs from run-matrix manifest")
    for name in ("pof", "footprints"):
        if instance_manifest["sources"][name]["sha256"] != design["source_sha256"][name]:
            raise ValueError(f"Instance {name} checksum differs from design")
    if len(instance_manifest["instances"]) != design["benchmark"]["instances"]:
        raise ValueError("Instance manifest is incomplete")
    with matrix_path.open("r", encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != matrix_manifest["planned_runs"]:
        raise ValueError("Run matrix row count differs from its manifest")
    validate_environment(design)
    return design, matrix_manifest, instance_manifest, rows


def _run_task(row: dict, design: dict, instance_path: Path, output_dir: Path, provenance: dict) -> dict:
    return run_one(row, design, read_json(instance_path), output_dir, provenance)


def run_matrix(rows: list[dict], design: dict, instance_files: dict, instances_dir: Path,
               output_root: Path, provenance: dict, workers: int) -> dict:
    if not 1 <= workers <= design["runs"]["max_parallel_runs"]:
        raise ValueError("Worker count is outside the frozen parallel-run limit")
    if any((output_root / row["run_id"]).exists() for row in rows):
        raise ValueError("A planned run directory already exists; check it before scheduling again")
    output_root.mkdir(parents=True, exist_ok=True)
    counts = {"complete": 0, "incomplete": 0, "scheduler_error": 0}
    progress_path = output_root / "batch-progress.jsonl"
    with progress_path.open("a", encoding="utf-8", newline="\n") as progress, ProcessPoolExecutor(max_workers=workers) as executor:
        pending = {}
        next_row = iter(rows)

        def schedule():
            while len(pending) < 2 * workers:
                try:
                    row = next(next_row)
                except StopIteration:
                    break
                item = instance_files[row["person_day_id"]]
                task_provenance = {**provenance, "instance": item}
                future = executor.submit(_run_task, row, design, instances_dir / item["file"],
                                         output_root / row["run_id"], task_provenance)
                pending[future] = row["run_id"]

        schedule()
        finished = 0
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                run_id = pending.pop(future)
                try:
                    metrics = future.result()
                    state = "complete" if metrics["complete"] else "incomplete"
                    event = {"run_id": run_id, "state": state,
                             "actual_evaluations": metrics["actual_evaluations"],
                             "stop_reason": metrics["stop_reason"]}
                except Exception:
                    state = "scheduler_error"
                    event = {"run_id": run_id, "state": state, "traceback": traceback.format_exc()}
                counts[state] += 1
                finished += 1
                progress.write(json.dumps(event, separators=(",", ":")) + "\n")
                progress.flush()
            if finished % 100 < len(done) or finished == len(rows):
                print(f"{finished}/{len(rows)} complete={counts['complete']} "
                      f"incomplete={counts['incomplete']} scheduler_error={counts['scheduler_error']}", flush=True)
            schedule()
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--matrix", type=Path, required=True)
    parser.add_argument("--matrix-manifest", type=Path, required=True)
    parser.add_argument("--instances-dir", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--run-id")
    choice.add_argument("--all", action="store_true", help="Run the entire confirmatory matrix explicitly")
    parser.add_argument("--workers", type=int, default=1, help="Parallel run processes for --all; maximum from design is eight")
    args = parser.parse_args(argv)
    if args.run_id and args.workers != 1:
        parser.error("--workers applies only to --all")
    design, matrix_manifest, instance_manifest, rows = load_context(
        args.design, args.matrix, args.matrix_manifest, args.instances_dir)
    if args.run_id:
        rows = [row for row in rows if row["run_id"] == args.run_id]
        if len(rows) != 1:
            parser.error(f"Run ID {args.run_id} not in frozen matrix")
    instance_files = {item["person_day_id"]: item for item in instance_manifest["instances"]}
    provenance = {
        "design": matrix_manifest["design"], "cohort": matrix_manifest["cohort"],
        "matrix": matrix_manifest["matrix"], "instance_manifest": input_info(args.instances_dir / "instances-manifest.json"),
        "source_sha256": design["source_sha256"], "code_revision": code_revision(),
    }
    if args.all:
        for item in instance_files.values():
            path = args.instances_dir / item["file"]
            if input_info(path)["sha256"] != item["sha256"]:
                raise ValueError(f"Local instance checksum differs: {path}")
        counts = run_matrix(rows, design, instance_files, args.instances_dir, args.output_root,
                            provenance, args.workers)
        return 0 if counts["complete"] == len(rows) else 1
    for row in rows:
        item = instance_files[row["person_day_id"]]
        path = args.instances_dir / item["file"]
        if input_info(path)["sha256"] != item["sha256"]:
            raise ValueError(f"Local instance checksum differs: {path}")
        output_dir = args.output_root / row["run_id"]
        metrics = run_one(row, design, read_json(path), output_dir, {**provenance, "instance": item})
        print(f"{row['run_id']} {metrics['stop_reason']} {metrics['actual_evaluations']}/{row['planned_evaluations']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
