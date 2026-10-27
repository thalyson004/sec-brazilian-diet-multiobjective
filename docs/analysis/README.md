# Confirmatory analysis, 2 October 2026

> This document describes the earlier respondent-day benchmark. The current article uses the [whole-meal profile study](../profiles/README.md).

The complete, independently rescored campaign is documented in [the execution validation](../validations/2026-10-02-execution-completeness.md). The local input to these analyses is `results/full-matrix-validation.json`, whose SHA-256 is `5df4ab8d1fecd29fcc68e3b5a79038912fcea7f655baa522d10e525532a96c7f`. All 19,200 campaign run directories, their 31,680,000 evaluated candidates, and the 24 instance files remain local. The two repository JSON records contain aggregate statistics only, without respondent IDs, food coefficients or diet vectors.

| Published record | SHA-256 | Contents |
| --- | --- | --- |
| [`primary-analysis.json`](primary-analysis.json) | `76a0c83d0c57cca56f6a073c377702164f1032ad55af2c089340fe91548c7128` | 40 subset/algorithm summaries, 60 registered paired contrasts, Holm adjustment, within-cell ranks, profiles and seed stability |
| [`secondary-analysis.json`](secondary-analysis.json) | `ba2ed9a659942a9d732d11d155a22ca23dd415258efdb16ceb2a3d2327ef8f38` | Pooled and leave-one-algorithm-out IGD+, front dietary summaries, food retention and occasion mass change |

`sec_diet.analysis` checks the full validation and matrix checksum, requires exactly 20 planned replicates in each of 960 respondent/subset/algorithm cells, and computes the registered mean of 24 paired respondent-level median-hypervolume differences. It uses 99,999 paired sign-flip vectors with seed `2026100201` and 9,999 respondent bootstrap resamples with seed `2026100202`, both from NumPy PCG64. Holm adjustment covers all 60 tests. The Monte Carlo p-value includes a plus-one correction. The full-precision repository JSON is authoritative; rounded manuscript values are display values.

`sec_diet.secondary` builds the exact unique nondominated union of all 80 run fronts separately for every respondent and objective subset (240 groups) and calculates IGD+ for each of the 19,200 saved fronts. Its leave-one-algorithm-out reference uses the other 60 fronts. It also summarizes all four raw objectives, energy, fiber, sodium, and exploratory food/occasion descriptors. Food retention means a modeled quantity at least 10% of that observed for the same food/preparation/occasion; occasion mass change is relative to each observed occasion mass. These exploratory descriptors do not measure acceptance or usual diet. No alternate nutrient or environmental data source was run.

From a fresh clone with independently obtained source files, build the 24 local instances and execute and validate the full matrix as in [the execution guide](../experiment-pipeline.md). Then run:

```powershell
.venv\Scripts\python -m pip install -e ".[experiment,figures]"
.venv\Scripts\sec-analyze --matrix docs/protocol/run-matrix.csv --validation results/full-matrix-validation.json --output-root results/runs --report results/primary-analysis.json
.venv\Scripts\sec-analyze-secondary --matrix docs/protocol/run-matrix.csv --validation results/full-matrix-validation.json --output-root results/runs --instances-dir data/processed/instances --report results/secondary-analysis.json --workers 8
.venv\Scripts\sec-render-analysis --primary results/primary-analysis.json --secondary results/secondary-analysis.json --output-dir results/analysis-figures --matrix docs/protocol/run-matrix.csv --runs-root results/runs
```

The renderer produces three aggregate indicator figures and two detailed local 2D/3D Pareto-front figures for one registered respondent-day and replicate. Only the aggregate figures are committed under [`figures/`](figures/). The respondent-level fronts remain local. Colors in each aggregate heatmap are scaled separately within an objective subset, and raw hypervolumes are never compared across dimensions. The plots are generated from the aggregate repository JSON without hand selection of a favorable run.

## Exploratory front-attainment figures

The four additional front figures summarize all 24 respondent-days and 20 replicates for each algorithm in five selected objective subsets (9,600 saved run fronts). They use the complete original campaign, not a new optimization run. The selected subsets illustrate nutrient–carbon, carbon–water, nutrient–departure and two three-objective trade-offs. Their choice and all pointwise comparisons are exploratory; the 60 registered hypervolume tests remain the only confirmatory contrasts.

```powershell
.venv\Scripts\sec-analyze-fronts --matrix docs/protocol/run-matrix.csv --validation results/full-matrix-validation.json --runs-root results/runs --output-dir results/front-analysis-figures --report results/front-analysis.json
```

The output report is committed as [`front-analysis.json`](front-analysis.json), SHA-256 `126fbf82fa1ebb29b2c7f61a3927d0bdfe27fa5c91bb2ddbb65c7d7c12b40813`. It contains only pointwise medians and attainment fractions across 480 fronts per algorithm and subset; no respondent identifiers, food coefficients, or individual diets appear. The four PDFs under [`figures/`](figures/) are rendered from this aggregate report. At a first-objective threshold, a 2D curve gives the smallest second objective in each saved front and then the pointwise median across runs. A 3D surface gives the smallest departure subject to two simultaneous thresholds. Runs without an attainable point count above every finite value, so a median is displayed only where at least half of the 480 runs attain the threshold. Fixed display limits are N at most 0.25, C and W at most 0.35, and D at most 1; full original fronts remain local. The median curves and surfaces are not themselves feasible fronts.

Of 60 registered contrasts, 39 have Holm-adjusted p < 0.05. NSGA-II exceeds NSGA-III in all ten subsets; NSGA-II exceeds SPEA2 in two. Every run has a feasible point because the observed baseline is included in the common initial population. This does not indicate that both nutrient aspirations are met. The 24 deliberately balanced respondents do not represent Brazilian prevalence, and differences over optimizer seeds are not population uncertainty. Pooled IGD+ is descriptive and reference dependent. Peak traced Python allocation excludes native process memory.

The 19,200 runs contain 26,568,644 feasible evaluations out of 31,680,000 recorded evaluations. Across the 40 subset/algorithm cells, a standard 1.5-IQR rule flags 27 respondent-level median hypervolumes, at most one in any cell. All remain in the registered analysis; no instance or seed was selected or excluded after inspecting performance.
