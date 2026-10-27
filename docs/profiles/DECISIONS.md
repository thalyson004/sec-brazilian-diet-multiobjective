# Decisions for the profile experiment — 6 October 2026

## Reference anthropometry

Heights use national median estimates from POF 2008–2009, Table 1.1, total urban and rural populations: the 30–34 age band for the 30-year profiles and the 55–64 age band for the 60-year profiles. The [IBGE report](https://biblioteca.ibge.gov.br/visualizacao/livros/liv45419.pdf), PDF pages 79–80, gives these sex-specific estimates. The food records remain from POF 2017–2018 and ages are matched exactly. We do not present the earlier heights as measurements of the later respondents or as current population estimates.

Reference weight is calculated as `24 × height_m²`. BMI 24 kg/m² is a study choice within the adult and older-adult eutrophy intervals in the [SISVAN manual](https://bvsms.saude.gov.br/bvs/publicacoes/orientacoes_basicas_sisvan.pdf), PDF pages 23, 25 and 110. The source supports the intervals, not one uniquely optimal BMI. Using the same BMI avoids adding an unsupported age-specific weight-loss or weight-gain goal. These are maintenance scenarios for apparently healthy, nonsmoking, nonpregnant and nonlactating adults; they do not diagnose the survey respondents.

| Profile | Height (m) | Reference weight (kg) | BMI (kg/m²) | Maintenance energy (kcal/day) |
| --- | ---: | ---: | ---: | ---: |
| F30 | 1.600 | 61.44 | 24 | 2167.35 |
| F60 | 1.566 | 58.86 | 24 | 1903.25 |
| M30 | 1.716 | 70.67 | 24 | 2736.69 |
| M60 | 1.682 | 67.90 | 24 | 2342.14 |

Calculations retain the full stored weight, with six decimal places; the table rounds for display. Physical activity is the **low-active category**, explicitly assumed for all four reference scenarios. It is not estimated from POF. This common choice isolates the selected age/sex contrasts instead of adding an activity-level comparison. Maintenance energy uses the 2023 [Dietary Reference Intakes for Energy](https://doi.org/10.17226/26818), Table S-3, with age in years, height in centimetres and weight in kilograms:

- Women: `575.77 − 7.01 × age + 6.60 × height_cm + 12.14 × weight_kg`.
- Men: `581.47 − 10.83 × age + 8.30 × height_cm + 14.94 × weight_kg`.

The ±5% hard energy interval is a modeling tolerance around the reference maintenance estimate. It is not a confidence interval for that equation or evidence of individual energy balance.

## Nutrient goals and their meaning

The manuscript presents reference values and general characteristics in separate tables, including eligibility, physiological assumptions, dietary pattern, activity and maintenance goal. Every borrowed reference has a nearby source; numerical study choices are labeled as such. The requirements table includes the hard energy interval and distinguishes it from the 23 optimized nutrient criteria. The [literature comparison](../literature/README.md) explains how related models support the current question without equating their numerical outcomes.

The complete machine-readable table is [`targets.json`](targets.json). [`references.json`](references.json) links every numerical rule to its primary source. Health Canada's official 2025 tables supply sex/age recommendations, including the 2011 calcium/vitamin D and 2019 potassium updates. Supporting NASEM PDFs are in the global research library.

- Protein: at least 0.8 g/kg/day, intersected with 10–35% of the candidate's energy intake.
- Total fat: the intersection of the 20–35% DRI range with the WHO maximum of 30%, producing 20–30% of the candidate's energy.
- Fiber: the larger of the sex/age DRI adequate intake and WHO's 25 g/day adult minimum. The older-female criterion is therefore 25 g rather than the DRI value of 21 g alone.
- Saturated and trans fatty acids: WHO maxima of 10% and 1% of candidate energy. These fractions use 9 kcal/g.
- Sodium: WHO's 2000 mg/day maximum. This is not labeled as a tolerable upper intake level.
- Other modeled minerals and vitamins: RDA lower goals and total-intake upper limits when applicable. Adequate intake is identified as AI, and tolerable upper intake level as UL; neither is relabeled as an RDA.

The active v4.1 nutritional objective is the equally weighted mean of capped criterion-attainment percentages, maximized. A separate mean lower-target shortage penalty is added after normalization to included non-nutritional search coordinates, with weight 5 selected by the reduced matched study in PENALTY.md. Equal weights are a transparent modeling choice; they do not rank clinical severity. Nutritional success reports all 23 targets individually and simultaneous attainment. The relative attainment tolerance is `1e-6`; it is numerical, not clinical.

We do not impose supplemental-magnesium, synthetic-niacin, supplemental-vitamin-E or preformed-vitamin-A limits on total dietary fields. The available fields cannot identify those restricted chemical/source fractions. Folate is reported descriptively because its correspondence to dietary folate equivalents is unresolved. Carbohydrate uses 45--65% of candidate energy, calculated with 4 kcal/g from the reported POF total-carbohydrate field. This is an operational measure, not an independently measured digestible fraction; no digestible-carbohydrate RDA is imposed. Cholesterol and mono-/polyunsaturated fats remain descriptive where their specific recommended fractions cannot be identified. No unmeasured nutrient is inserted as zero. Reported composition zeros retain the source dictionary's uncertainty.

## Six-position observed-meal preparation

The decision unit is a complete observed meal, not a food quantity. `V9017` records breakfast (1), lunch (2), snack (3), dinner (4), supper (5), other (6) or unspecified (9). `V9015` records the nearest hour. Named breakfast/lunch/dinner/supper map directly. Snacks before noon enter morning snack, and later snacks enter afternoon snack. Other/unspecified occasions use 04--09 breakfast, 09--11 morning snack, 11--14 lunch, 14--17 afternoon snack, 17--21 dinner, and 21--04 supper. These half-open intervals implement the requested six-position scheme; the IBGE dictionary supports the input meaning, not these cutoff choices.

A snack/other occasion with missing or invalid hour excludes the whole day. Named occasions remain usable without a time. All consumption lines in one respondent/day/position are combined with their original grams and absolute reported nutrient amounts. Multiple recorded events in a position are thus a daily-slot intake; they are not asserted to be one simultaneous event. Missing positions have empty item lists and zero totals. An empty option is admissible only when that absence occurred in that profile/position.

Eligibility requires positive finite grams, finite nonnegative values in the 29 composition fields, positive energy, at least one non-water food and complete positive carbon/water linkage for non-water items. A failed line excludes its complete day. One eligible day per respondent is retained using a fixed hash ordering. Six separate pools per profile store complete alternatives; repeated meals are deduplicated only when their foods, quantities and reported nutrient amounts match. Opaque source-day identifiers retain provenance locally.

Meal nutrient totals are direct sums of source absolute amounts. No composition regression, scaling or independently optimized food amounts is used. Meal footprints sum recorded grams times the matched environmental coefficients. Tap water remains inside its recorded meal with its nutrient amounts; zero environmental coefficients are a source convention and do not establish a measured footprint. It is excluded from food-mass departure and food-group denominators.

## Whole-meal formulation and operators

A candidate contains six integer indices, one per position-specific pool. This is equivalent to binary meal selections with exactly one selection per position. Each selected meal contributes fixed nutrient, footprint and food-mass vectors. The hard daily energy interval is the reference requirement plus/minus 5%. The 23 criteria define capped percentage attainment. Lower coverage is min(intake/minimum, 1); upper compliance is min(maximum/intake, 1) where applicable. Each criterion uses their minimum, and A averages the 23 percentages. Above-minimum intake receives 100% until a separate documented upper bound is violated. Mean lower-target shortfall P covers the 20 lower-goal criteria. Search coordinates are nutritional loss 1-A/100 and fixed-normalized C, W and D plus weight times P. Physical outcomes and search coordinates are saved separately; numerical feasibility remains the hard energy interval.

C and W sum meal carbon and water. D measures relative absolute change from the profile mean food/preparation/position mass vector, excluding tap water. Food quantities are derived outcomes of selected meals and do not become independent decision variables. The scenarios NC, NW, ND, NCW, NCD and NWD always include N.

Population 66 starts from distinct observed six-position days matched across algorithms. Uniform crossover (probability 0.9) exchanges complete positions. Categorical mutation independently replaces each position with a pool alternative with probability 1/6, preserving every recorded portion. NSGA-II, SPEA2, NSGA-III and SMS-EMOA retain their distinct survival mechanisms. Four profiles, six scenarios, four algorithms and twenty replicates define 1920 runs of 16500 evaluations, or 31.68 million evaluations. The one-hour limit retains interrupted runs as incomplete.

## Analysis and interpretation

Normalization bounds are fixed from pool extrema and the energy interval. Hypervolume uses reference 1.1; IGD+ uses the pooled nondominated candidates within a profile/scenario as an empirical reference. Ten checkpoints describe search progress. The 144 within-profile and 36 equal-profile global contrasts form one Holm-adjusted family; matched seed replicates are the statistical units. This is optimizer variation over fixed scenarios, not population inference.

Dietary selections are maximum capped nutrient attainment, nearest unpenalized normalized origin and minimum departure. Reports retain six whole-meal alternatives, their immutable items and quantities, source-day identifiers and empty positions. Nutrient gaps, all-target attainment and food-group changes accompany actual 2D/3D fronts and projections. Missing fronts have no invented menu. Global indicators give each profile equal weight.

The linear feasibility diagnostic allows fractional meal mixtures only as a relaxation. If it is infeasible, no whole-meal menu can attain all targets under these inputs. If feasible, it does not establish an admissible integer menu. Fractional mixtures are not diet solutions.

The active design is `sec2026-pof-meals-v4.1-penalty-5`. The corrected 864-run [weight comparison](PENALTY.md) selected 5 before a separate 1,920-run main campaign. The rule admits weights within 0.5 percentage point of best mean attainment and 0.5 criterion of best mean attained count, then chooses the smallest mean included non-nutritional outcome. Weight 5 has 95.9237% attainment and 18.4306 attained criteria, with mean other outcome 0.0569419; weight 50 has 96.3736%, 18.7986 and 0.0892687. Thus choosing 5 preserves 36.2% better mean other outcome than 50 within the registered nutritional plateau. These tolerances and penalty are computational settings, not clinical recommendations.

The completed main campaign has 31.68 million evaluations and 15,022 reporting-front entries. [Validation](../validations/2026-10-06-capped-attainment.md) records reconstruction and integrity. Historical v3's 263,195 entries and all earlier designs are preserved separately and do not support the revised objective.

## Complete-front diets and food mass interpretation

The saved `front.npz` file for each run contains all nondominated six-position indices and objective vectors. The corresponding prepared profile JSON stores the full observed meal pools, with food codes, preparations and original gram portions. `scripts/export_pareto_diets.py` joins these artifacts and writes every front menu into a local compressed JSONL file. The separate manifest pins the original execution and analysis hashes and the postprocessing script hash. This avoids changing the provenance of the completed optimizer campaign.

For illustrative manuscript tables, NSGA-II is a fixed display algorithm, so the example algorithm is not selected by a favorable final ranking. Within each profile and objective set, the displayed run is nearest the NSGA-II median hypervolume; its menu is the front member nearest the normalized origin in that set's coordinates. Every meal and food portion is shown. These 24 examples are illustrations rather than representative means or recommendations.

For food-type analysis, sum grams over all six positions by POF food code; combine preparations of the same code but retain distinct codes and keep tap water as a separate type. For each profile, objective set and algorithm, use one nearest-origin compromise menu from each of 20 independent runs, then calculate arithmetic mean and sample standard deviation (`ddof=1`). A code absent in a run contributes zero; all codes in the retained profile meal pools receive a row, including a zero row when absent from every selected menu in the cell. This avoids treating correlated points in one front as independent repetitions. Tap water is included in descriptive total grams, but remains outside the departure objective and has the environmental coefficient specified by the source workbook. These composition differences are descriptive and have no food-wise significance tests.


## English publication displays and postprocessing

The reviewed 701-code English dictionary preserves POF identifiers and regional names with English descriptors. Group names are translated as well. Food grams and baseline changes use mean and sample SD over 20 independent compromise menus, including zeros; the fixed baseline makes change SD equal mass SD. Display ranking is post hoc and descriptive: largest absolute NC change, averaging algorithm means equally. Plain water is excluded only from this display ranking. The leading code per profile and the top three F30 codes motivate the main table and figure; all food codes remain in the full summary.

Two-dimensional lines connect evaluated points only. Three-dimensional triangles require at least three distinct projected points of rank two. Long edges are masked using the greater of 0.90 projected unit-range length and twice median nearest-neighbor spacing. Faces use opacity 0.32; neither faces nor lines establish feasible intermediate meals. Twenty-four example menus use the fixed NSGA-II median-hypervolume/compromise rule and show exact physical outcomes in appendix tables. Nutrient heatmaps summarize the fraction of independent compromise menus attaining each criterion, rather than every front member.


## Energy context in attainment comparisons

F30, F60, M30 and M60 all assume low-active activity; the maintenance energies and ±5% intervals are unchanged. The combined observed/optimized table reports individual profile rows and equal-profile GLOBAL rows, with no common GLOBAL ceiling. Observed cohorts and optimization meal pools remain specific to sex and exact age. A day is never selected for another profile merely because its energy fits that interval. The extractor rejects source-day overlap between profiles and retains the original source-instance checks.

A larger energy allowance may provide room for nutrient-bearing meal combinations. It does not guarantee a higher score: both energy bounds, nutrient upper limits, nutrient requirements and the available meal choices matter. The compared feasible sets are not nested. The current experiment changes these conditions jointly across profiles and does not estimate an isolated or causal energy effect. M30 has the largest ceiling and highest compromise attainment; M60 has a higher ceiling than F60 but lower attainment. This contextual interpretation belongs in Results, Discussion and Conclusion.
