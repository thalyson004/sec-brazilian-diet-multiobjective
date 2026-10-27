# Revision checks — 6 October 2026

## Scope

These checks concern editorial corrections, graphics, compatibility with saved respondent-day results and the characterization of the four proposed profiles. They do not validate a new profile-based optimization experiment.

## Software and source characterization

- The existing seven controlled software tests passed after the module and command renames. They cover arithmetic, dominance and hypervolume, four optimizer adapters, damaged or missing outputs, parallel execution and repeated survival operations in two and three dimensions.
- The package installed successfully in the local virtual environment with `pip install --no-deps -e .`.
- Saved run `406960d266f248773dfcc057` passed the current result checker, including rescoring and completion checks. Only this saved run was rechecked during this revision; this is not a fresh check of the full campaign.
- `sec-describe-profiles` read the original POF ZIP and environmental workbook without modifying either source. Exact-age eligible groups contain 712 respondent-days for F30, 562 for F60, 550 for M30 and 401 for M60. Their respective distinct respondent counts are 399, 315, 315 and 226.
- The characterization reports numerical status for the 29 available dietary fields, coverage and input hashes. A reported zero does not establish measured nutrient absence. No individual quantities are published in this report.
- Original frozen JSON payloads and saved run logs were retained byte for byte. Compatibility with historical termination names is handled by the checker; newly generated runs use `evaluation_limit`.

## Graphics and manuscript

- Existing aggregate results were rendered as vector PDF and SVG with shared typography and scales. The three-dimensional attainment summaries have complementary threshold maps.
- The workflow remains an editable SVG with a vector PDF for LaTeX. It still describes the respondent-day experiment.
- The manuscript compiled with `pdflatex`, BibTeX and two final LaTeX passes, with no unresolved citation or cross-reference warnings. The revised draft has 14 pages and 22 bibliography entries.
- The compiled PDF contains 16 distinct clickable DOI destinations. No DOI was invented for the two newly cited conference papers.
- Text inspection at final manuscript scale found approximately 9-point figure labels in the workflow, three-dimensional comparison and companion map.

## Remaining dependency

The POF 2017–2018 did not collect weight or height. The profile catalogue therefore leaves anthropometry, physical activity and nutrient targets unresolved. The author must select their source before maintenance-energy targets and the new experiment can be finalized. Results from the original 19,200-run campaign are not profile-based results.
