"""Aggregate saved front approximations without releasing individual diets."""

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
from matplotlib import colors
from matplotlib.ticker import FormatStrFormatter

from .analysis import ALGORITHMS, digest
from .graphics import configure, export


PAIRS = ("N,C", "C,W", "N,D")
TRIPLES = ("N,C,D", "C,W,D")
SUBSETS = PAIRS + TRIPLES
METHODS = {"NSGA2": "NSGA-II", "SPEA2": "SPEA2", "NSGA3": "NSGA-III", "SMSEMOA": "SMS-EMOA"}
PALETTE = {"NSGA2": "#1465a0", "SPEA2": "#db772e", "NSGA3": "#36876a", "SMSEMOA": "#8355a6"}
LABELS = {"N": "Nutrient deviation", "C": "Carbon footprint", "W": "Water footprint", "D": "Diet departure"}
# Shared, fixed display ranges. Values outside these ranges remain in the saved fronts.
LIMITS = {"N": 0.25, "C": 0.35, "W": 0.35, "D": 1.0}


def front_values(path: Path, dimensions: tuple[str, ...]) -> np.ndarray:
    with path.open(encoding="utf-8") as stream:
        values = []
        for line in stream:
            if line.strip():
                normalized = json.loads(line)["evaluation"]["normalized"]
                values.append([normalized[name] for name in dimensions])
    result = np.asarray(values, dtype=float).reshape(-1, len(dimensions))
    if len(result) == 0 or not np.isfinite(result).all() or ((result < 0) | (result > 1)).any():
        raise ValueError(f"Invalid normalized front: {path}")
    return result


def attainment_curve(front: np.ndarray, xgrid: np.ndarray) -> np.ndarray:
    """Minimum second coordinate at or below each first-coordinate threshold."""
    bins = np.searchsorted(xgrid, front[:, 0], side="left")
    curve = np.full(len(xgrid), np.inf)
    in_range = bins < len(xgrid)
    np.minimum.at(curve, bins[in_range], front[in_range, 1])
    return np.minimum.accumulate(curve)


def attainment_surface(front: np.ndarray, xgrid: np.ndarray, ygrid: np.ndarray) -> np.ndarray:
    """Minimum third coordinate at or below both coordinate thresholds."""
    xbins = np.searchsorted(xgrid, front[:, 0], side="left")
    ybins = np.searchsorted(ygrid, front[:, 1], side="left")
    surface = np.full((len(xgrid), len(ygrid)), np.inf)
    in_range = (xbins < len(xgrid)) & (ybins < len(ygrid))
    np.minimum.at(surface, (xbins[in_range], ybins[in_range]), front[in_range, 2])
    return np.minimum.accumulate(np.minimum.accumulate(surface, axis=0), axis=1)


def summarize(stack: list[np.ndarray]) -> dict:
    values = np.stack(stack)
    # Inf is nonattainment. Thus a reported median exists only where at least
    # more than half the run fronts attain the objective threshold.
    finite = np.isfinite(values)
    with np.errstate(invalid="ignore"):
        median = np.median(values, axis=0)
    median = np.where(np.isfinite(median), median, None)
    return {"median": median.tolist(), "attainment_fraction": finite.mean(axis=0).tolist()}


