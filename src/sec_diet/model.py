"""Independent SEC diet model and validation of local instance files."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np


OBJECTIVES = ("N", "C", "W", "D")
NUTRIENTS = ("ENERGIA_KCAL", "FIBRA", "SODIO")


def positive_finite(value: object, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be positive and finite")
    return number


def nonnegative_finite(value: object, name: str) -> float:
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be nonnegative and finite")
    return number


@dataclass(frozen=True)
class DietModel:
    instance_id: str
    baseline: np.ndarray
    nutrients: np.ndarray  # rows are variables, columns are energy, fiber, sodium per gram
    fixed_nutrients: np.ndarray
    carbon: np.ndarray
    water: np.ndarray
    fiber_min: float
    sodium_max: float
    energy_lower: float
    energy_upper: float

    @classmethod
    def from_dict(cls, data: dict, design: dict) -> "DietModel":
        if data.get("schema_version") != "1.0" or data.get("study_id") != design["study_id"]:
            raise ValueError("Instance schema or study ID differs from frozen design")
        rows = data.get("variables")
        if not isinstance(rows, list) or len(rows) < 5:
            raise ValueError("Instance needs at least five observed variables")
        keys = []
        for row in rows:
            key = (row["food_code"], row["preparation_code"], row["occasion_code"])
            if key in keys:
                raise ValueError(f"Duplicate food/preparation/occasion variable: {key}")
            if row["occasion_code"] not in {"1", "2", "3", "4", "5", "6"}:
                raise ValueError(f"Invalid occasion code: {row['occasion_code']}")
            keys.append(key)
        baseline = np.asarray([positive_finite(row["baseline_g"], "baseline_g") for row in rows], dtype=float)
        nutrients = np.asarray([[nonnegative_finite(row["nutrients_per_g"][name], name) for name in NUTRIENTS] for row in rows], dtype=float)
        fixed = np.asarray([nonnegative_finite(data["fixed_tap_water_nutrients"][name], name) for name in NUTRIENTS], dtype=float)
        carbon = np.asarray([positive_finite(row["carbon_gco2e_per_g"], "carbon") for row in rows], dtype=float)
        water = np.asarray([positive_finite(row["water_l_per_g"], "water") for row in rows], dtype=float)
        bounds = design["benchmark"]["quantity_bounds"]
        if bounds != [0.0, 2.0]:
            raise ValueError("Unsupported quantity bounds in frozen design")
        band = design["benchmark"]["energy_band_relative_to_modeled_baseline"]
        if band != [0.8, 1.2]:
            raise ValueError("Unsupported energy band in frozen design")
        baseline_energy = float(fixed[0] + np.dot(baseline, nutrients[:, 0]))
        positive_finite(baseline_energy, "modeled baseline energy")
        aspirations = design["objectives"]["nutrient_aspirations"]
        return cls(
            instance_id=data["person_day_id"], baseline=baseline, nutrients=nutrients,
            fixed_nutrients=fixed, carbon=carbon, water=water,
            fiber_min=positive_finite(aspirations["fiber_min_g_per_day"], "fiber aspiration"),
            sodium_max=positive_finite(aspirations["sodium_max_mg_per_day"], "sodium aspiration"),
            energy_lower=band[0] * baseline_energy, energy_upper=band[1] * baseline_energy,
        )

    @property
    def n_var(self) -> int:
        return len(self.baseline)

    @property
    def upper_bounds(self) -> np.ndarray:
        return 2.0 * self.baseline

    @property
    def normalization(self) -> np.ndarray:
        sodium_top = float(self.fixed_nutrients[2] + np.dot(self.upper_bounds, self.nutrients[:, 2]))
        n_max = max(1.0, 0.5 * (1.0 + max(0.0, sodium_top - self.sodium_max) / self.sodium_max))
        carbon_max = float(np.dot(self.upper_bounds, self.carbon))
        water_max = float(np.dot(self.upper_bounds, self.water))
        return np.asarray([n_max, carbon_max, water_max, 1.0], dtype=float)

    def evaluate(self, values: np.ndarray) -> dict:
        x = np.asarray(values, dtype=float)
        if x.shape != (self.n_var,) or not np.all(np.isfinite(x)):
            raise ValueError("Candidate must be a finite vector with the instance dimension")
        q = self.fixed_nutrients + x @ self.nutrients
        raw = np.asarray([
            0.5 * (max(0.0, self.fiber_min - q[1]) / self.fiber_min
                   + max(0.0, q[2] - self.sodium_max) / self.sodium_max),
            float(np.dot(x, self.carbon)), float(np.dot(x, self.water)),
            float(np.abs(x - self.baseline).sum() / self.baseline.sum()),
        ], dtype=float)
        energy_violation = max(0.0, self.energy_lower - q[0], q[0] - self.energy_upper)
        box_violation = max(0.0, float((-x).max()), float((x - self.upper_bounds).max()))
        feasible = energy_violation == 0.0 and box_violation == 0.0
        return {
            "nutrients": dict(zip(NUTRIENTS, map(float, q))),
            "raw": dict(zip(OBJECTIVES, map(float, raw))),
            "normalized": dict(zip(OBJECTIVES, map(float, raw / self.normalization))),
            "energy_violation_kcal": float(energy_violation),
            "box_violation_g": float(box_violation),
            "feasible": bool(feasible),
        }


def nondominated_indices(rows: list[dict], subset: tuple[str, ...]) -> list[int]:
    """Incremental exact Pareto archive; identical diets appear only once."""
    archive: list[int] = []
    for i, row in enumerate(rows):
        if not row["evaluation"]["feasible"]:
            continue
        x = row["x_g"]
        f = row["evaluation"]["normalized"]
        rejected = False
        remove = []
        for j in archive:
            old = rows[j]
            if x == old["x_g"]:
                rejected = True
                break
            g = old["evaluation"]["normalized"]
            if all(g[k] <= f[k] for k in subset) and any(g[k] < f[k] for k in subset):
                rejected = True
                break
            if all(f[k] <= g[k] for k in subset) and any(f[k] < g[k] for k in subset):
                remove.append(j)
        if not rejected:
            archive = [j for j in archive if j not in remove]
            archive.append(i)
    return archive
