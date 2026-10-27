# Input data

The study uses POF 2017-2018 food-consumption records and a food environmental-footprint workbook. Download the files from their original sources:

- [IBGE POF microdata and documentation](https://ftp.ibge.gov.br/Orcamentos_Familiares/Pesquisa_de_Orcamentos_Familiares_2017_2018/Microdados/): `Dados_20230713.zip` and the accompanying documentation archive.
- [Environmental footprint workbook](https://osf.io/download/fv3tx/): save it locally as `pegadas_alimentos.xlsx`.

Place these files in `raw/`. Extracted records and prepared local inputs are written to `processed/` and `results/`. Both data directories are ignored by Git. The [data validation](../docs/data-validation.md) records input checksums and source-field information; its respondent-day cohort is from an earlier benchmark.

The whole-meal study uses the nutrients reported in POF to evaluate 23 profile-specific criteria. The source archives, environmental workbook, food-level nutrient coefficients and unselected source meal pools are obtained or reconstructed locally.

The repository publishes [all reporting-front menus](../fronts/meal-profile-study-v4.1-penalty-5/README.md), [energy-restricted observed diets](../comparisons/observed-profile-energy-context/README.md) and [reference-constrained selections](../comparisons/reference-compromise-v1/README.md), including their food names and portions. The [profile guide](../docs/profiles/README.md) describes the current study.