def collect(matrix: Path, validation: Path, root: Path) -> dict:
    validation_record = json.loads(validation.read_text(encoding="utf-8"))
    if not validation_record["complete_matrix"] or validation_record["counts"]["complete"] != 19200 or \
            validation_record["matrix"]["sha256"] != digest(matrix):
        raise ValueError("Complete matching independent validation required")
    grouped = defaultdict(list)
    with matrix.open(newline="", encoding="utf-8") as stream:
        for row in csv.DictReader(stream):
            if row["objective_subset"] in SUBSETS:
                grouped[(row["objective_subset"], row["algorithm"])].append(row)
    if set(grouped) != {(subset, method) for subset in SUBSETS for method in ALGORITHMS}:
        raise ValueError("Incomplete selected subset/algorithm grid")

    outputs = {}
    for subset in SUBSETS:
        names = tuple(subset.split(","))
        xgrid = np.linspace(0, LIMITS[names[0]], 101)
        surface_xgrid = np.linspace(0, LIMITS[names[0]], 25) if len(names) == 3 else None
        ygrid = np.linspace(0, LIMITS[names[1]], 25) if len(names) == 3 else None
        curves, surfaces = {}, {}
        for method in ALGORITHMS:
            rows = grouped[(subset, method)]
            if len(rows) != 480 or len({(r["person_day_id"], r["replicate_id"]) for r in rows}) != 480:
                raise ValueError(f"Expected 24 respondents and 20 seeds: {subset}, {method}")
            projection_stack, surface_stack = [], []
            for row in rows:
                values = front_values(root / row["run_id"] / "front.jsonl", names)
                projection_stack.append(attainment_curve(values[:, :2], xgrid))
                if ygrid is not None:
                    surface_stack.append(attainment_surface(values, surface_xgrid, ygrid))
            curves[method] = summarize(projection_stack)
            if ygrid is not None:
                surfaces[method] = summarize(surface_stack)
        outputs[subset] = {"objectives": names, "run_fronts_per_method": 480,
                           "x_thresholds": xgrid.tolist(), "curves": curves}
        if ygrid is not None:
            outputs[subset]["surface_x_thresholds"] = surface_xgrid.tolist()
            outputs[subset]["y_thresholds"] = ygrid.tolist()
            outputs[subset]["surfaces"] = surfaces
    return {"schema_version": "1.0", "study_id": "sec2026-pof-person-day-v1",
            "input_sha256": {"matrix": digest(matrix), "full_validation": digest(validation)},
            "description": "Exploratory pointwise median best-attainable normalized objectives across all 24 respondents and 20 seeds per method; inf/nonattainment retained before medians",
            "display_limits": LIMITS, "subsets": outputs}


def style() -> None:
    configure()


def plot_pairs(report: dict, directory: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(12.5, 5.2), constrained_layout=True)
    for index, (ax, subset) in enumerate(zip(axes, PAIRS)):
        item = report["subsets"][subset]
        xname, yname = item["objectives"]
        for method in ALGORITHMS:
            median = np.asarray([np.nan if value is None else value for value in item["curves"][method]["median"]])
            ax.plot(item["x_thresholds"], median, color=PALETTE[method], lw=1.8, label=METHODS[method])
        ax.set(xlabel=f"{LABELS[xname]} threshold ({xname})", ylabel=f"Best {LABELS[yname].lower()} ({yname})",
               xlim=(0, LIMITS[xname]), ylim=(0, LIMITS[yname]))
        ax.text(0, 1.04, f"({chr(97 + index)}) {xname} + {yname}", transform=ax.transAxes)
        ax.grid(alpha=.18)
    handles, labels = axes[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside upper center", ncol=4, frameon=False)
    export(fig, directory / "fronts-2d-comparison.pdf")
    plt.close(fig)


def plot_added_objective(report: dict, directory: Path) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 9.0), sharex=True, sharey=True, constrained_layout=True)
    for index, (ax, method) in enumerate(zip(axes.flat, ALGORITHMS)):
        for subset, linestyle in (("N,C", "-"), ("N,C,D", "--")):
            item = report["subsets"][subset]
            median = [np.nan if value is None else value for value in item["curves"][method]["median"]]
            ax.plot(item["x_thresholds"], median, linestyle,
                    color=PALETTE[method], lw=1.9, label="Two objectives" if subset == "N,C" else "Three objectives")
        ax.set(xlim=(0, LIMITS["N"]), ylim=(0, LIMITS["C"]))
        ax.text(0, 1.04, f"({chr(97 + index)}) {METHODS[method]}", transform=ax.transAxes)
        ax.grid(alpha=.18)
    for ax in axes[-1]:
        ax.set_xlabel("Nutrient-deviation threshold (N)")
    for ax in axes[:, 0]:
        ax.set_ylabel("Best carbon footprint (C)")
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="outside upper center", ncol=2, frameon=False)
    export(fig, directory / "fronts-added-objective.pdf")
    plt.close(fig)


