# Whole-meal formulation validation - 2026-10-06

## Scope

Active design: `sec2026-pof-meals-v3`. Decision vectors contain six categorical whole-meal indices. Food amounts and all 29 reported nutrient/energy fields are preserved from source records. Energy is constrained; 23 nutritional criteria contribute to deviation.

## Automated checks

Command: `.venv\Scripts\python -m unittest discover -s tests -v`.

All 13 tests pass: seven historical adapter checks and six meal-design checks. The latter cover named/time-based mapping, invalid times, absent positions, original portions and nutrient amounts, six-index membership, the complete IEEE reference nutrient list, four algorithms in two and three objectives, rescoring, matched initialization, resume and analysis outputs.

The analysis integration test executes 64 synthetic runs at 18 evaluations, covering four profiles, two scenarios, four algorithms and two replicates. It validates the 64-run analysis manifest, 192 six-position selected menus, 2D SVG and 3D PDF fronts, nutrient and food-group outcomes, statistical tables and the generated preparation table. Synthetic observations are explicitly marked fixtures and do not enter the article's scientific results.

## Preparation from the source files

The unified script was executed with `--prepare-only` using the registered original POF ZIP and footprint workbook. Selected respondent-days: F30=437, F60=339, M30=347, M60=248. Pool sizes, empty-position counts, exclusions and source/instance checksums are recorded in [preparation-summary.json](../profiles/preparation-summary.json). The fractional meal-mixture diagnostics are feasible for each profile; this does not establish strict target feasibility for integer menus.

The four source-derived instances were also checked in 32 short runs: four profiles, NC and NCW, four algorithms, one replicate and 132 evaluations per run (4,224 evaluations). All passed saved-candidate rescoring and completion checks. The aggregate record is [short-run-validation.json](../profiles/short-run-validation.json); individual meals and candidate arrays remain local.

## Unified Windows entry point

The exact `run-study.ps1 -PrepareOnly` command was executed successfully in Windows PowerShell 5.1 with the original inputs. Native notices written to stderr are preserved and command success is determined by exit status. An intentionally missing POF input was rejected with the Python argument-validation exit code 2 and propagated by the wrapper. No optimizer campaign was started in these wrapper checks.

## Interpretation and limits

These checks establish implementation consistency and pipeline operability. They do not estimate algorithm superiority, final nutritional attainment or environmental reductions. The 1,920-run, 16,500-evaluation main campaign has not been started. The active manuscript reports preparation and the revised protocol, and preserves prior scientific outcomes separately.

Both current LaTeX entry points compile with BibTeX and repeated pdflatex passes. The compiled manuscript was visually inspected for the full nutritional table, source-to-meal mapping and whole-meal equations. DOI annotations are checked in the final PDF.
