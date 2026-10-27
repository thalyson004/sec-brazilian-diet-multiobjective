# Multiobjective Optimization of Brazilian Diets

Code and data for **Multiobjective Evolutionary Optimization of Observed Brazilian Meals across Dietary Reference Profiles**. The study compares four evolutionary algorithms using food-consumption records from the Brazilian Household Budget Survey (POF) 2017-2018.

A diet is assembled from six complete observed meals: breakfast, morning snack, lunch, afternoon snack, dinner and supper. Each selected meal keeps its recorded foods and portions. A position can be empty when that absence was observed in the corresponding profile.

## Published results

| Data | Contents |
| --- | --- |
| [Pareto fronts and menus](fronts/meal-profile-study-v4.1-penalty-5/README.md) | All 1,920 reporting fronts and 15,022 menu entries, with food names and portions |
| [Observed diets](comparisons/observed-profile-energy-context/README.md) | 108 observed days within the energy intervals of their respective profiles |
| [Reference-constrained selections](comparisons/reference-compromise-v1/README.md) | 1,920 selected menus, nutrient outcomes and food-type means and standard deviations |
| [Front-based sensitivity analysis](comparisons/compromise-selection-v1/README.md) | Comparison of selection rules on the saved reporting fronts |

The 15,022 entries are counted across runs; a menu may appear in more than one run. The reference-constrained selections use all energy-feasible menus evaluated in each run and therefore may lie outside the saved reporting fronts. Their complete menus are available, while full evaluation histories and unselected source meal pools remain local.

## Study design

The profiles represent women and men aged 30 and 60. Each assumes low physical activity and weight maintenance. The energy interval is set to 95%-105% of the profile's estimated maintenance requirement.

| Profile | Reference person | Energy interval (kcal/day, rounded) |
| --- | --- | ---: |
| F30 | Woman, 30 years | 2,059-2,276 |
| F60 | Woman, 60 years | 1,808-1,998 |
| M30 | Man, 30 years | 2,600-2,874 |
| M60 | Man, 60 years | 2,225-2,459 |

The four objectives are nutrient attainment (N), carbon footprint (C), water footprint (W) and departure from the profile's observed food quantities (D). The study considers NC, NW and ND pairs and NCW, NCD and NWD triples. Nutrient attainment combines 23 criteria; lower requirements and applicable upper limits are assessed separately for each criterion. A shortage penalty of 5 is applied to the normalized non-nutritional search objectives. The value was selected in a [reduced study](docs/profiles/PENALTY.md).

NSGA-II, SPEA2, NSGA-III and SMS-EMOA were run for each profile and objective set, with 20 replications and 16,500 objective-function evaluations per run: **1,920 runs** and **31.68 million evaluations**. See the [profile definitions](docs/profiles/DECISIONS.md) for the anthropometry, nutrient targets and meal preparation rules.

## Installation

Python 3.11 or newer is required. The reported environment used Python 3.14.4; the recorded package versions are in [requirements-experiment.lock](requirements-experiment.lock).

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[experiment,figures]"
```

On Linux or macOS, create the environment with `python3 -m venv .venv` and install the same dependencies with `.venv/bin/python -m pip install -e ".[experiment,figures]"`. The published menu lists can be read with Python's standard library; NumPy is needed for the NPZ front arrays.

To run the software checks on Windows:

```powershell
.venv\Scripts\python -m unittest discover -s tests -v
```

## Input data

Download the following files and place them in `data/raw/`:

| Input | Source |
| --- | --- |
| `Dados_20230713.zip` | [IBGE POF 2017-2018 microdata](https://ftp.ibge.gov.br/Orcamentos_Familiares/Pesquisa_de_Orcamentos_Familiares_2017_2018/Microdados/) |
| `pegadas_alimentos.xlsx` | [Environmental footprint workbook](https://osf.io/download/fv3tx/) |

The IBGE documentation archive is also available from the microdata directory. The [data guide](data/README.md) links the source checksums and explains which files are distributed. Raw inputs, food-level nutrient coefficients and reconstructed source meal pools are not included in the repository.

## Run the study

From the repository root on Windows:

```powershell
.\run-study.ps1 `
  -Pof "data/raw/Dados_20230713.zip" `
  -Footprints "data/raw/pegadas_alimentos.xlsx" `
  -OutputDir "results/sec2026-reproduction" `
  -Penalty -Workers 8
```

This prepares the profile-specific meal pools, executes the 1,920 runs and generates analyses, figures, tables and reconstructed menus. It uses the saved penalty selection of 5. Choose a new output directory for a new campaign. Results are written under `results/`, which Git ignores.

On other platforms, use the Python entry point after installation:

```bash
.venv/bin/python scripts/run_profile_study.py \
  --pof data/raw/Dados_20230713.zip \
  --footprints data/raw/pegadas_alimentos.xlsx \
  --output-dir results/sec2026-reproduction \
  --penalty --workers 8
```

Use `-PrepareOnly` to prepare the inputs without running the algorithms, or `-Resume` to resume the same campaign. `-NoPenalty` selects the separate no-penalty formulation. The [execution guide](docs/profiles/RUNNING.md) describes the equivalent Python flags, resuming, calibration and output files.

After a campaign has completed, reproduce the final comparison files with:

```powershell
.venv\Scripts\python scripts/export_reference_analysis.py `
  --campaign results/sec2026-reproduction `
  --pof data/raw/Dados_20230713.zip `
  --footprints data/raw/pegadas_alimentos.xlsx `
  --output results/reference-comparison
```

This is a postprocessing step; it reads the saved campaign and does not run the optimizers again. The published comparison uses observed profile means as references, rather than paired individual diets. Global summaries give each profile equal weight.

## Inspect a published menu

The following example prints one saved F30 menu and its recorded portions. It does not require the original input files or an optimization run.

```python
import gzip
import json

path = "fronts/meal-profile-study-v4.1-penalty-5/F30/menus.jsonl.gz"
with gzip.open(path, "rt", encoding="utf-8") as stream:
    menu = json.loads(next(stream))

print(menu["run_id"], menu["outcomes"])
for meal in menu["meals"]:
    print(meal["position"])
    for food in meal["items"]:
        print("  ", food["food_name"], food["grams"], "g")
```

The release includes `runs.csv`, `selections.csv`, per-profile `points.csv`, compressed menu lists and the original NumPy front arrays. See the [fronts guide](fronts/meal-profile-study-v4.1-penalty-5/README.md) for identifiers, objective units and file formats.

## Repository layout

| Path | Contents |
| --- | --- |
| `src/sec_diet/` | Data preparation, optimization models and analysis code |
| `scripts/` | Study execution, diet extraction and result export |
| `run-study.ps1` | Windows entry point for the complete campaign |
| `fronts/` | Published reporting fronts and complete optimized menus |
| `comparisons/` | Observed diets and selection analyses |
| `docs/profiles/` | Profile definitions, nutrient targets and execution guide |
| `data/` | Local input and prepared-data directories |
| `tests/` | Checks for the models, algorithms and result generation |

`docs/protocol/` and `docs/analysis/` describe an earlier respondent-day benchmark. The active article uses the whole-meal profile design described above.

## Citation

Publication details will be added when the article is available.

## License

The original code is available under the [MIT License](LICENSE). The POF data and environmental workbook have their own source terms and are obtained separately.