def plot_triple(report: dict, subset: str, directory: Path) -> None:
    item = report["subsets"][subset]
    xname, yname, zname = item["objectives"]
    x, y = np.meshgrid(item["surface_x_thresholds"], item["y_thresholds"], indexing="ij")
    fig = plt.figure(figsize=(12.5, 11.2))
    scale = colors.Normalize(vmin=0, vmax=LIMITS[zname])
    axes = []
    for index, method in enumerate(ALGORITHMS, 1):
        ax = fig.add_subplot(2, 2, index, projection="3d")
        axes.append(ax)
        z = np.asarray([[np.nan if value is None else value for value in row]
                        for row in item["surfaces"][method]["median"]])
        z = np.ma.masked_invalid(z)
        ax.plot_surface(x, y, z, cmap="viridis_r", norm=scale,
                        edgecolor="#d0d5db", linewidth=.2, antialiased=True, alpha=1,
                        rcount=25, ccount=25)
        ax.set(xlabel=f"{xname} threshold", ylabel=f"{yname} threshold", zlabel=f"Best {zname}",
               xlim=(0, LIMITS[xname]), ylim=(0, LIMITS[yname]), zlim=(0, LIMITS[zname]))
        ax.set_box_aspect((1, 1, .85), zoom=.8)
        ax.view_init(elev=32, azim=-130)
        ax.tick_params(labelsize=16, pad=3)
        ax.xaxis.labelpad = 11
        ax.yaxis.labelpad = 11
        ax.zaxis.labelpad = 8
        ax.set_xticks(np.linspace(0, LIMITS[xname], 3))
        ax.set_yticks(np.linspace(0, LIMITS[yname], 3)[1:])
        ax.set_zticks([0, .5, 1])
        ax.xaxis.set_major_formatter(FormatStrFormatter("%g"))
        ax.yaxis.set_major_formatter(FormatStrFormatter("%g"))
        ax.text2D(.5, 1.02, f"({chr(96 + index)}) {METHODS[method]}",
                  transform=ax.transAxes, ha="center", color="#17304d")
    fig.subplots_adjust(left=.02, right=.88, top=.93, bottom=.09, hspace=.15, wspace=.02)
    cax = fig.add_axes([.925, .19, .022, .64])
    bar = fig.colorbar(plt.cm.ScalarMappable(norm=scale, cmap="viridis_r"), cax=cax)
    bar.set_label(f"Median best {LABELS[zname].lower()} ({zname})")
    export(fig, directory / ("fronts-3d-" + subset.replace(",", "-") + ".pdf"))
    plt.close(fig)

    # A matching map gives an unobstructed view of the same threshold summary.
    fig, axes = plt.subplots(2, 2, figsize=(11.5, 9.5), layout="constrained")
    for index, (ax, method) in enumerate(zip(axes.flat, ALGORITHMS)):
        z = np.asarray([[np.nan if value is None else value for value in row]
                        for row in item["surfaces"][method]["median"]])
        image = ax.pcolormesh(x, y, z, cmap="viridis_r", norm=scale, shading="nearest")
        ax.set(xlabel=f"{LABELS[xname]} threshold ({xname})",
               ylabel=f"{LABELS[yname]} threshold ({yname})")
        ax.text(0, 1.04, f"({chr(97 + index)}) {METHODS[method]}", transform=ax.transAxes)
    bar = fig.colorbar(image, ax=list(axes.flat), shrink=.9)
    bar.set_label(f"Median best {LABELS[zname].lower()} ({zname})")
    export(fig, directory / ("fronts-threshold-map-" + subset.replace(",", "-") + ".pdf"))
    plt.close(fig)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--validation", required=True, type=Path)
    parser.add_argument("--runs-root", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args(argv)
    report = collect(args.matrix, args.validation, args.runs_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    style()
    plot_pairs(report, args.output_dir)
    plot_added_objective(report, args.output_dir)
    for subset in TRIPLES:
        plot_triple(report, subset, args.output_dir)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"selected_subsets": list(SUBSETS), "run_fronts": 9600,
                      "figures": 4, "report": str(args.report)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
