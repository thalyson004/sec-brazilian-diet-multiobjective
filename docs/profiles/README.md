# Dietary profiles and meals

The study defines four reference profiles: women and men aged 30 and 60, with low physical activity and weight maintenance. Each profile has its own nutrient targets, energy interval and set of observed POF meals. Reference heights and weights define the scenarios; they are not measurements assigned to the survey respondents.

A candidate menu selects one complete meal for each of six daily positions. Foods and recorded portions remain together, and a position can be empty if the profile's source records include an absence there. Energy is constrained to 95%-105% of the profile's estimated maintenance requirement. The nutritional objective averages capped attainment across 23 criteria, with a penalty for lower-target shortages.

| File | Contents |
| --- | --- |
| [DECISIONS.md](DECISIONS.md) | Sources, anthropometry, meal mapping and nutrient rules |
| [catalogue.json](catalogue.json) | Profile characteristics and objective sets |
| [targets.json](targets.json) and [references.json](references.json) | Nutritional targets and their sources |
| [PENALTY.md](PENALTY.md) | Reduced study used to select the shortage weight |
| [RUNNING.md](RUNNING.md) | Commands for the campaign, reconstruction and analysis |
| [TABLE-CONSOLIDATION.md](TABLE-CONSOLIDATION.md) | How per-run choices enter the article's summaries |

The completed campaign contains 1,920 runs and 15,022 reporting-front entries. [Complete menus and front files](../../fronts/meal-profile-study-v4.1-penalty-5/README.md) are available for all four profiles. The separate [reference-constrained selection](../../comparisons/reference-compromise-v1/README.md) uses all energy-feasible evaluated candidates from each run.
