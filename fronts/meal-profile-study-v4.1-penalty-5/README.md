# Complete reporting fronts: whole-meal profile study v4.1, penalty 5

This release contains all 1,920 saved reporting fronts and their 15,022 complete daily-menu entries from the finished campaign. Each profile contributes six objective sets (NC, NW, ND, NCW, NCD, NWD), four algorithms (NSGA-II, SPEA2, NSGA-III, SMS-EMOA) and 20 replications. Each run received 16,500 evaluations. Repeated menus within different runs retain their run identities. These computational menus are descriptive research results, not dietary prescriptions.

| Profile | Run fronts | Menu entries |
| --- | ---: | ---: |
| F30 | 480 | 3180 |
| F60 | 480 | 1434 |
| M30 | 480 | 7786 |
| M60 | 480 | 2622 |

## Files and correspondence

- `runs.csv`: one row per run, including profile, objective set, algorithm, replication, seed, front size, ZIP path/member and the original NPZ SHA-256.
- `<profile>/fronts.zip`: 480 original `front.npz` files named `<run_id>.npz`, preserved byte for byte. A front belongs to its own run and objective set. No cross-run or cross-scenario Pareto filtering is applied.
- `<profile>/points.csv`: one row per front entry, with metadata, candidate identifier, six meal indices, physical outcomes, unpenalized normalized coordinates and penalized search coordinates.
- `<profile>/menus.jsonl.gz`: the same entries with full six-position food/portion lists, English names/groups, food/preparation codes and grams. An empty item list denotes an observed absent position. All foods and portions in a selected meal are preserved.
- `selections.csv`: the original 5,760 rule-specific selections used for dietary summaries, keyed by `run_id` and `candidate_index`. It contains one selection per run for each of `nutrition_max`, `compromise` and `departure_min`.
- `study.json`, `execution.json`, `completion.json`: frozen design, numerical execution provenance/environment and completion counts.
- `manifest.json`: counts, source and exporter hashes, and SHA-256/byte counts for every released file.

Join `runs.csv`, points, menus and selections by `run_id`. Within a run, `candidate_index` is the identifier in the original evaluated-candidate history. `front_offset` is its zero-based row in that run's NPZ arrays. The six `meal_indices` are zero-based indices into the corresponding profile/position pools, in breakfast, morning snack, lunch, afternoon snack, dinner and supper order. Complete published food lists allow inspection without obtaining those pools.

## Objective coordinates and units

All NPZ objective arrays have four columns in N, C, W, D order, including coordinates omitted from a particular search. `raw` stores capped attainment in percent, carbon in **g CO2e/day**, water in L/day, and departure as a dimensionless fraction. `normalized` stores the unpenalized minimization coordinates: N is `1 - attainment_percent/100`, while C/W/D use fixed profile-pool bounds. `search` stores the penalized coordinates associated with those same points. `X` stores six meal indices; `indices` stores candidate identifiers.

The CSV and JSON outcome fields convert carbon to **kg CO2e/day** (`carbon_kg`) and departure to **percent** (`departure_percent`). `attainment_percent` and `water_l` retain percent and L/day. `normalized_NCWD` and `search_NCWD` retain original coordinate values. The ZIPs contain the saved reporting fronts; the larger penalized search archives and complete evaluation histories remain separate local outputs. Reporting fronts are empirical nondominated sets for their own objective subsets, not established true global Pareto fronts.

## Relation to Tables 9 and 10

The optimized side of the observed comparison uses `selection=compromise`: 480 selections per profile. The nutritional selection table separately summarizes all three rules over those same 480 runs. A run has the same weight regardless of front size; rules can choose the same menu. GLOBAL averages the four profile means equally. See the [consolidation guide](../../docs/profiles/TABLE-CONSOLIDATION.md). The complete menus in the [observed comparison](../../comparisons/observed-profile-energy-context/README.md) correspond to the compromise subset here.

## Read the files

Python standard libraries read the CSV, ZIP and compressed JSON Lines files; NumPy reads NPZ arrays. For example, from this release directory:

```python
import csv, gzip, io, json, zipfile
import numpy as np

with open('runs.csv', encoding='utf-8', newline='') as stream:
    run = next(csv.DictReader(stream))
with zipfile.ZipFile(run['archive']) as archive:
    with np.load(io.BytesIO(archive.read(run['archive_member'])), allow_pickle=False) as front:
        print(front['X'], front['raw'])
with gzip.open(run['profile_id'] + '/menus.jsonl.gz', 'rt', encoding='utf-8') as stream:
    menu = next(json.loads(line) for line in stream if json.loads(line)['run_id'] == run['run_id'])
print(menu['outcomes'], menu['meals'])
```

## Reproduce the release

From the standalone repository with the completed numerical campaign and its `interpretation/` export available locally:

```powershell
.venv/Scripts/python scripts/export_public_fronts.py --campaign results/meal-profile-study-v4.1-penalty-5 --output results/public-fronts-reproduction
```

The command starts no optimization, requires a new output directory, checks each reconstructed menu against its saved front and confirms that every saved selection is present. ZIP/GZIP timestamps and output ordering are fixed for reproducible files. Original source data and food-level nutrient coefficients are obtained separately under their source terms. The public release includes optimized food/portion lists and menu-level objectives; source nutrient coefficients and unselected meal pools remain local. To rerun the full experiment, follow [RUNNING.md](../../docs/profiles/RUNNING.md).
