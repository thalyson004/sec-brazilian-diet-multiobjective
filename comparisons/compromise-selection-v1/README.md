# Reference-based compromise selection: retrospective feasibility analysis

The original `compromise` rule minimizes Euclidean distance to zero in the unpenalized normalized coordinates included in each run. It has no observed-baseline improvement constraints. Water is omitted from that distance in NC, ND and NCD. Including all four coordinates also does not ensure improvement relative to observed diets.

## Coverage and a bound on possible selection changes

| Profile | Observed W | Original W | Lowest possible mean W | Change from observed | Joint NCW fronts | Joint NCWD fronts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| F30 | 5262.0 | 6379.4 | 5487.5 | +4.29% | 216/480 | 23/480 |
| F60 | 5704.9 | 5921.0 | 5612.9 | -1.61% | 287/480 | 188/480 |
| M30 | 6143.8 | 4560.9 | 3168.7 | -48.42% | 451/480 | 277/480 |
| M60 | 6622.6 | 7744.9 | 6675.0 | +0.79% | 248/480 | 147/480 |

Water is in L/day. The lower bound takes the minimum-water point from each of the original 480 fronts, then averages with the same equal run weights. Every one-point-per-run selection has mean water at least this bound. F30 and M60 exceed their observed means even at this bound. This proves a limitation of post-selection on these saved fronts, not infeasibility of improved diets in the complete meal-combination space. Conditional successes must not replace all 480 runs while retaining that denominator.

## Implemented alternative

The front-restricted sensitivity function `select_reference_compromise` in `src/sec_diet/compromise_selection.py` first requires strict improvement relative to the matching observed profile means: higher capped nutrient attainment, lower carbon and lower water. `protect_departure=True` also requires lower D. A relative gain must exceed 1e-12, solely a floating-point comparison tolerance. This maximin sensitivity is separate from the final history-based, reference-constrained ideal-distance selection.

For eligible menus, the nutritional gain is `(A - observed_A)/(100 - observed_A)`. Carbon, water and optional departure gains are `(observed_value - value)/observed_value`. The rule maximizes the smallest gain, then the sum of gains, then prefers the smaller original candidate identifier. This is an explicit retrospective decision rule with equal priority to its dimensionless improvement coordinates, not a clinically validated preference model. It has no penalty-weight change and starts no optimization. If there is no eligible point it returns `None`, without a worsening fallback or another run's menu.

The observed reference uses the same sex, exact age and energy-matched days as the original comparison. Higher attainment means improvement of the capped summary score; it does not establish that all 23 criteria are met. For D, the reference is the mean of those individuals' departures from the original profile food/preparation/position mean vector. It is not the zero departure of that aggregate vector. `observed-departure-reference.json` provides every observed D outcome and the execution/input hashes. It was derived from the executed local pools with the unchanged original D function; nutrient/footprint scores were matched against the published observed outcomes before accepting a day.

## Files and interpretation

- `run-selections.csv`: every original run for every assessed rule. Missing joint-improvement choices remain explicit (`available=False`, empty candidate/outcome fields).
- `coverage-by-cell.csv`: availability and joint-improvement counts separately for every profile, objective set and algorithm; each cell retains its 20 planned runs.
- `summary.json`: observed references, all-run and conditional summaries, and per-profile/global coverage. Global means give profiles equal weight. Conditional means use only eligible runs and have a different algorithm/scenario mixture from the full campaign; they are not replacement estimates for Tables 9 and 10.
- `selected-menus.jsonl.gz`: all available NCW and NCWD reference-rule selections, with complete published food/portion lists and an explicit `selection_method`. The same menu can occur under both rules or in different runs.
- `compromise-feasibility.tex`: generated manuscript table reporting the lower bound and joint-improvement availability.
- `manifest.json`: source-release, observed-data, script, selector and output hashes.

`original_distance` recovers the saved selections; `all_four_distance` assesses including N/C/W/D in the distance. `minimum_water_bound` and `minimum_departure_bound` provide coordinate-wise bounds rather than joint-compromise recommendations. The two front-restricted reference rules have conditional coverage of 1,202/1,920 (NCW) and 635/1,920 (NCWD). The original optimization, fronts, calibration, original dietary selections and indicators remain unchanged. These conditional summaries must not be described as the Ref. rows of the main tables: [the final reference compromise](../reference-compromise-v1/README.md) uses all energy-feasible evaluated candidates, including alternatives omitted from the original final fronts.

## Reproduce using only published data

From the standalone repository:

```powershell
.venv/Scripts/python scripts/analyze_compromise_selection.py --fronts fronts/meal-profile-study-v4.1-penalty-5 --comparison comparisons/observed-profile-energy-context --departure-reference comparisons/compromise-selection-v1/observed-departure-reference.json --output results/compromise-selection-reproduction
```

To derive the observed D reference again from the completed original local campaign, replace `--departure-reference ...` with `--campaign results/meal-profile-study-v4.1-penalty-5`. The output directory must be new. [RUNNING.md](../../docs/profiles/RUNNING.md) describes complete source reconstruction and execution. The lower bounds concern only the original reporting fronts. The complete evaluated histories contain further alternatives, allowing the separate reference-constrained ideal-distance rule to provide a joint improvement in all 1,920 runs without repeating optimization. Improving all measured criteria is a different decision requirement from optimizing pairs/triples; reporting archives and complete evaluated candidate pools must be distinguished explicitly.
