# Reference-constrained compromises from complete evaluated histories

This retrospective decision analysis uses the completed v4.1 penalty-5 campaign. It repeats no optimization and preserves the original final reporting fronts and their indicator/food analyses. It selects one reference-constrained compromise from each of the 1,920 original runs, using **all energy-feasible evaluated menus**, including initialization. This candidate pool is larger than the original final shortage-prioritized reporting front. Only 14 of the new selections occur in those original final fronts.

## Selection rule and reference

For each profile, first require higher capped nutrient attainment, lower carbon, lower water and lower departure than the matching energy-restricted observed group means. A relative gain must exceed 1e-12 for each coordinate, a floating-point tolerance. The observed days and energy bands are unchanged. D is compared with the observed mean individual-day distance to the original aggregate profile vector, not with the zero distance of that aggregate itself. These references are in [the sensitivity release](../compromise-selection-v1/observed-departure-reference.json).

Among eligible candidates, minimize Euclidean distance to zero in all four original unpenalized normalized coordinates: N is `1-A/100`, and C/W/D use the original fixed profile-pool bounds. Smaller original candidate identifier resolves exact ties. This retains the original normalization while introducing explicit reference-improvement requirements and protecting every measured coordinate. The script checks that the selected point is not dominated in four coordinates by any energy-feasible evaluated candidate in that run. It can lie outside a run's original two-/three-objective final reporting front.

If a run has no eligible menu, the selector returns no choice and the release command stops rather than fabricating a complete comparison. In this campaign every run provides a valid choice. Higher summary attainment than the observed mean does not establish complete nutritional adequacy. The new choices average 95.67% attainment, versus 97.98% for the original ideal-distance choices and 75.78% observed. None of the new reference choices meets all 23 criteria. The gain in jointly protected outcomes therefore accompanies a nutritional trade-off relative to the original choice, which must be reported.

| Profile | Selected runs | Attainment (%) | Carbon (kg CO2e/day) | Water (L/day) | Departure (%) |
| --- | ---: | ---: | ---: | ---: | ---: |
| F30 | 480 | 94.41 | 2.769 | 2774.4 | 180.62 |
| F60 | 480 | 95.24 | 1.866 | 2148.2 | 190.65 |
| M30 | 480 | 97.80 | 2.860 | 2633.3 | 171.83 |
| M60 | 480 | 95.22 | 3.157 | 2178.4 | 181.33 |
| GLOBAL | 1920 | 95.67 | 2.663 | 2433.6 | 181.11 |

All four outcomes improve over their profile's observed means in **each individual selected menu**, not only in the profile averages. This is a comparison against reference means, not a paired intervention or a population effect. GLOBAL gives the four equally sized profiles equal weight. D is a relative mass distance and can exceed 100%; it is not a validated acceptability probability.

## Files and relation to the manuscript

- `run-selections.csv`: all 1,920 choices, metadata, candidate identifiers, energy, physical outcomes, attained-criterion counts, shortage values, eligible-pool size, membership in the original final front and SHA-256 of the original evaluation file.
- `complete-menus.jsonl.gz`: the same choices with their six original meal indices, full English food/portion lists and fixed normalized coordinates. Join by `run_id` and `candidate_index`.
- `nutrient-outcomes.csv`: all 23 nutrient outcomes per selected menu, with amounts, lower/upper targets, deficits, excesses and attainment.
- `food-type-mass-summary.csv`: food-code daily grams, means and sample SD over 20 reference choices per profile/scenario/algorithm, including zeros for absence. `baseline_g` uses the original full retained profile cohort, as in the original food analysis, rather than the smaller energy-matched comparison subset.
- `summary.json`: means, SD, sample counts and complete-attainment counts by profile and globally.
- `original-selection-summary.json`: original Max N, ideal-distance and Min D summaries, retained for the combined nutritional table.
- `observed-comparison.tex`, `nutrition-selections.tex`: current manuscript Tables 9 and 10. Ideal denotes the original front-based compromise; Ref. denotes the new complete-history reference-constrained choice. The original and new numbers must not be attributed to the same decision rule.
- `manifest.json`: source/reference, script, selector and output hashes. Original evaluation-file hashes are recorded separately for each run.

The original [1,920 final reporting fronts](../../fronts/README.md) remain published without alteration. The [front-restricted sensitivity](../compromise-selection-v1/README.md) explains why choosing only from those final fronts could not achieve joint improvement in all four outcomes for every profile. The archive distinction, rather than new optimizer execution, makes the additional choice possible.

## Reproduce

With the completed original numerical campaign and its original input pools/reconstruction locally available, run from the standalone repository:

```powershell
.venv/Scripts/python scripts/select_reference_compromises.py --campaign results/meal-profile-study-v4.1-penalty-5 --comparison comparisons/observed-profile-energy-context --sensitivity comparisons/compromise-selection-v1 --output results/reference-compromise-reproduction
```

Use a new output directory. The script rescores every selected genotype with the original model and checks its outcomes, energy feasibility and saved nutrient count before publishing it. Copy the two generated table files to a manuscript checkout when updating Tables 9 and 10. [RUNNING.md](../../docs/profiles/RUNNING.md) describes reconstructing and executing the original study. The published choice/food/nutrient files can be inspected without the private source pools; independently obtained source data are needed to reconstruct the complete histories and rescore nutrients. Food-level source nutrient coefficients and full evaluation histories are not included in this release.
