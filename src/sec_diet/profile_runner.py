"""Matched evolutionary runs initialized from observed diets of each profile."""

from __future__ import annotations

import hashlib
import time
import traceback
from pathlib import Path

import numpy as np
from pymoo.core.problem import Problem
from pymoo.core.repair import Repair
from pymoo.core.mutation import Mutation
from pymoo.operators.crossover.ux import UniformCrossover
from pymoo.indicators.hv import HV
from pymoo.termination.collection import TerminationCollection
from pymoo.termination.max_eval import MaximumFunctionCallTermination
from pymoo.termination.max_time import TimeBasedTermination

from .instances import read_json, write_json
from .profile_model import ProfileModel
from .runner import algorithm_for, versions
from .source_checks import input_info


def front_indices(values: np.ndarray) -> np.ndarray:
    """Exact incremental minimization archive, retaining unique objective vectors."""
    archive = []
    for i, value in enumerate(values):
        if archive:
            previous = values[archive]
            if np.any(np.all(previous <= value, axis=1)):
                continue
            archive = [j for j, remove in zip(archive, np.all(value <= previous, axis=1)) if not remove]
        archive.append(i)
    return np.asarray(archive, dtype=int)


class MealRepair(Repair):
    def __init__(self, model):
        super().__init__()
        self.model = model

    def _do(self, problem, X, **kwargs):
        return self.model.repair(X)


class WholeMealMutation(Mutation):
    def _do(self, problem, X, random_state=None, **kwargs):
        rng = random_state if random_state is not None else np.random.default_rng()
        values = X.astype(int).copy()
        mask = rng.random(values.shape) < 1.0 / problem.n_var
        for slot in range(problem.n_var):
            eligible = np.flatnonzero(mask[:, slot])
            values[eligible, slot] = rng.integers(0, int(problem.xu[slot])+1, size=len(eligible))
        return values


class ProfileProblem(Problem):
    def __init__(self, model, subset, evaluation_limit):
        super().__init__(n_var=model.n_var, n_obj=len(subset), n_ieq_constr=2+len(model.meal_limits),
                         xl=np.zeros(model.n_var), xu=model.upper_bounds)
        self.model, self.subset, self.evaluation_limit = model, subset, evaluation_limit
        self.vectors, self.raw, self.normalized, self.constraints = [], [], [], []
        self.search,self.attained,self.shortfall=[],[],[]

    def _evaluate(self, X, out, *args, **kwargs):
        fitness, constraints = [], []
        for x in np.atleast_2d(X):
            result = self.model.evaluate(x)
            self.vectors.append(x.copy())
            self.raw.append([result["raw"][name] for name in "NCWD"])
            self.normalized.append([result["normalized"][name] for name in "NCWD"])
            self.constraints.append(result["constraints"])
            self.search.append([result["search_normalized"][name] for name in "NCWD"])
            self.attained.append(result["attained_targets"])
            self.shortfall.append(result["shortfall_fraction"])
            fitness.append([result["search_normalized"][name] for name in self.subset])
            constraints.append(result["constraints"])
        out["F"], out["G"] = np.asarray(fitness), np.asarray(constraints)


def run_plan(design: dict) -> list[dict]:
    rows = []
    for profile in design["profiles"]:
        for subset in design["objective_subsets"]:
            for replicate in range(1, design["replicates"] + 1):
                seed_text = f"{design.get('seed_namespace',design['study_id'])}|{profile}|{subset}|{replicate}"
                seed = int(hashlib.sha256(seed_text.encode()).hexdigest()[:8], 16) or 1
                for algorithm in design["algorithms"]:
                    run_id = hashlib.sha256(f"{seed_text}|{algorithm}".encode()).hexdigest()[:24]
                    rows.append(dict(run_id=run_id, profile_id=profile, objective_subset=subset,
                                     algorithm=algorithm, replicate=replicate, seed=seed))
    return rows


def initial_population(model, row, design):
    rng = np.random.default_rng(row["seed"])
    return model.sampling_pool[rng.choice(len(model.sampling_pool), design["implementation"]["population_size"], replace=False)]


