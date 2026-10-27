# POF 2017–2018 data validation

This validation uses the IBGE `Dados_20230713.zip` and `Documentacao_20230713.zip` releases and the November 2023 environmental workbook from the [OSF record](https://osf.io/g9d5y/). The official [IBGE microdata page](https://www.ibge.gov.br/estatisticas/sociais/saude/24786-pof-2017-2018.html) and [file index](https://ftp.ibge.gov.br/Orcamentos_Familiares/Pesquisa_de_Orcamentos_Familiares_2017_2018/Microdados/) identify the release. The workbook's download is `https://osf.io/download/fv3tx/`. The OSF file metadata reports the same SHA-256 as the local copy.

| Input | SHA-256 | Size | Distribution in this repository |
| --- | --- | ---: | --- |
| `Dados_20230713.zip` | `f5b71f85452345e6e82caee15c70578c948981d8a8e5f99bd90ec60fac5b7932` | 146,294,013 bytes | Link and checksum only |
| `Documentacao_20230713.zip` | `cbb075d2a8b986f0ddbe4800b09f972139d1d757dc3f3d373c76e9432048d755` | 5,203,471 bytes | Link and checksum only |
| OSF `e.book_Pegadas_alimentos_Brasil_planilhas_20231122.xlsx` | `988040f8e9c668d823c41b0839132a3494b9a3ad6e5a4945e18757542b16d4af` | 626,724 bytes | Link and checksum only |

The IBGE lists the microdata files as public. Public access does not by itself establish permission to republish them. The OSF node exposes no license in its API metadata, so its workbook is also linked rather than copied into this repository. The code's MIT license applies only to the code and original documentation. The [TBCA site](https://www.tbca.net.br/) states restrictions on reproducing its material and a confidentiality process for the POF–TBCA file; no TBCA nutrient table or derived coefficients are included here.

## Reading the records

`sec_diet.layout` uses the official *Consumo Alimentar* sheet of the IBGE variable dictionary. Its one-based positions confirm the zero-based positions in the code. `QUADRO` 72 and 73 identify the two collection days. `QTD` is grams with three decimal places. `V9017` is the recorded eating occasion. A blank `COD_PREPARACAO_FINAL` is documented for lines representing additions to foods and is **not** the same raw code as preparation 99. The older project extractor remapped occasions into six meals, set unparseable quantities to zero, and excluded foods outside an existing map. The SEC extractor retains original occasion and preparation fields and reports exclusions instead of applying those choices implicitly.

The unit of extraction is a person-day. The local JSONL output preserves one row per accepted consumption record. A stable hash replaces the composite respondent-day key; identifiers are not written in the aggregate validation. No age, meal, nutrient, or environmental-coverage filter is applied at extraction. A single recorded day does not represent long-term usual intake.

## Observed validation counts

The full run is recorded in [`validations/pof2018-source-validation.json`](validations/pof2018-source-validation.json) and [`validations/pof2018-extraction-manifest.json`](validations/pof2018-extraction-manifest.json). These are source and extraction diagnostics, not the confirmatory analytical cohort.

| Diagnostic | Count |
| --- | ---: |
| Consumption records | 1,175,390 |
| Respondents with records | 46,164 |
| Person-days with records | 85,018 |
| Records with blank preparation | 168,264 |
| Distinct food codes among blank-preparation records | 12 |
| Environmental workbook data rows | 2,701 |
| Person-days whose every row has numeric carbon and water coefficients after the addition crosswalk, including zeros | 84,851 |
| Person-days whose every row has strictly positive carbon and water coefficients | 36,096 |

All `QTD` fields in this release parsed as positive finite numbers. The validation flags 198 records over 5,000 g and records the minimum and maximum, without excluding them. The largest flagged items are primarily water and other beverages; a threshold alone is not evidence of an error. The validation found no short lines or exact duplicate lines. Counts from other source versions must be regenerated, not copied from this report.

The official consumption file also contains 29 absolute nutrient fields per record. All 1,175,390 rows have numeric, nonnegative entries in all 29 fields; the validation records positive and zero counts for each field without publishing any quantities. These are the nutrients attached to **observed consumption**, not an independently verified per-100-g coefficient table for candidate diets. The IBGE dictionary states that some zero nutrient values may indicate a quantity near zero or a nutrient not examined; the TBCA code is needed to distinguish cases in the original table. Numeric coverage alone does not establish independent nutritional validity. The SEC design uses within-key consistency diagnostics and a slope through the origin over all POF lines, with this limitation disclosed. The legacy extractor's first observed per-100-g value is not reused.

The workbook has 2,700 positive and one zero carbon coefficient, and 2,643 positive and 58 zero water coefficients. The zero carbon and water coefficients for public tap water account for 120,011 consumption records; other zero water values include fish and salt. Its `Dados_Referencias_2018` sheet explicitly describes the tap-water value as assigned zero and unpublished, so it should not be interpreted as a measured zero impact. The rationale for other zero water values remains unresolved. Those rows are excluded from the primary analytical cohort.

The exact food-code/preparation-code join covers 883,923 consumption records with positive coefficients for both dimensions. The 168,264 blank-preparation addition records have 12 food codes. Each has a single workbook row with preparation 99; this is a separately reported candidate crosswalk, supported by the dictionary's description of addition lines and the workbook's unique key. Another 212 consumption records share one unmatched exact key, `7800301#1`. The workbook contains other preparations for this food but not preparation 1; a nearest-name substitution is not justified. Days containing that unmatched optimized line are excluded by the primary cohort rule. Description-only fuzzy matching is not used.

## Rebuild locally

After installing the package, download the three files from the official links above into `data/raw/`. Keep the original ZIPs and workbook filenames or pass their actual paths. Run:

```powershell
sec-data-validation --pof data/raw/Dados_20230713.zip --documentation data/raw/Documentacao_20230713.zip --footprints data/raw/pegadas_alimentos.xlsx --output results/pof2018-source-validation.json
sec-diet-extract --pof data/raw/Dados_20230713.zip --output data/processed/pof2018-consumption.jsonl --manifest results/pof2018-extraction-manifest.json
```

The tools read `CONSUMO_ALIMENTAR.txt` directly from the official data ZIP. The JSONL contains food and preparation identifiers, observed grams, eating occasion, hour, day, and a respondent-day hash. It has no nutrient or footprint values. The manifest records source and output hashes and row counts. `data/raw/`, `data/processed/`, `results/`, and `logs/` are ignored by Git.

## Analytical cohort and frozen linkage

The independent [cohort validation](validations/pof2018-cohort-validation.json) joins every recorded person-day to `MORADOR.txt`, checks source nutrient consistency for energy, fiber and sodium, and applies the published selection rule. Of 85,018 person-days, 55,329 belong to adults aged 19–59; 53,632 have strictly positive carbon and water coefficients for every optimized line after observed tap water is held fixed; 48,920 have only the six known occasion codes; 48,736 have at least two occasions; and 48,323 have at least five food/preparation/occasion variables and positive reported energy. Keeping one eligible day per respondent yields 27,481 respondents. Six are selected from each of four age-by-sex strata, for 24 benchmark instances with 5–19 variables. The manifest holds opaque day hashes and no food or nutrient amounts.

The validation found 2,545 distinct non-water food/preparation keys in POF; none had more than one TBCA identifier. For energy, fiber and sodium, no key had both zero and positive per-100-g ratios or a within-key difference over 5%. This is an internal consistency result for POF's reported quantities, not an independent TBCA validation. The frozen method estimates per-gram coefficients locally from all POF lines with a weighted slope through the origin. No coefficient table is published. All 120,011 public-tap-water records have positive reported sodium, so the model keeps their nutrient contribution fixed even though the water mass is excluded from decision variables and the departure denominator.

The unmatched `7800301#1` and non-water rows with zero or absent environmental values remain outside the selected cohort. The workbook's assigned zero for public tap water is not interpreted as measured zero impact. Blank additions use preparation 99 only where that is the sole preparation row for the food; the observed raw blank remains distinct for nutrient estimation. The exact mathematical formulation, units, algorithms and analysis are in [the frozen design](protocol/README.md).

## Additional linkage questions for sensitivity work

1. Independently validate the POF embedded nutrient coefficients against an authorized composition source, if access and terms permit. `sec-data-validation --nutrients` accepts a local CSV for coverage diagnostics only.
2. Investigate the unmatched environmental key and zero-water values such as fish without inserting undocumented substitutions into the primary analysis.
3. Quantify uncertainty and boundary differences described in the workbook's `Notas_2018`, `Base_Pegadas_2018`, and `Dados_Referencias_2018` sheets before interpreting absolute footprints.

The present validations establish input and cohort coverage, not that any planned optimizer will finish or improve the observed diets. Those outcomes belong to the later execution phases.
