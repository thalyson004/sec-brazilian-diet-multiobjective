"""Matched reduced experiment choosing a shortage penalty before the main study."""
from __future__ import annotations

import os
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

import argparse
import hashlib
import json
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from shutil import copyfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import numpy as np
from sec_diet.instances import read_json, write_json
from sec_diet.profile_pipeline import configuration
from sec_diet.profile_runner import run_plan, execute_task
from sec_diet.runner import code_revision, versions
from sec_diet.source_checks import input_info

ROOT = Path(__file__).resolve().parents[1]


def save_csv(path, rows):
    import csv
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepared-inputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "results/penalty-weight-study-v4.1")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    weights = [0., 1., 5., 10., 25., 50.]
    catalogue = read_json(ROOT / "docs/profiles/catalogue.json")
    protocol = dict(schema_version='4.1',spea2_constant_coordinate_guard=True,weights=weights, profiles=["F30", "F60", "M30", "M60"],
                    algorithms=["NSGA2", "SPEA2", "NSGA3", "SMSEMOA"],
                    objective_subsets=["N,C", "N,W", "N,C,D"], evaluations=3300, replicates=3,
                    seed_namespace="sec2026-pof-meals-v4-penalty-calibration",
                    selection_rule="nearest unpenalized normalized origin among reporting-front points",
                    weight_rule="eligible within 0.5 percentage point of best mean capped adequacy and 0.5 criterion of best mean attained count; minimize mean included non-N normalized objective among eligible weights; smallest weight breaks ties",
                    main_seeds="separate main-study namespace; no calibration seeds reused",
                    role="exploratory calibration; no confirmatory p-values or population inference")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    registered = output / "protocol.json"
    if registered.exists() and read_json(registered) != protocol:
        raise ValueError("Calibration directory has a different registered design")
    write_json(registered, protocol)
    inputs = output / "inputs"
    inputs.mkdir(exist_ok=True)
    source_manifest = read_json(args.prepared_inputs / "manifest.json")
    for profile in source_manifest["profiles"]:
        source = args.prepared_inputs / profile["instance"]["filename"]
        if input_info(source)["sha256"] != profile["instance"]["sha256"]:
            raise ValueError("Prepared input checksum mismatch")
        target = inputs / source.name
        if target.exists() and input_info(target)["sha256"] != input_info(source)["sha256"]:
            raise ValueError("Calibration input changed")
        if not target.exists():
            copyfile(source, target)
    if not (inputs / "manifest.json").exists():
        copyfile(args.prepared_inputs / "manifest.json", inputs / "manifest.json")
    provenance = dict(code_revision=code_revision(), environment=versions(),
                      protocol_sha256=input_info(registered)["sha256"],
                      prepared_manifest_sha256=input_info(inputs / "manifest.json")["sha256"])
    if (output / "execution.json").exists() and read_json(output / "execution.json") != provenance:
        raise ValueError("Calibration code or inputs changed; choose a new output directory")
    write_json(output / "execution.json", provenance)
    tasks = []
    for weight in weights:
        design = configuration(catalogue, 3300, 3, penalty=weight > 0, penalty_weight=weight)
        design["seed_namespace"] = protocol["seed_namespace"]
        design["objective_subsets"] = protocol["objective_subsets"]
        write_json(output / f"weight-{weight:g}" / "design.json", design)
        for row in run_plan(design):
            directory = output / f"weight-{weight:g}" / "runs" / row["run_id"]
            tasks.append((weight, row, design, directory))
    states = []
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(execute_task, row, design, str(inputs / (row["profile_id"] + ".json")),
                               str(directory), provenance, args.resume): (weight, row)
                   for weight, row, design, directory in tasks}
        with (output / "progress.jsonl").open("a", encoding="utf-8") as stream:
            for count, future in enumerate(as_completed(futures), 1):
                weight, row = futures[future]
                try:
                    state = future.result()
                except Exception as error:
                    state = dict(run_id=row["run_id"], state="failed", reason=str(error))
                state["weight"] = weight
                states.append(state)
                stream.write(json.dumps(state) + "\n")
                stream.flush()
                if count % 24 == 0 or state["state"] == "failed":
                    print(f"{count}/{len(tasks)} weight={weight:g} {state['state']}", flush=True)
    failures = [s for s in states if s["state"] == "failed"]
    write_json(output / "completion.json", dict(planned_runs=len(tasks), complete_runs=len(tasks)-len(failures), failures=failures))
    if failures:
        raise ValueError("Calibration incomplete; no weight has been selected")
    records = []
    for weight, row, design, directory in tasks:
        with np.load(directory / "front.npz", allow_pickle=False) as front:
            if not len(front["X"]):
                raise ValueError("Calibration contains an empty feasible front")
            columns = ["NCWD".index(n) for n in row["objective_subset"].split(",")]
            i = int(np.argmin(np.linalg.norm(front["normalized"][:, columns], axis=1)))
            global_i = int(front["indices"][i])
            raw, norm = front["raw"][i], front["normalized"][i]
        with np.load(directory / "evaluations.npz", allow_pickle=False) as data:
            attained = int(data["attained_targets"][global_i])
            shortfall = float(data["shortfall"][global_i])
        records.append(dict(weight=weight, **row, adequacy_percent=float(raw[0]), attained_targets=attained,
                            all_targets_attained=int(attained == 23), shortfall_fraction=shortfall,
                            carbon_kg=float(raw[1]/1000), water_l=float(raw[2]), departure_percent=float(raw[3]*100),
                            other_objective_mean=float(np.mean(norm[columns[1:]]))))
    save_csv(output / "outcomes.csv", records)
    summaries = []
    for weight in weights:
        selected = [r for r in records if r["weight"] == weight]
        summaries.append(dict(weight=weight, runs=len(selected),
            mean_adequacy_percent=float(np.mean([r["adequacy_percent"] for r in selected])),
            mean_attained_targets=float(np.mean([r["attained_targets"] for r in selected])),
            all_targets_fraction=float(np.mean([r["all_targets_attained"] for r in selected])),
            other_objective_mean=float(np.mean([r["other_objective_mean"] for r in selected])),
            mean_carbon_kg=float(np.mean([r["carbon_kg"] for r in selected])),
            mean_water_l=float(np.mean([r["water_l"] for r in selected])),
            mean_departure_percent=float(np.mean([r["departure_percent"] for r in selected]))))
    best_a = max(r["mean_adequacy_percent"] for r in summaries)
    best_n = max(r["mean_attained_targets"] for r in summaries)
    eligible = [r for r in summaries if r["mean_adequacy_percent"] >= best_a-.5 and r["mean_attained_targets"] >= best_n-.5]
    if not eligible:
        raise ValueError("Prespecified nutritional thresholds select no weight; retain results for review")
    chosen = min(eligible, key=lambda r: (r["other_objective_mean"], r["weight"]))
    selection = dict(selected_weight=chosen["weight"], eligible_weights=[r["weight"] for r in eligible],
                     protocol=protocol, provenance=provenance, summaries=summaries,
                     outcomes_sha256=input_info(output / "outcomes.csv")["sha256"])
    write_json(output / "selection.json", selection)
    write_json(ROOT / "docs/profiles/penalty-selection.json", selection)
    save_csv(output / "summary.csv", summaries)
    print(json.dumps(selection, indent=2), flush=True)


if __name__ == "__main__":
    main()
