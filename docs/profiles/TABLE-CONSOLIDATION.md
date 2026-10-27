# Consolidation of the observed comparison and nutritional selections

## Unit and weights

The campaign contains four profiles, six objective sets (NC, NW, ND, NCW, NCD and NWD), four algorithms (NSGA-II, SPEA2, NSGA-III and SMS-EMOA), and 20 matched replications. Each run has its own saved reporting front.

All [1,920 reporting fronts and 15,022 complete menus](../../fronts/meal-profile-study-v4.1-penalty-5/README.md) are available in the repository. `runs.csv` identifies the 480 fronts per profile, and `selections.csv` identifies the three selected members per run used below. These public indices allow each summarized selection to be located in its original front.

For each selection rule, one menu is selected per run. Each profile therefore contributes 6 × 4 × 20 = 480 selected-menu records per rule. The global total is 1,920 per rule. Each of the 24 algorithm–scenario cells contributes 20 records, so all cells receive equal weight. The 15,022 complete-front entries are a different count. Front size does not increase a run's contribution to these tables.

Separate runs can select identical menus, and different rules can select the same menu from a front. These records retain their run identities and weights. The three original rules are summarized separately, producing 5,760 records in `article/diet-selections.csv`, rather than one pooled sample of 5,760 distinct diets.

## Selection rules

- **Max N:** highest capped nutrient attainment. Ties prefer lower normalized carbon, then water, then departure. This is the lexicographic order of the unpenalized normalized N/C/W/D coordinates.
- **Comp.:** smallest Euclidean distance to zero in the run's included unpenalized normalized objective coordinates. The nutritional coordinate is `1 - attainment_percent / 100`; the others use fixed profile-pool bounds. The shortage penalty is not part of this reporting distance.
- **Min D:** smallest physical departure on the same reporting front, even when D was not a search objective. It does not represent a new departure-only optimization.

For tied compromise distances or departures, NumPy selects the first candidate in saved front order. The selection implementation is in `src/sec_diet/profile_results.py`; `selected_outcomes` in `src/sec_diet/publication_outputs.py` recovers the saved choices and outcomes.

Comp. is an ideal-distance choice without an observed-reference improvement constraint. In NC, ND and NCD its distance omits water. Even a distance using all four coordinates does not guarantee improvement over observed means. The [retrospective reference-based analysis](../../comparisons/compromise-selection-v1/README.md) implements a separate strict-improvement selector and reports availability. It retains missing choices explicitly. Its conditional summaries are not replacements for the original 480-run rows, and do not imply algorithm/scenario balance among the eligible fronts.

## Original observed-versus-optimized release

The optimized row for each profile uses only Comp.: the same 480 selected records summarized by that rule in the nutritional selection table. Energy and footprint outcomes are also reported. The 27 F30, 38 F60, 24 M30 and 19 M60 observed days form separate sex/exact-age/energy-matched comparison sets. Their own sample means are used. GLOBAL averages the four profile means equally on both sides, giving each observed profile weight 1/4 despite different numbers of respondents. All 23 is expressed as a percentage of records attaining all criteria.

`scripts/extract_observed_comparison.py` generates this table. The release in `comparisons/observed-profile-energy-context/` includes all compared menus, numerical outcomes and summaries. Each optimized row in `optimized-outcomes.csv` identifies its algorithm, objective set and replication.

## Original three-rule nutritional table

Each profile/rule row averages its own 480 selections. GLOBAL gives equal profile weights, equivalent to the arithmetic mean of 1,920 records because all four optimized groups have equal size. All 23 gives a count and denominator: for example, the global Comp. result 32/1,920 corresponds to 1.67% in the observed comparison. The three rule rows refer to alternative selections from the same run fronts and are not independent groups of experiments.

`scripts/export_publication.py` generates this table from the saved campaign. These descriptive averages summarize the stated mixture of search settings. Algorithm and objective-set differences require their separate displays; a consolidated row does not identify a best algorithm or objective set.

## Current reference-constrained compromise

The current manuscript additionally reports Ref., the [reference-constrained choice](../../comparisons/reference-compromise-v1/README.md) from **all energy-feasible evaluated candidates** in each run, including initialization. It first requires better capped nutrient attainment and lower C/W/D than the matching observed profile means, then minimizes Euclidean distance in all four original fixed normalized coordinates. There are 480 choices per profile and 1,920 globally. Its larger pool differs from the original final fronts; 1,906 choices lie outside those original fronts. The original optimization and indicator calculations are preserved.

Table 9 now has Observed, Ideal and Ref. rows per profile and globally, and includes departure so all four outcomes can be inspected. Table 10 places the three original rules (Max N, Ideal and Min D) plus Ref. in four paired column groups, with one row per profile and GLOBAL. Each profile/rule still summarizes 480 records, or 1,920 globally; the displayed outcomes are mean capped attainment and complete-attainment counts. The four rules must not be pooled as independent experiments. Original `compromise` identifiers map to Ideal; the new dataset uses `reference_compromise`. Original food/heatmap displays remain explicitly labeled as ideal-distance results; the reference release provides its own nutrient and food-type summaries.

The new choices improve all four outcomes over the observed profile means in every run, with mean attainment 95.67%, versus 97.98% under Ideal. None attains all 23 criteria. These are reference-mean improvements, not clinical adequacy or paired-person effects. The original reference values, activity assumptions and energy intervals are unchanged. The front-restricted conditional maximin sensitivity is a separate diagnostic and is not the Ref. rule.

Generate the current Table 9 and Table 10 sources with `scripts/select_reference_compromises.py`, or generate the full final bundle with `scripts/export_reference_analysis.py`. Earlier `extract_observed_comparison.py` and `export_publication.py` retain the original two-group/three-rule outputs for reproducibility; their tables do not contain the added Ref. rows.
