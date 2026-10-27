# Observed diets under the study's energy intervals

This release accompanies the descriptive observed-versus-optimized comparison added on 23 October 2026. No evolutionary optimization was repeated.

## Selection

The script rebuilds the original POF cohort from independently obtained source files, using the frozen profiles, exact sex/age, complete-day/linkage filters, six-meal mapping and original deterministic one-day-per-respondent rule. Canonical instance hashes must reproduce the executed study. It then retains only the originally chosen days within each profile's unchanged hard energy interval (±5%). No second day is substituted, portions are not rescaled, and nutrient quality or footprints do not determine selection. These are reference requirements, not measured requirements of individual survey participants.

| Profile | Original retained respondents | Included | Energy interval (kcal/day) |
| --- | ---: | ---: | ---: |
| F30 | 437 | 27 | 2058.98402–2275.71918 |
| F60 | 339 | 38 | 1808.08602–1998.41087 |
| M30 | 347 | 24 | 2599.85156–2873.52015 |
| M60 | 248 | 19 | 2225.03367–2459.24774 |

The observed total is 108 distinct respondents, one unchanged day each. Each optimized profile contributes its original 480 compromise selections (six scenarios, four algorithms, 20 repetitions). Global indicators average the four profile means equally. The two sides are not paired individuals, exact energy distributions differ, and no survey or population inference is intended. The observed subset belongs to the same data used to construct the meal pools; it is not an independent validation set.

## Files

- `F30-complete-diets.json`, `F60-complete-diets.json`, `M30-complete-diets.json`, `M60-complete-diets.json`: all selected observed days, including the six positions, empty meals, food/preparation codes, English names/groups and recorded grams. Source day identifiers are opaque hashes.
- `optimized-complete-diets.jsonl`: all 1,920 compared compromise menus, with six indices into reconstructed profile pools, complete food/portion lists, run identifiers and outcomes. Repeated menus across runs remain in the file.
- `observed-outcomes.csv`, `optimized-outcomes.csv`: daily energy, capped attainment, target count, carbon/water and simultaneous target attainment.
- `selection-flow.csv`: counts and exact energy limits.
- `comparison-summary.json`: profile means, sample SD within each side, and equal-profile global means.
- `observed-comparison.tex`, `observed-profiles.tex`: manuscript tables generated from the summaries.
- `manifest.json`: source, protocol, extraction script and output hashes. The protocol is `docs/profiles/observed-comparison-protocol.json`.

Food-level nutrient coefficients and private prepared pools are not redistributed. Daily menu outcomes are reported, and source reconstruction is available through the script. The complete quantity lists are available for inspection and reuse; the source workbook and nutrient composition must be obtained independently for rescoring.

## Reproduce just one observed profile

From the standalone repository, install the documented dependencies and run:

```powershell
.venv\Scripts\python scripts/extract_observed_comparison.py `
  --pof C:\data\Dados_20230713.zip `
  --footprints C:\data\pegadas_alimentos.xlsx `
  --profile F30 --output results\observed-F30
```

Omit `--profile` to extract all four, or repeat it for selected profiles. This mode needs no optimizer outputs and creates no optimized comparison. Reuse the exact source versions identified in the manifest. Output directories must be new, protecting previous extractions.

## Reproduce the full article comparison

With the completed main campaign present:

```powershell
.venv\Scripts\python scripts/extract_observed_comparison.py `
  --pof C:\data\Dados_20230713.zip `
  --footprints C:\data\pegadas_alimentos.xlsx `
  --campaign results\meal-profile-study-v4.1-penalty-5 `
  --output results\observed-comparison-reproduction
```

The script independently rescores every saved optimized selection and checks its values against the recorded outcomes. All observed and optimized menus must satisfy the same profile energy limits. It writes the complete comparison, data and LaTeX tables without starting an optimizer.
