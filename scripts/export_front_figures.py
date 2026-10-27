"""Render full and two-panel front figures from the saved representative runs."""

import argparse
from pathlib import Path

import numpy as np

from sec_diet.instances import read_json
from sec_diet.profile_results import AXES, plot_fronts
from sec_diet.publication_outputs import read_csv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    design = read_json(args.campaign / "study.json")["design"]
    representatives = {}
    for row in read_csv(args.campaign / "article/figure-run-selections.csv"):
        with np.load(args.campaign / "runs" / row["run_id"] / "front.npz",
                     allow_pickle=False) as front:
            representatives[(row["profile_id"], row["objective_subset"], row["algorithm"])] = {
                "raw": front["raw"].copy()
            }
    if design.get("nutrition_objective") == "capped_attainment_percent":
        AXES["N"] = "Nutrient attainment (%)"
    plot_fronts(representatives, design, args.output)
    print(f"Saved vector front figures to {args.output}")


if __name__ == "__main__":
    main()
