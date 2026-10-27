"""Render aggregate analysis figures and optional local Pareto fronts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .analysis import ALGORITHMS
from .secondary import first_front
from .graphics import configure, export


SUBSETS = ("N,C", "N,W", "N,D", "C,W", "C,D", "W,D", "N,C,W", "N,C,D", "N,W,D", "C,W,D")


def aggregate_figures(primary: dict, secondary: dict, directory: Path) -> None:
    configure()
    directory.mkdir(parents=True, exist_ok=True)
    for key, filename, label, fmt in (
        ("mean_instance_median_hv", "hypervolume.pdf", "Mean respondent-level median hypervolume", ".3f"),
        ("wall_seconds_median", "wall-time.pdf", "Median wall time per run (s)", ".1f"),
    ):
        lookup = {(row["subset"], row["algorithm"]): row[key] for row in primary["summaries"]}
        grid = np.asarray([[lookup[(subset, method)] for method in ALGORITHMS] for subset in SUBSETS])
        # A separate display scale for every objective subset prevents misleading
        # cross-dimensional color comparisons.
        low, high = grid.min(axis=1, keepdims=True), grid.max(axis=1, keepdims=True)
        scaled = (grid - low) / np.maximum(high - low, 1e-12)
        fig, ax = plt.subplots(figsize=(9.5, 7.5))
        ax.imshow(scaled, cmap="Blues", vmin=0, vmax=1, aspect="auto")
        ax.set_xticks(range(4), ALGORITHMS)
        ax.set_yticks(range(10), [s.replace(",", "+") for s in SUBSETS])
        ax.axhline(5.5, color="black", linewidth=0.7)
        ax.set_xlabel("Algorithm")
        ax.set_ylabel("Optimized objective subset")
        for i in range(10):
            for j in range(4):
                ax.text(j, i, format(grid[i, j], fmt), ha="center", va="center",
                        color="white" if scaled[i, j] > .6 else "black", fontsize=16)
        fig.tight_layout()
        export(fig, directory / filename)
        plt.close(fig)
    lookup = {(row["subset"], row["algorithm"]): row["igd_plus_run_median"] for row in secondary["aggregates"]}
    grid = np.asarray([[lookup[(subset, method)] for method in ALGORITHMS] for subset in SUBSETS])
    low, high = grid.min(axis=1, keepdims=True), grid.max(axis=1, keepdims=True)
    scaled = (grid - low) / np.maximum(high - low, 1e-12)
    fig, ax = plt.subplots(figsize=(9.5, 7.5))
    ax.imshow(scaled, cmap="Blues_r", vmin=0, vmax=1, aspect="auto")
    ax.set_xticks(range(4), ALGORITHMS)
    ax.set_yticks(range(10), [s.replace(",", "+") for s in SUBSETS])
    ax.axhline(5.5, color="black", linewidth=0.7)
    ax.set_xlabel("Algorithm")
    for i in range(10):
        for j in range(4):
            ax.text(j, i, f"{grid[i,j]:.3f}", ha="center", va="center",
                    color="white" if scaled[i, j] < .4 else "black", fontsize=16)
    fig.tight_layout()
    export(fig, directory / "igd-plus.pdf")
    plt.close(fig)


def local_fronts(matrix: Path, root: Path, directory: Path) -> None:
    configure()
    with matrix.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    first_person = rows[0]["person_day_id"]
    groups = defaultdict(list)
    for row in rows:
        if row["person_day_id"] == first_person and row["objective_subset"] in ("N,C", "N,C,W") and row["replicate_id"] == "1":
            groups[row["objective_subset"]].append(row)
    for subset, selected in groups.items():
        names = subset.split(",")
        fig = plt.figure(figsize=(10, 8))
        ax = fig.add_subplot(111, projection="3d" if len(names) == 3 else None)
        all_values = []
        for row in selected:
            with (root / row["run_id"] / "front.jsonl").open(encoding="utf-8") as stream:
                front = [json.loads(line) for line in stream]
            values = np.asarray([[item["evaluation"]["normalized"][name] for name in names] for item in front])
            all_values.append(values)
            if len(names) == 2:
                ax.scatter(values[:, 0], values[:, 1], s=28, alpha=.8, label=row["algorithm"])
            else:
                ax.scatter(values[:, 0], values[:, 1], values[:, 2], s=28, alpha=.8, label=row["algorithm"])
        union = first_front(np.concatenate(all_values))
        if len(names) == 2:
            ax.plot(union[:, 0], union[:, 1], color="black", linewidth=.8, label="Pooled nondominated")
        ax.set_xlabel(names[0] + " normalized")
        ax.set_ylabel(names[1] + " normalized")
        if len(names) == 3:
            ax.set_zlabel(names[2] + " normalized")
        ax.legend(loc="upper center", bbox_to_anchor=(.5, 1.14), ncol=2, frameon=False)
        fig.tight_layout()
        export(fig, directory / ("local-front-" + subset.replace(",", "-") + ".pdf"))
        plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--secondary", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--matrix", type=Path)
    parser.add_argument("--runs-root", type=Path)
    args = parser.parse_args(argv)
    primary = json.loads(args.primary.read_text(encoding="utf-8"))
    secondary = json.loads(args.secondary.read_text(encoding="utf-8"))
    if primary["input_sha256"] != secondary["input_sha256"]:
        raise ValueError("Aggregate analyses use different campaigns")
    aggregate_figures(primary, secondary, args.output_dir)
    if bool(args.matrix) != bool(args.runs_root):
        raise ValueError("Provide both matrix and runs root for local fronts")
    if args.matrix:
        local_fronts(args.matrix, args.runs_root, args.output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
