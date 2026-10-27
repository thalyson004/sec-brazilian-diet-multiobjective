"""Reconstruct saved Pareto menus and summarize food masses without rerunning search.

The compressed full-front export is local and ignored by Git. Published example
tables use one fixed algorithm and a deterministic representative run per cell.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from openpyxl import load_workbook

from sec_diet.instances import read_json
from sec_diet.layout import code
from sec_diet.source_checks import FOOTPRINT_SHEET
from sec_diet.english_labels import english_food, english_group, food_labels


SUBSET_LABELS = {"N,C": "NC", "N,W": "NW", "N,D": "ND",
                 "N,C,W": "NCW", "N,C,D": "NCD", "N,W,D": "NWD"}
POSITIONS = ("Breakfast", "Morning snack", "Lunch", "Afternoon snack", "Dinner", "Supper")
PROFILES = ("F30", "F60", "M30", "M60")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_labels(path: Path) -> dict[str, str]:
    book = load_workbook(path, read_only=True, data_only=True)
    try:
        labels = {}
        for row in book[FOOTPRINT_SHEET].iter_rows(min_row=4, values_only=True):
            if row and isinstance(row[0], (int, float)) and row[1]:
                key = code(row[0])
                value = str(row[1]).strip().capitalize()
                # Four labels in the supplied workbook contain damaged accent
                # sequences; repair their displayed names without changing keys.
                value = value.replace("francã‹s", "francês").replace("inglã‹s", "inglês").replace("h2ohâ®", "H2OH")
                # A few codes have preparation-specific label variants. The
                # longest description keeps the food type recognizable.
                if len(value) > len(labels.get(key, "")):
                    labels[key] = value
        return {key:english_food(key) for key in labels if key in food_labels()}
    finally:
        book.close()


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def tex(value: str) -> str:
    for old, new in (("\\", "\\textbackslash{}"), ("&", "\\&"), ("%", "\\%"),
                     ("_", "\\_"), ("#", "\\#"), ("$", "\\$"),
                     ("{", "\\{"), ("}", "\\}")):
        value = value.replace(old, new)
    return value


def item_masses(meals: list[dict]) -> dict[str, float]:
    totals = defaultdict(float)
    for meal in meals:
        for item in meal["items"]:
            totals[item["food_code"]] += float(item["grams"])
    return dict(totals)


def render_example_table(subset: str, menus: dict[str, dict], labels: dict[str, str]) -> str:
    header=r"Position & F30 & F60 & M30 & M60 \\"
    lines = [r"{\small", r"\setlength{\tabcolsep}{3pt}",
             r"\begin{longtable}{@{}>{\raggedright\arraybackslash}p{.075\textwidth}*{4}{>{\raggedright\arraybackslash}p{.215\textwidth}}@{}}",
             r"\caption{Illustrative six-position menus for the " + SUBSET_LABELS[subset] +
             r" objectives, using the common representative NSGA-II rule. Foods retain observed portions; ``Empty'' denotes a source-observed absent meal. These examples are descriptive, not recommended diets.}",
             r"\label{tab:menu-" + SUBSET_LABELS[subset].lower() + r"}\\",
             r"\toprule",header,r"\midrule",r"\endfirsthead",
             r"\multicolumn{5}{l}{\tablename\ \thetable\ (continued)}\\",
             r"\toprule",header,r"\midrule",r"\endhead",
             r"\midrule\multicolumn{5}{r}{Continued on next page}\\",r"\endfoot",
             r"\bottomrule",r"\endlastfoot"]
    for slot, position in enumerate(POSITIONS):
        cells = []
        for profile in PROFILES:
            items = menus[profile]["meals"][slot]["items"]
            if not items:
                cells.append("Empty")
            else:
                cells.append("; ".join(f"{tex(labels[i['food_code']])} "
                                       f"({float(i['grams']):g} g)" for i in items))
        lines.append(tex(position) + " & " + " & ".join(cells) + r" \\")
    lines.extend([r"\end{longtable}",r"}", ""])
    return "\n".join(lines)


def render_mass_table(rows: list[dict], replicates: int) -> str:
    chosen = ("6303102", "6300113", "6803201", "8216301")
    lookup = {(r["objective_subset"], r["algorithm"], r["food_code"]): r
              for r in rows if r["profile_id"] == "F30" and r["food_code"] in chosen}
    lines = [r"\begin{table*}[t]", r"\centering\small", r"\setlength{\tabcolsep}{4pt}",
             r"\caption{Daily food-type grams in the F30 compromise menus, mean $\pm$ sample standard deviation over " + str(replicates) + r" independent runs per algorithm and objective set. A food absent in a run contributes zero grams. The four codes represent beans (6303102), white rice (6300113), mango (6803201) and tap water (8216301); the complete code-level matrix for all profiles and foods is in the companion CSV. Tap water is shown separately because it is omitted from the departure objective.}",
             r"\label{tab:food-type-mass}", r"\begin{tabular}{@{}llrrrr@{}}", r"\toprule",
             r"Objectives & Algorithm & Beans & White rice & Mango & Tap water \\", r"\midrule"]
    for subset in SUBSET_LABELS:
        for algorithm in ("NSGA2", "SPEA2", "NSGA3", "SMSEMOA"):
            cells = []
            for food_code in chosen:
                row = lookup.get((subset, algorithm, food_code))
                cells.append(f"{row['mean_g']:.1f} $\\pm$ {row['sd_g']:.1f}" if row else r"0.0 $\pm$ 0.0")
            lines.append(SUBSET_LABELS[subset] + " & " + algorithm.replace("NSGA2", "NSGA-II").replace("NSGA3", "NSGA-III").replace("SMSEMOA", "SMS-EMOA") + " & " + " & ".join(cells) + r" \\")
        if subset != "N,W,D":
            lines.append(r"\addlinespace")
    lines.extend([r"\bottomrule", r"\end{tabular}", r"\end{table*}", ""])
    return "\n".join(lines)


def export(campaign: Path, footprints: Path, output: Path, table_dir: Path) -> dict:
    article = campaign / "article"
    design = read_json(campaign / "study.json")["design"]
    if tuple(design["profiles"]) != PROFILES or tuple(design["objective_subsets"]) != tuple(SUBSET_LABELS):
        raise ValueError("The illustrative tables require the registered four profiles and six objective sets")
    replicates = int(design["replicates"])
    expected_runs = len(PROFILES) * len(SUBSET_LABELS) * len(design["algorithms"]) * replicates
    rows = list(csv.DictReader((article / "run-indicators.csv").open(encoding="utf-8", newline="")))
    if len(rows) != expected_runs or any(int(r["evaluations"]) != int(design["evaluations"]) for r in rows):
        raise ValueError("The registered profile campaign is incomplete")
    selections = {(r["profile_id"], r["objective_subset"], r["algorithm"]): r["run_id"]
                  for r in csv.DictReader((article / "figure-run-selections.csv").open(encoding="utf-8", newline=""))}
    selected = {}
    with (article / "selected-menus.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            menu = json.loads(line)
            if menu["selection"] == "compromise":
                selected[menu["run_id"]] = menu
    if len(selected) != expected_runs:
        raise ValueError("One compromise menu per run is required")
    labels = load_labels(footprints)
    # The preparation directory is content-addressed separately from its manifest.
    dirs = [p for p in (campaign / "inputs").iterdir() if p.is_dir() and all((p / f"{v}.json").exists() for v in PROFILES)]
    if len(dirs) != 1:
        raise ValueError("Cannot unambiguously locate the four meal pools")
    instance_root = dirs[0]
    execution = read_json(campaign / "execution.json")
    input_manifest = read_json(instance_root / "manifest.json")
    if digest(instance_root / "manifest.json") != execution["instance_manifest_sha256"]:
        raise ValueError("Prepared meal pools do not match the saved execution")
    if digest(footprints) != input_manifest["sources"]["footprints"]["sha256"]:
        raise ValueError("Food-label workbook differs from the saved campaign input")
    instances = {p: read_json(instance_root / f"{p}.json") for p in PROFILES}
    used_codes={item['food_code'] for instance in instances.values() for pool in instance['meal_pools'] for meal in pool for item in meal['items']}
    if used_codes-set(labels):
        raise ValueError(f"Missing English food descriptions: {sorted(used_codes-set(labels))}")
    baseline_by_profile={}
    for profile,instance in instances.items():
        totals=defaultdict(float)
        for variable,grams in zip(instance['variables'],instance['baseline_g']):totals[variable['food_code']]+=float(grams)
        observed_water=[]
        for vector in instance['observed_diets']:
            observed_water.append(sum(item['grams'] for slot,index in enumerate(vector)
                for item in instance['meal_pools'][slot][int(index)]['items'] if item['tap_water']))
        totals['8216301']=float(np.mean(observed_water))
        baseline_by_profile[profile]=dict(totals)
    output.mkdir(parents=True, exist_ok=True)
    table_dir.mkdir(parents=True, exist_ok=True)
    mass_by_cell = defaultdict(list)
    group_by_code = {}
    profile_codes={}
    for profile,instance in instances.items():
        profile_codes[profile]=set()
        for pool in instance['meal_pools']:
            for meal in pool:
                for item in meal['items']:
                    key=item['food_code'];group=item['food_group']
                    if key in group_by_code and group_by_code[key]!=group:raise ValueError(f'Inconsistent source group for {key}')
                    group_by_code[key]=group;profile_codes[profile].add(key)
    front_count = 0
    with (output / "all-pareto-menus.jsonl.gz").open("wb") as raw_stream, \
         gzip.GzipFile(fileobj=raw_stream, mode="wb", filename="", mtime=0, compresslevel=6) as compressed, \
         io.TextIOWrapper(compressed, encoding="utf-8") as stream:
        for row in rows:
            profile, subset, algorithm = row["profile_id"], row["objective_subset"], row["algorithm"]
            instance = instances[profile]
            with np.load(campaign / "runs" / row["run_id"] / "front.npz", allow_pickle=False) as front:
                X, raw, normalized, indices = (front[k] for k in ("X", "raw", "normalized", "indices"))
                if len(X) != int(row["front_size"]):
                    raise ValueError(f"Front size mismatch: {row['run_id']}")
                for i, vector in enumerate(X):
                    meals = []
                    for slot, index in enumerate(vector):
                        meal = instance["meal_pools"][slot][int(index)]
                        meals.append({"position": instance["meal_slots"][slot], "meal_index": int(index),
                                      "meal_id": meal.get("meal_id"), "items": meal["items"]})
                    entry = {"run_id": row["run_id"], "profile_id": profile, "objective_subset": subset,
                             "algorithm": algorithm, "replicate": int(row["replicate"]),
                             "candidate_index": int(indices[i]), "raw_NCWD": raw[i].tolist(),
                             "normalized_NCWD": normalized[i].tolist(), "meals": meals}
                    stream.write(json.dumps(entry, ensure_ascii=False, allow_nan=False, separators=(",", ":")) + "\n")
                    front_count += 1
            menu = selected[row["run_id"]]
            amounts = item_masses(menu["meals"])
            mass_by_cell[(profile, subset, algorithm)].append((int(row["replicate"]), amounts))
            for meal in menu["meals"]:
                for item in meal["items"]:
                    key = item["food_code"]
                    group = item["food_group"]
                    if key in group_by_code and group_by_code[key] != group:
                        raise ValueError(f"Food code {key} has inconsistent groups")
                    group_by_code[key] = group
    if front_count != sum(int(r["front_size"]) for r in rows):
        raise ValueError("Missing Pareto menus")
    summaries = []
    group_summaries = []
    total_summaries = []
    scope_codes = defaultdict(set)
    for profile in PROFILES:
        for subset in SUBSET_LABELS:scope_codes[(profile,subset)].update(profile_codes[profile])
    for (profile, subset, _algorithm), values in mass_by_cell.items():
        scope_codes[(profile, subset)].update(set().union(*(amounts for _, amounts in values)))
    for (profile, subset, algorithm), values in sorted(mass_by_cell.items()):
        if len(values) != replicates or {rep for rep, _ in values} != set(range(1, replicates + 1)):
            raise ValueError("Missing independent replicate menus in a cell")
        values = sorted(values)
        codes = sorted(scope_codes[(profile, subset)])
        daily_totals = np.array([sum(amounts.values()) for _, amounts in values])
        total_summaries.append({"profile_id": profile, "objective_subset": subset, "algorithm": algorithm,
                                "selection": "compromise", "replicates": replicates,
                                "mean_g": float(daily_totals.mean()), "sd_g": float(daily_totals.std(ddof=1))})
        for group in sorted({group_by_code[c] for c in codes}):
            grams = np.array([sum(v for c, v in amounts.items() if group_by_code[c] == group)
                              for _, amounts in values])
            group_summaries.append({"profile_id": profile, "objective_subset": subset,
                                    "algorithm": algorithm, "selection": "compromise", "food_group": english_group(group),
                                    "replicates": replicates, "mean_g": float(grams.mean()),
                                    "sd_g": float(grams.std(ddof=1))})
        for food_code in codes:
            grams = np.array([amounts.get(food_code, 0.) for _, amounts in values])
            summaries.append({"profile_id": profile, "objective_subset": subset, "algorithm": algorithm,
                              "selection": "compromise", "food_code": food_code,
                              "food_name": labels[food_code],
                              "food_group": english_group(group_by_code[food_code]), "replicates": replicates,
                              "present_replicates": int(np.count_nonzero(grams)),
                              "mean_g": float(grams.mean()), "sd_g": float(grams.std(ddof=1)),
                              "baseline_g": baseline_by_profile[profile].get(food_code,0.),
                              "mean_change_g": float(grams.mean())-baseline_by_profile[profile].get(food_code,0.),
                              "change_sd_g": float(grams.std(ddof=1)),
                              "relative_change_percent": 100*(float(grams.mean())/baseline_by_profile[profile][food_code]-1) if baseline_by_profile[profile].get(food_code,0.)>0 else None})
    fields = ["profile_id", "objective_subset", "algorithm", "selection", "food_code", "food_name",
              "food_group", "replicates", "present_replicates", "mean_g", "sd_g", "baseline_g", "mean_change_g", "change_sd_g", "relative_change_percent"]
    write_csv(output / "food-type-mass-summary.csv", summaries, fields)
    write_csv(output / "food-group-mass-summary.csv", group_summaries,
              ["profile_id", "objective_subset", "algorithm", "selection", "food_group", "replicates", "mean_g", "sd_g"])
    write_csv(output / "total-mass-summary.csv", total_summaries,
              ["profile_id", "objective_subset", "algorithm", "selection", "replicates", "mean_g", "sd_g"])
    (table_dir / "food-type-mass-f30.tex").write_text(render_mass_table(summaries, replicates), encoding="utf-8", newline="\n")
    example_rows = []
    for subset in SUBSET_LABELS:
        menus = {}
        for profile in PROFILES:
            run_id = selections[(profile, subset, "NSGA2")]
            menus[profile] = selected[run_id]
            example_rows.append({"profile_id": profile, "objective_subset": subset, "algorithm": "NSGA2",
                                 "run_id": run_id, "candidate_index": menus[profile]["candidate_index"],
                                 "total_food_g": sum(item_masses(menus[profile]["meals"]).values())})
        (table_dir / f"example-menu-{SUBSET_LABELS[subset].lower()}.tex").write_text(
            render_example_table(subset, menus, labels), encoding="utf-8", newline="\n")
    write_csv(output / "example-menu-index.csv", example_rows,
              ["profile_id", "objective_subset", "algorithm", "run_id", "candidate_index", "total_food_g"])
    from sec_diet.diet_figures import export_composition
    export_composition(summaries, output/'figures', table_dir)
    manifest = {"postprocessing_script_sha256": digest(Path(__file__)),
                "base_execution_sha256": digest(campaign / "execution.json"),
                "base_analysis_manifest_sha256": digest(article / "analysis-manifest.json"),
                "footprints_sha256": digest(footprints), "run_count": len(rows),
                "english_labels_sha256": digest(Path(__file__).resolve().parents[1]/'docs/profiles/food-labels-en.json'),
                "front_menu_count": front_count, "food_summary_rows": len(summaries),
                "food_group_summary_rows": len(group_summaries),
                "example_menu_count": len(example_rows),
                "all_front_sha256": digest(output / "all-pareto-menus.jsonl.gz"),
                "food_summary_sha256": digest(output / "food-type-mass-summary.csv"),
                "example_table_sha256": {p.name: digest(p) for p in sorted(table_dir.glob("example-menu-*.tex"))}}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, default=Path("results/meal-profile-study"))
    parser.add_argument("--footprints", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--table-dir", type=Path)
    args = parser.parse_args()
    output = args.output or args.campaign / "interpretation"
    tables = args.table_dir or output / "tables"
    print(json.dumps(export(args.campaign, args.footprints, output, tables), indent=2))


if __name__ == "__main__":
    main()
