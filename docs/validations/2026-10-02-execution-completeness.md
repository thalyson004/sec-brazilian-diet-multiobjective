# Confirmatory execution completeness, 2 October 2026

The corrected campaign uses runner commit `b775cb2798507e3ec2e298fca4914fbe90ae23f2` with the frozen `sec2026-pof-person-day-v1` design and matrix. Independent validation code was committed as `26bce06`. All detailed outputs remain in ignored local `results/runs/`; they contain POF-derived dietary quantities and are not part of this public report.

| Check | Result |
| --- | ---: |
| Planned matrix rows and unique run IDs | 19,200 / 19,200 |
| Batch events and unique completed IDs | 19,200 / 19,200 |
| Output directories | 19,200 |
| Completed runs after independent artifact rescoring | 19,200 |
| Incomplete, missing-directory, missing-file or invalid runs | 0 |
| Actual recorded objective evaluations | 31,680,000 |

The verificador read every `config.json`, every candidate in `evaluated-solutions.jsonl`, every final-population diet, every front, metric, resource record and run log. It recalculated modeled nutrients, all four raw and normalized objectives, feasibility, each feasible nondominated front and external hypervolume. It required the corrected runner commit in every configuration and verified the frozen design, matrix and local instance hashes. The `complete_matrix` flag was true and the validation command exited successfully. Recorded per-run wall time ranged from 0.81 to 15.27 seconds, with median 1.56 seconds. The recorded peak Python-traced allocation is not total process memory.

Local evidence hashes:

* `results/runs/batch-progress.jsonl`: SHA-256 `98819a7b1e48b881fe855b652f7de0e81fb5e859cf03d2f730bb9ee9d07d3dfb`.
* `results/full-matrix-validation.json`: SHA-256 `5df4ab8d1fecd29fcc68e3b5a79038912fcea7f655baa522d10e525532a96c7f`.

The first campaign was aborted because `pymoo` reused state inside SPEA2's default survival object. Its 631 events and eight in-flight directories are preserved locally under `results/aborted-2026-10-02-shared-spea2-survival/` and are excluded from this count. The [decision record](../decisions/2026-10-02-aborted-campaign-and-restart.md) explains the error and full restart. The corrected campaign needed no seed replacement or rerun. This document establishes execution and file integrity; statistical contrasts, IGD+ pooling, dietary interpretation and figures are reported separately in the [analysis record](../analysis/README.md).
