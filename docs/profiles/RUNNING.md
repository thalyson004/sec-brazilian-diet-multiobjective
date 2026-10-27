# Running the whole-meal profile study

This guide covers the campaign, published diet reconstruction and article outputs. Commands are run from the repository root. The [main README](../../README.md) lists the input sources and installation steps.

## Run a campaign

On Windows, with `Dados_20230713.zip` and the environmental workbook in `data/raw/`:

```powershell
.\run-study.ps1 `
  -Pof "data/raw/Dados_20230713.zip" `
  -Footprints "data/raw/pegadas_alimentos.xlsx" `
  -OutputDir "results/sec2026-reproduction" `
  -Penalty -Workers 8
```

The wrapper creates `.venv` if needed and installs the experiment and figure dependencies. Use a clean committed checkout so the campaign can record its code revision. The published experiment used Python 3.14.4 and the package versions in [requirements-experiment.lock](../../requirements-experiment.lock).

The equivalent Python command works on other platforms after installation:

```bash
.venv/bin/python scripts/run_profile_study.py \
  --pof data/raw/Dados_20230713.zip \
  --footprints data/raw/pegadas_alimentos.xlsx \
  --output-dir results/sec2026-reproduction \
  --penalty --workers 8
```

The default campaign runs four algorithms for four profiles, six objective sets and 20 replications, with 16,500 evaluations per run. It prepares the meal pools, runs the optimizers, checks the saved results and generates the analyses and menu reconstructions. Use a new output directory for a new campaign.

`-Penalty` or `--penalty` uses the weight 5 selected in the [reduced study](PENALTY.md). An explicit weight can be supplied with `-PenaltyWeight` or `--penalty-weight`. `-NoPenalty` or `--no-penalty` uses the capped nutritional objective without the additional shortage penalty; store that formulation in a separate directory.

## Prepare, resume and analyze

Add these options to the corresponding command above:

| Windows | Python | Purpose |
| --- | --- | --- |
| `-PrepareOnly` | `--prepare-only` | Prepare inputs and the run matrix without optimization |
| `-Resume` | `--resume` | Check and continue an existing campaign |
| `-AnalyzeOnly` | `--analyze-only` | Check completed runs and regenerate analyses |

Resume with the same input files, code revision, output directory and experimental settings. The worker count may change. Partial or invalid run directories are reported rather than silently replaced. The published numerical campaign recorded execution revision `b36df1b943a9f24b338656d006c720da1ff891f5`; its saved results and a new execution have separate provenance.

## Campaign outputs

| Path within the campaign directory | Contents |
| --- | --- |
| `study.json`, `execution.json`, `completion.json` | Design, execution environment and completed run counts |
| `runs/<run_id>/evaluations.npz` | Evaluated meal indices, outcomes and constraints |
| `runs/<run_id>/search-front.npz` | Penalized search archive |
| `runs/<run_id>/front.npz` | Reporting front used for the published indicators |
| `article/` | Indicators, nutrient summaries, figures, tables and analysis manifest |
| `interpretation/` | Reconstructed front menus, illustrative diets and food-mass summaries |
| `publication/` | Figures and tables prepared from the saved campaign |

The reporting front is an unpenalized nondominated subset of a run's penalized search archive. Food-code mean and sample standard deviation use 20 selected menus for each profile, objective set and algorithm; absent foods contribute zero. Complete evaluation histories and the reconstructed source meal pools stay in local output directories.

## Reproduce the final comparison bundle

After a campaign completes, run:

```powershell
.venv\Scripts\python scripts/export_reference_analysis.py `
  --campaign results/sec2026-reproduction `
  --pof data/raw/Dados_20230713.zip `
  --footprints data/raw/pegadas_alimentos.xlsx `
  --output results/reference-comparison
```

The output path must be new. This postprocessing command exports the reporting fronts, extracts the observed diets, analyzes choices on the saved fronts and selects reference-constrained menus from all energy-feasible evaluated candidates. The generated `comparisons/reference-compromise-v1/` directory contains `observed-comparison.tex` and `nutrition-selections.tex`; the sensitivity directory contains `compromise-feasibility.tex`.

The reference-constrained rule selects one menu per run that improves nutrient attainment, carbon, water and departure relative to the corresponding observed profile means. It then minimizes the four-coordinate normalized distance. These choices may lie outside the original reporting front. The published [reference selections](../../comparisons/reference-compromise-v1/README.md), [observed diets](../../comparisons/observed-profile-energy-context/README.md) and [front-based sensitivity](../../comparisons/compromise-selection-v1/README.md) include file descriptions and independent commands.

To extract observed diets for one profile without a completed optimizer campaign:

```powershell
.venv\Scripts\python scripts/extract_observed_comparison.py `
  --pof data/raw/Dados_20230713.zip `
  --footprints data/raw/pegadas_alimentos.xlsx `
  --profile F30 --output results/observed-f30
```

## Published reporting fronts

The [front release](../../fronts/meal-profile-study-v4.1-penalty-5/README.md) contains 480 fronts per profile and 15,022 menu entries across the four profiles. `runs.csv` identifies the run, `points.csv` contains the objective values, and `menus.jsonl.gz` contains the corresponding six-position food and portion lists. See the release guide for units and the relationship between front offsets and candidate identifiers.

With the completed campaign and its `interpretation/` output, regenerate the release in a new directory:

```powershell
.venv\Scripts\python scripts/export_public_fronts.py `
  --campaign results/sec2026-reproduction `
  --output results/public-fronts-reproduction
```

## Publication layout from saved results

To render the article's figures and tables from a completed campaign:

```powershell
.venv\Scripts\python scripts/export_publication.py `
  --campaign results/sec2026-reproduction `
  --output results/publication-layout
```

For front figures only:

```powershell
.venv\Scripts\python scripts/export_front_figures.py `
  --campaign results/sec2026-reproduction `
  --output results/front-layout
```

The front renderer uses the saved representative-run selection and `front.npz` files. It produces full figures and two-panel `row-1`/`row-2` versions in PDF and SVG. The rows keep the same points, axis limits and supported 3D surfaces as the full figures. The publication renderer also uses saved dietary and reconstruction outputs. Neither command runs an optimizer.

### Table typesetting

Menu tables align meal-position labels to the left. The sensitivity table uses the CAS placement option `[pos=htbp]`. These settings affect presentation; the manuscript's LaTeX packages are separate from the Python experiment dependencies.
