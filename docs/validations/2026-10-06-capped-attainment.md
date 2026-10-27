# Capped-attainment campaign validation — 6 October 2026

> This record describes the campaign validation on 6 October 2026. The [complete reporting fronts and menus](../../fronts/meal-profile-study-v4.1-penalty-5/README.md) and [reference selections](../../comparisons/reference-compromise-v1/README.md) were released later.

## Completed numerical campaign

The corrected weight comparison completed 864 runs at 3,300 evaluations (2,851,200 total), with no failures or warnings. It used numerical code 21be27a and selected weight 5 by the registered rule. Its outcomes SHA-256 is e9d2dda8f8b6858994e27eea976c47f5f269b3f8dfffef769c30d458f7b9271e.

The main campaign completed 1,920 runs at 16,500 evaluations (31,680,000 total), with no failures or warnings. Numerical execution revision: b36df1b943a9f24b338656d006c720da1ff891f5. Every run has a nonempty energy-feasible reporting front. The reporting fronts have 15,022 entries, ranging from one to 70 per run (median five). Entries across runs need not be distinct menus. All 180 Holm-adjusted hypervolume contrasts have adjusted p >= 0.05; this is not an equivalence test.

## Reconstruction and independent checks

All 15,022 saved reporting-front vectors were independently rescored for physical objectives, normalized coordinates and energy feasibility. Their nondominance and every run's evaluation count were checked. The byte counts and SHA-256 values of 7,680 saved optimizer artifacts match the recorded metrics. No inconsistency was found. The complete-front JSONL export has SHA-256 e220b56ea72230ab785a5a9a33e4d92de6d070953ae1965a19ba8f1d84d256b5. The 39,504-row food summary has SHA-256 8dd0bb9a91207330ffdfd6fec83a51d5ed56ed3456df667c550e70d5d856c131.

The full controlled suite passed 26 tests (39.828 seconds in the final run). It covers capped coverage, effective shortage weighting, four algorithm adapters, finite SPEA2 selection for constant coordinates, unchanged positive-span survival, whole-meal preservation, English labels, publication summaries, transparent supported 3D faces and complete per-menu attainment cells. The full real-source campaign additionally establishes that these outputs can be generated for every planned configuration.

## Publication outputs

The original numerical artifacts and original article analysis remain unchanged. The separate publication directory stores larger-font criterion heatmaps, revised front displays, nutritional selection summaries, largest-change food displays and full example-menu tables with physical outcomes. Its manifest identifies the original execution and input hashes, plus the exact publication and renderer source hashes. These are deterministic postprocessing steps without additional optimizer runs. The unified script invokes them automatically for future capped-attainment campaigns; scripts/export_publication.py regenerates them for an already completed campaign.

Mean compromise attainment is 97.9821%, with 19.5651 fully attained criteria on average and 32/1,920 menus attaining all 23 (all M30). Maximum-attainment selections reach all criteria in 291/1,920 cases; minimum-departure selections in 30/1,920. Soft nutrient goals and these criterion counts remain distinct from the hard energy interval.

## Preservation and interpretation

Historical v3 results, the first v4 calibration and the interrupted v4 main attempt remain in their original directories. Only corrected v4.1 experiments support the revised manuscript. Source records, coefficients and complete individual menus remain ignored local outputs; aggregate summaries and the requested manuscript examples are the publication material. Neither high average attainment, filled visual facets nor descriptive food changes establish clinical suitability, continuous feasibility or population effects.