def validate_run(directory: Path, row: dict, design: dict, instance: dict, provenance: dict) -> dict:
    config = read_json(directory / "config.json")
    if config != dict(run=row, design=design, provenance=provenance):
        raise ValueError(f"Saved inputs or code differ for {row['run_id']}")
    result = read_json(directory / "metrics.json")
    model = ProfileModel(instance, design)
    if not np.array_equal(np.load(directory/"initial-population.npy", allow_pickle=False), initial_population(model,row,design)):
        raise ValueError("Saved initial population differs from the matched observed-diet sample")
    with np.load(directory / "evaluations.npz", allow_pickle=False) as data:
        X, raw, normalized, constraints = (data[k] for k in ("X", "raw", "normalized", "constraints"))
        search=data['search'] if 'search' in data else normalized
        if len(X) != result["actual_evaluations"] or len(X) != design["evaluations"] or not result["complete"] or result["stop_reason"] != "evaluation_limit":
            raise ValueError(f"Incomplete run retained at {directory}")
        feasible = []
        for i, x in enumerate(X):
            current = model.evaluate(x)
            expected_raw = [current["raw"][n] for n in "NCWD"]
            expected_norm = [current["normalized"][n] for n in "NCWD"]
            if not np.allclose(raw[i], expected_raw, rtol=1e-10, atol=1e-10) or not np.allclose(normalized[i], expected_norm, rtol=1e-10, atol=1e-10):
                raise ValueError(f"Saved objectives differ at candidate {i}")
            if not np.allclose(constraints[i], current["constraints"], rtol=1e-10, atol=1e-10):
                raise ValueError(f"Saved constraints differ at candidate {i}")
            if not np.allclose(search[i],[current['search_normalized'][n] for n in 'NCWD'],rtol=1e-10,atol=1e-10):
                raise ValueError(f"Saved penalized objectives differ at candidate {i}")
            feasible.append(current["feasible"])
        subset = ["NCWD".index(n) for n in row["objective_subset"].split(",")]
        eligible = np.flatnonzero(feasible)
        search_indices = eligible[front_indices(search[eligible][:, subset])]
        indices = search_indices[front_indices(normalized[search_indices][:, subset])]
        if (directory/"search-front.npz").exists():
            with np.load(directory/"search-front.npz",allow_pickle=False) as front:
                if not np.array_equal(front['indices'],search_indices):
                    raise ValueError("Saved penalized search front differs from recomputation")
        with np.load(directory / "front.npz", allow_pickle=False) as front:
            if not np.array_equal(front["indices"], indices) or not np.array_equal(front["X"], X[indices]):
                raise ValueError("Saved front differs from recomputed nondominated candidates")
        hv = float(HV(ref_point=np.full(len(subset), 1.1))(normalized[indices][:, subset])) if len(indices) else 0.
        if not np.isclose(hv, result["hypervolume"], rtol=1e-10, atol=1e-10):
            raise ValueError("Saved hypervolume differs from recomputation")
        if result["feasible_evaluations"] != sum(feasible):
            raise ValueError("Saved feasible count differs from recomputation")
    for name, saved in result["outputs"].items():
        if input_info(directory / name)["sha256"] != saved["sha256"]:
            raise ValueError(f"Saved checksum differs for {name}")
    return result


def execute_task(row: dict, design: dict, instance_path: str, directory_path: str, provenance: dict, resume: bool):
    directory, instance = Path(directory_path), read_json(Path(instance_path))
    if directory.exists():
        if not resume:
            raise ValueError(f"Run already exists: {directory}. Use --resume to check and retain it.")
        result = validate_run(directory, row, design, instance, provenance)
        return dict(run_id=row["run_id"], state="retained", metrics=result)
    model = ProfileModel(instance, design)
    initial = initial_population(model,row,design)
    directory.mkdir(parents=True)
    write_json(directory / "config.json", dict(run=row, design=design, provenance=provenance))
    np.save(directory / "initial-population.npy", initial, allow_pickle=False)
    subset = tuple(row["objective_subset"].split(","))
    problem = ProfileProblem(model, subset, design["evaluations"])
    algorithm = algorithm_for(row["algorithm"], design, model, subset, initial, repair=MealRepair(model),
        crossover=UniformCrossover(prob=design["implementation"]["crossover"]["probability"]), mutation=WholeMealMutation(prob=1.0))
    started = time.perf_counter()
    error = None
    try:
        algorithm.setup(problem, termination=TerminationCollection(MaximumFunctionCallTermination(design["evaluations"]),
            TimeBasedTermination(design["wall_time_limit_seconds"])), seed=row["seed"], verbose=False)
        while algorithm.has_next():
            remaining = design["evaluations"] - len(problem.vectors)
            if remaining <= 0:
                break
            algorithm.n_offsprings = min(design["implementation"]["offspring_per_step"][row["algorithm"]], remaining)
            algorithm.next()
    except Exception:
        error = traceback.format_exc()
    optimization_wall_seconds=time.perf_counter()-started
    X = np.asarray(problem.vectors).reshape(-1, model.n_var)
    raw = np.asarray(problem.raw).reshape(-1, 4)
    normalized = np.asarray(problem.normalized).reshape(-1, 4)
    search=np.asarray(problem.search).reshape(-1,4)
    constraints = np.asarray(problem.constraints).reshape(-1, 2+len(model.meal_limits))
    np.savez_compressed(directory / "evaluations.npz", X=X, raw=raw, normalized=normalized, search=search,
        constraints=constraints,attained_targets=np.asarray(problem.attained),shortfall=np.asarray(problem.shortfall))
    feasible = np.flatnonzero(np.all(constraints<=1e-10,axis=1))
    columns = ["NCWD".index(n) for n in subset]
    search_indices=feasible[front_indices(search[feasible][:,columns])]
    indices = search_indices[front_indices(normalized[search_indices][:, columns])]
    np.savez_compressed(directory / "search-front.npz",indices=search_indices,X=X[search_indices],
        raw=raw[search_indices],normalized=normalized[search_indices],search=search[search_indices])
    np.savez_compressed(directory / "front.npz", indices=indices, X=X[indices], raw=raw[indices],
        normalized=normalized[indices],search=search[indices])
    complete = error is None and len(X) == design["evaluations"]
    result = dict(run_id=row["run_id"], complete=complete, actual_evaluations=len(X),
        feasible_evaluations=len(feasible), front_size=len(indices),
        stop_reason="error" if error else "evaluation_limit" if complete else "wall_time_limit",
        wall_seconds=optimization_wall_seconds, total_task_wall_seconds=time.perf_counter()-started,
        hypervolume=float(HV(ref_point=np.full(len(subset), 1.1))(normalized[indices][:, columns])) if len(indices) else 0.,
        outputs={name: input_info(directory/name) for name in ("evaluations.npz", "front.npz", "search-front.npz","initial-population.npy")})
    write_json(directory / "metrics.json", result)
    (directory / "run.log").write_text(error or result["stop_reason"], encoding="utf-8")
    if not complete:
        raise ValueError(f"Run ended {result['stop_reason']}; partial files retained at {directory}")
    validate_run(directory, row, design, instance, provenance)
    return dict(run_id=row["run_id"], state="complete", metrics=result)
