# Rebuilding and running the SEC comparison

> This document describes the earlier respondent-day benchmark. The current article uses the [whole-meal profile study](profiles/README.md).

The frozen design is [`protocol/design.json`](protocol/design.json); its complete schedule is [`protocol/run-matrix.csv`](protocol/run-matrix.csv). The matrix has 19,200 planned runs. These commands do not imply that any run has been completed. Every source archive, derived instance and run output must stay in a local ignored directory. No TBCA nutrient table or POF-derived coefficient file belongs in a public commit.

## Install and verify the inputs

From a fresh clone, use Python 3.11 or newer. The released dependency snapshot was captured on Windows with Python 3.14.4; exact optimizer versions are checked at execution.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[experiment]"
.venv\Scripts\python -m unittest discover -s tests -v
```

Obtain `Dados_20230713.zip` from the [IBGE POF microdata directory](https://ftp.ibge.gov.br/Orcamentos_Familiares/Pesquisa_de_Orcamentos_Familiares_2017_2018/Microdados/) and the November 2023 environmental workbook from the [OSF record](https://osf.io/g9d5y/). Keep them in `data/raw/` under the filenames used below or change the paths. The builder checks both SHA-256 hashes against the frozen design and cohort validation. It stops on any mismatch, duplicate environmental key, unsupported food link, malformed record, or unexpected instance size.

```powershell
.venv\Scripts\sec-build-instances --pof data/raw/Dados_20230713.zip --footprints data/raw/pegadas_alimentos.xlsx --design docs/protocol/design.json --cohort docs/validations/pof2018-cohort-validation.json --output-dir data/processed/instances
```

This command reads all POF consumption lines to derive local per-gram energy, fiber and sodium coefficients, then writes the 24 selected instances and `instances-manifest.json`. The directory must be empty before it runs. These JSON files include food-level coefficients and must remain local. Their manifest records the source, design, cohort and instance hashes. The frozen cohort-validation JSON is kept with its original CRLF bytes through `.gitattributes` because its byte hash is part of the run matrix; do not reformat that file. The tracked source and cohort validations contain aggregate counts only.

## Execute one registered run

Choose an existing `run_id` from `docs/protocol/run-matrix.csv`, for example with a CSV reader. The command below requires an explicit ID; it never selects a row silently. It refuses to overwrite an existing output directory. The working tree must be committed so that the recorded Git revision identifies the actual code. A wheel installation outside Git requires an exact 40-character `SEC_CODE_REVISION` environment variable.

```powershell
.venv\Scripts\sec-run --design docs/protocol/design.json --matrix docs/protocol/run-matrix.csv --matrix-manifest docs/protocol/run-matrix-manifest.json --instances-dir data/processed/instances --output-root results/runs --run-id REPLACE_WITH_REGISTERED_RUN_ID
.venv\Scripts\sec-check-results --design docs/protocol/design.json --matrix docs/protocol/run-matrix.csv --matrix-manifest docs/protocol/run-matrix-manifest.json --instances-dir data/processed/instances --output-root results/runs --report results/one-run-validation.json --run-id REPLACE_WITH_REGISTERED_RUN_ID
```

The runner verifies versions and all manifest hashes before evaluation. The same seed generates the same initial population for all four algorithms in a matched instance and objective subset. Every candidate evaluation is written immediately. A time limit or exception leaves a partial output with `complete=false`; the checker returns a nonzero status for it. A run is complete only at exactly 1,650 recorded evaluations with the evaluation limit stop reason.

## Execute and validate the entire registered matrix

The command below explicitly schedules every row with up to eight independent worker processes. Its 19,200 runs require substantial time and disk space. `--workers 1` runs sequentially. No two workers receive the same run ID. The scheduler appends one durable event per finished run to `batch-progress.jsonl` under the output root. The checker reports missing directories and files, incomplete runs, invalid saved values and the final completion flag.

```powershell
.venv\Scripts\sec-run --design docs/protocol/design.json --matrix docs/protocol/run-matrix.csv --matrix-manifest docs/protocol/run-matrix-manifest.json --instances-dir data/processed/instances --output-root results/runs --all --workers 8
.venv\Scripts\sec-check-results --design docs/protocol/design.json --matrix docs/protocol/run-matrix.csv --matrix-manifest docs/protocol/run-matrix-manifest.json --instances-dir data/processed/instances --output-root results/runs --report results/full-matrix-validation.json --workers 8 --expected-code-revision b775cb2798507e3ec2e298fca4914fbe90ae23f2
```

The checker exits successfully only if every requested run is complete. The optional revision requirement above pins the corrected campaign; change it only when validationing a different, explicitly documented campaign. Existing outputs are never overwritten or silently reused. To resume after interruption, run each still-missing registered ID explicitly and preserve all prior logs; an incomplete directory requires investigation before a rerun. The validation report lists each planned ID and its state. Pooled IGD+ is computed by the separate [analysis workflow](analysis/README.md), never filled with a substitute value in the per-run pipeline.

## Files per run

| File | Contents |
| --- | --- |
| `config.json` | Full matrix row, design, source and instance checksums, environment and Git revision |
| `evaluated-solutions.jsonl` | Every evaluated diet in order, quantities, modeled nutrients, all raw and normalized objectives, violations and feasibility |
| `final-population.jsonl` | Complete final algorithm population with independent model scores |
| `front.jsonl` | Unique feasible nondominated diets from all evaluated candidates |
| `metrics.json` | Completion, stop reason, evaluation and feasible counts, front size, external hypervolume; IGD+ explicitly deferred to the pooled analysis |
| `resources.json` | Wall and CPU time and peak Python-traced allocations; native process memory is not captured |
| `run.log` | Stop reason, count and traceback if an error occurred |

The checker independently recalculates every saved diet, rebuilds the feasible nondominated front, recomputes hypervolume, and checks the completion flag. Python-traced memory excludes native allocations and should not be interpreted as total peak resident memory. Run outputs are local by default because they include POF-derived coefficients and dietary quantities. Any public aggregate release requires a separate source-term review.
