# Capped nutrient attainment and effective shortage penalties

The v4 formulation replaces the v3 mean unbounded relative-deviation score. For a lower goal L, coverage is min(q/L, 1). A quantity above the requirement receives 100% coverage. For an upper-only limit U, compliance is min(U/q, 1), with zero intake assigned full upper-limit compliance. When a criterion has both bounds, take the smaller of lower coverage and upper compliance. Thus intake above an RDA is not penalized until a documented UL or recommended upper bound is crossed. The mean of the 23 percentages is the reported nutritional objective A, maximized. The algorithms minimize 1-A/100.

The shortage term P is the mean of max(0, 1-q/L) over criteria with a lower goal. Carbon, water and departure have fixed pool-derived normalization bounds. With penalty enabled, their search coordinates are normalized outcome + lambda*P. The nutritional search coordinate remains 1-A/100. Normalization precedes the addition; multiplying and then normalizing a nutritional objective by the same weight would have no effect on Pareto dominance. Physical outcome values and unpenalized normalized values are saved separately from penalized search coordinates.

The optimizer's archive is stored in search-front.npz. The reported front keeps the points in that archive that are also nondominated in unpenalized physical objective coordinates, preserving the direction A=maximize and C/W/D=minimize. Indicators use those fixed, unpenalized coordinates and a common reference. Every evaluated menu, both front versions and their six meal indices are retained locally. No interpolation produces a new diet.

## Reduced study registered before selection

The study_penalty_weights.py script runs weights 0, 1, 5, 10, 25 and 50 for all four profiles and all four algorithms in NC, NW and NCD. These three scenarios cover carbon, water and quantity departure and both two- and three-objective search. Each setting has three matched repeats and 3,300 evaluations, giving 864 runs and 2,851,200 evaluations. Weights share initial populations and seeds. The main study uses a separate seed namespace.

For each run, use the nearest unpenalized normalized-origin point in the reporting front. Calculate capped nutrient attainment, fully attained criterion count, all-criterion attainment and included non-nutritional normalized outcomes. A weight is eligible if its mean attainment is within 0.5 percentage point of the best weight and its mean attained count is within 0.5 criterion of the best. These are explicit exploratory plateau tolerances: smaller than one complete nutrient criterion, without pretending to be a clinical threshold. Among eligible weights choose the smallest mean included non-nutritional normalized outcome, then the smaller weight for an exact tie. This rule is fixed before inspecting outcomes.

The saved selection JSON records all weight summaries, the original reduced-study design, source checksums and code revision. It is committed before the full penalized campaign. The resulting value is a setting supported by this reduced study, not a universally optimal penalty. Profile-specific performance and limitations must be reported.

## First calibration (v4.0, preserved)

All 864 runs completed with 3,300 evaluations and nonempty reporting fronts. Initial-population file hashes and seeds match across all six weights in each of the 144 cells. The selection rule chose weight 5 from eligible weights 5, 10, 25 and 50. Mean attainment was 94.2356% at weight 0 and 95.9237% at weight 5; mean fully attained criteria increased from 17.4722 to 18.4306 of 23. The mean included non-nutritional normalized outcome increased from 0.0340102 to 0.0569419. Weight 50 reached 96.3860% and 18.8056 criteria, but its non-nutritional outcome was 0.0891906. These are descriptive reduced-study means. Only one of the 144 weight-5 compromise menus attained all 23 criteria. Remaining shortages must be reported in the full campaign.

The code revision for the calibration is ac076de. The saved outcomes checksum is 00935a28e2bb752ab4cb8c475b100024c8d6bb3c97112488f1292880fd4b2d1c. The main campaign retains a distinct seed namespace and uses the same prepared food/meal universe.

## Completed v4.1 calibration

The corrected study completed all 864 runs with no failures and no warnings. The same rule selected weight 5; eligible weights remain 5, 10, 25 and 50. The weight-0 and weight-5 summaries are unchanged from the preserved first calibration. At weight 50, corrected mean attainment is 96.3736%, mean attained count 18.7986 and mean included non-nutritional outcome 0.0892687. The corrected code revision is 21be27a and the outcomes checksum is e9d2dda8f8b6858994e27eea976c47f5f269b3f8dfffef769c30d458f7b9271e. The active selection JSON contains this corrected evidence. All 144 cells retain identical seeds and initialization across six weights.

## Commands and preserved campaigns

The v4.1 revision handles zero-span coordinates in SPEA2's internal density normalization with a unit divisor and requires finite strength/density fitness. Positive-span coordinates retain the library calculation. The first main attempt was interrupted after 276 accepted complete runs and is excluded from the paper; all its files and the first calibration remain in their original v4 directories. Repeat the same reduced protocol in results/penalty-weight-study-v4.1, then the full matrix in results/meal-profile-study-v4.1-penalty-<weight>. The selection rule and independent seed namespaces are unchanged. The calibrated main entry point rejects a selection record lacking the normalization correction.

The revised food-code summary covers every food in each profile's meal pools, including foods absent from all algorithms' compromise menus. It reports mean grams, sample standard deviation, observed mean baseline, mean gram change and relative change (when the baseline is positive). With a fixed baseline, change standard deviation equals the mass standard deviation. Tap-water baseline grams are reconstructed from observed days separately because the departure baseline excludes tap water. Menu tables use a page-breaking appendix layout.

    .venv\Scripts\python scripts/study_penalty_weights.py --prepared-inputs results/meal-profile-study/inputs/a143d9fd53d6 --workers 8
    .\run-study.ps1 -Pof C:\data\Dados_20230713.zip -Footprints C:\data\pegadas_alimentos.xlsx -Penalty -Workers 8
    .\run-study.ps1 -Pof C:\data\Dados_20230713.zip -Footprints C:\data\pegadas_alimentos.xlsx -NoPenalty -Workers 8

An explicit -PenaltyWeight 10 or --penalty-weight 10 requires the penalty flag. Default v4 output folders identify the mode and weight; the v3 results/meal-profile-study directory is preserved. An existing output directory registered to another design is refused. The no-penalty v4 control uses the same capped nutritional objective and is distinct from the historical v3 objective.
