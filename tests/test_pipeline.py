"""Controlled arithmetic and runner checks with invented coefficients only."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
from pymoo.indicators.hv import HV

from sec_diet.source_checks import input_info
from sec_diet.check import check_one, main as check_main
from sec_diet.instances import write_json
from sec_diet.model import DietModel, nondominated_indices
from sec_diet.runner import main as run_main, run_matrix, run_one


def design() -> dict:
    return {
        "schema_version": "1.0", "study_id": "controlled-arithmetic-only",
        "benchmark": {"quantity_bounds": [0.0, 2.0], "energy_band_relative_to_modeled_baseline": [0.8, 1.2]},
        "objectives": {"pairs": ["N,C"], "triples": [], "nutrient_aspirations": {
            "fiber_min_g_per_day": 25.0, "sodium_max_mg_per_day": 2000.0},
            "metric_reference_point_normalized": 1.1},
        "implementation": {
            "population_size": 6, "offspring_per_step": {"NSGA2": 6, "SPEA2": 6, "NSGA3": 6, "SMSEMOA": 1},
            "nsga3_das_dennis_partitions": {"2": 5, "3": 2},
            "crossover": {"probability": 0.9, "eta": 20}, "mutation": {"eta": 20},
            "duplicate_elimination": True},
        "runs": {"objective_evaluations_including_initial_population": 18, "wall_time_limit_seconds": 30,
                 "max_parallel_runs": 2},
    }


def instance() -> dict:
    return {
        "schema_version": "1.0", "study_id": "controlled-arithmetic-only", "person_day_id": "toy-day",
        "fixed_tap_water_nutrients": {"ENERGIA_KCAL": 0.0, "FIBRA": 0.0, "SODIO": 100.0},
        "variables": [{
            "food_code": str(i), "preparation_code": "1", "occasion_code": "1" if i < 3 else "2",
            "baseline_g": 100.0,
            "nutrients_per_g": {"ENERGIA_KCAL": 2.0, "FIBRA": 0.02, "SODIO": 1.0},
            "carbon_gco2e_per_g": 3.0, "water_l_per_g": 0.5,
        } for i in range(5)],
    }


def row(algorithm: str) -> dict:
    return {
        "run_id": f"toy-{algorithm}", "person_day_id": "toy-day", "food_occasion_variables": "5",
        "objective_subset": "N,C", "algorithm": algorithm, "seed": "1234",
        "population_size": "6", "planned_evaluations": "18", "replicate_id": "1",
    }


class ArithmeticChecks(unittest.TestCase):
    def test_baseline_units_fixed_sodium_and_normalization(self):
        model = DietModel.from_dict(instance(), design())
        result = model.evaluate(model.baseline)
        self.assertEqual(result["nutrients"]["ENERGIA_KCAL"], 1000.0)
        self.assertEqual(result["nutrients"]["SODIO"], 600.0)
        self.assertEqual(result["raw"]["N"], 0.3)
        self.assertEqual(result["raw"]["C"], 1500.0)
        self.assertEqual(result["raw"]["W"], 250.0)
        self.assertEqual(result["raw"]["D"], 0.0)
        self.assertTrue(result["feasible"])
        self.assertEqual(result["normalized"]["C"], 0.5)
        self.assertFalse(model.evaluate(np.zeros(model.n_var))["feasible"])
        self.assertFalse(model.evaluate(model.upper_bounds)["feasible"])

    def test_dominance_and_hypervolume(self):
        rows = []
        for i, (n, c) in enumerate(((0.2, 0.8), (0.8, 0.2), (0.9, 0.9), (0.2, 0.8))):
            rows.append({"x_g": [float(i)], "evaluation": {"feasible": True, "normalized": {"N": n, "C": c}}})
        self.assertEqual(nondominated_indices(rows, ("N", "C")), [0, 1, 3])
        self.assertAlmostEqual(HV(ref_point=np.array([1.1, 1.1]))(np.array([[0.2, 0.8], [0.8, 0.2]])), 0.45)

    def test_four_adapters_and_saved_rescoring(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("NSGA2", "SPEA2", "NSGA3", "SMSEMOA"):
                run_row = row(name)
                output = root / name
                metrics = run_one(run_row, design(), instance(), output, {"code_revision": "0" * 40})
                self.assertEqual(metrics["actual_evaluations"], 18, name)
                self.assertTrue(metrics["complete"], name)
                checked = check_one(output, run_row, DietModel.from_dict(instance(), design()), design())
                self.assertEqual(checked["state"], "complete", name)
            first = root / "NSGA2" / "evaluated-solutions.jsonl"
            rerun = root / "repeat"
            run_one(row("NSGA2"), design(), instance(), rerun, {"code_revision": "0" * 40})
            self.assertEqual(first.read_bytes(), (rerun / "evaluated-solutions.jsonl").read_bytes())

    def test_checker_detects_missing_and_corrupt_outputs(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "run"
            run_row = row("NSGA2")
            model = DietModel.from_dict(instance(), design())
            run_one(run_row, design(), instance(), root, {"code_revision": "0" * 40})
            front = root / "front.jsonl"
            front.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Saved front differs"):
                check_one(root, run_row, model, design())
            front.unlink()
            self.assertEqual(check_one(root, run_row, model, design())["state"], "missing_files")

    def test_registered_cli_and_completion_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            spec = design()
            spec["benchmark"]["instances"] = 1
            spec["source_sha256"] = {"pof": "a" * 64, "footprints": "b" * 64}
            spec["implementation"].update({"version": "0.6.1.6", "numpy_version": "2.4.1", "scipy_version": "1.17.0"})
            design_path, cohort_path, matrix_path = root / "design.json", root / "cohort.json", root / "matrix.csv"
            write_json(design_path, spec)
            write_json(cohort_path, {"schema_version": "1.0"})
            run_row = row("NSGA2")
            with matrix_path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=list(run_row), lineterminator="\n")
                writer.writeheader()
                writer.writerow(run_row)
            matrix_manifest_path = root / "matrix-manifest.json"
            write_json(matrix_manifest_path, {"design": input_info(design_path), "cohort": input_info(cohort_path),
                                              "matrix": input_info(matrix_path), "planned_runs": 1})
            instances_dir = root / "instances"
            instance_path = instances_dir / "toy-day.json"
            write_json(instance_path, instance())
            write_json(instances_dir / "instances-manifest.json", {
                "design": input_info(design_path), "cohort": input_info(cohort_path),
                "sources": {"pof": {"sha256": "a" * 64}, "footprints": {"sha256": "b" * 64}},
                "instances": [{"person_day_id": "toy-day", "file": instance_path.name, **input_info(instance_path)}],
            })
            common = ["--design", str(design_path), "--matrix", str(matrix_path),
                      "--matrix-manifest", str(matrix_manifest_path), "--instances-dir", str(instances_dir),
                      "--output-root", str(root / "runs"), "--run-id", run_row["run_id"]]
            with patch("sec_diet.runner.code_revision", return_value="0" * 40):
                self.assertEqual(run_main(common), 0)
            report = root / "validation.json"
            self.assertEqual(check_main([*common, "--report", str(report)]), 0)
            self.assertTrue(__import__("json").loads(report.read_text(encoding="utf-8"))["counts"]["complete"] == 1)
            parallel_report = root / "parallel-validation.json"
            self.assertEqual(check_main([*common[:-2], "--report", str(parallel_report), "--workers", "2",
                                         "--expected-code-revision", "0" * 40]), 0)
            self.assertTrue(__import__("json").loads(parallel_report.read_text(encoding="utf-8"))["complete_matrix"])

    def test_two_worker_schedule_uses_separate_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "instances" / "toy-day.json"
            write_json(path, instance())
            item = {"person_day_id": "toy-day", "file": path.name, **input_info(path)}
            rows = [row("NSGA2"), row("SPEA2")]
            result = run_matrix(rows, design(), {"toy-day": item}, path.parent,
                                root / "runs", {"code_revision": "0" * 40}, workers=2)
            self.assertEqual(result, {"complete": 2, "incomplete": 0, "scheduler_error": 0})
            for run_row in rows:
                self.assertEqual(check_one(root / "runs" / run_row["run_id"], run_row,
                                           DietModel.from_dict(instance(), design()), design())["state"], "complete")

    def test_repeated_algorithms_across_two_and_three_dimensions(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            specification = design()
            specification["objectives"]["triples"] = ["N,C,W"]
            for name in ("NSGA2", "SPEA2", "NSGA3", "SMSEMOA"):
                for subset in ("N,C", "N,C,W", "N,C"):
                    run_row = row(name)
                    run_row["run_id"] += f"-{len(list(root.iterdir()))}"
                    run_row["objective_subset"] = subset
                    output = root / run_row["run_id"]
                    metrics = run_one(run_row, specification, instance(), output, {"code_revision": "0" * 40})
                    self.assertTrue(metrics["complete"], (name, subset, metrics))
                    self.assertEqual(check_one(output, run_row, DietModel.from_dict(instance(), specification),
                                               specification)["state"], "complete")


if __name__ == "__main__":
    unittest.main()
