# Published reporting fronts

The [whole-meal v4.1 study with shortage weight 5](meal-profile-study-v4.1-penalty-5/README.md) provides all 1,920 completed run fronts and 15,022 complete daily-menu entries. Each of four profiles has 480 fronts from six objective sets, four algorithms and 20 replications.

| Profile | Fronts | Menu entries | Files |
| --- | ---: | ---: | --- |
| F30 | 480 | 3,180 | [Front arrays](meal-profile-study-v4.1-penalty-5/F30/fronts.zip), [points](meal-profile-study-v4.1-penalty-5/F30/points.csv), [complete menus](meal-profile-study-v4.1-penalty-5/F30/menus.jsonl.gz) |
| F60 | 480 | 1,434 | [Front arrays](meal-profile-study-v4.1-penalty-5/F60/fronts.zip), [points](meal-profile-study-v4.1-penalty-5/F60/points.csv), [complete menus](meal-profile-study-v4.1-penalty-5/F60/menus.jsonl.gz) |
| M30 | 480 | 7,786 | [Front arrays](meal-profile-study-v4.1-penalty-5/M30/fronts.zip), [points](meal-profile-study-v4.1-penalty-5/M30/points.csv), [complete menus](meal-profile-study-v4.1-penalty-5/M30/menus.jsonl.gz) |
| M60 | 480 | 2,622 | [Front arrays](meal-profile-study-v4.1-penalty-5/M60/fronts.zip), [points](meal-profile-study-v4.1-penalty-5/M60/points.csv), [complete menus](meal-profile-study-v4.1-penalty-5/M60/menus.jsonl.gz) |

[runs.csv](meal-profile-study-v4.1-penalty-5/runs.csv) identifies each front and its original file hash. [selections.csv](meal-profile-study-v4.1-penalty-5/selections.csv) links the three reporting rules to members of these fronts. [The manifest](meal-profile-study-v4.1-penalty-5/manifest.json) records all counts and file checksums. These entries retain separate run identities even when food combinations repeat.

The release README explains coordinate units, joins and reproduction with `scripts/export_public_fronts.py`. It distinguishes the published reporting fronts from the larger penalized search archives and complete evaluation histories, which remain local.

The separate [reference-based selection analysis](../comparisons/compromise-selection-v1/README.md) checks which fronts contain joint improvements over the observed means and implements selection with explicit missing choices. It uses these published fronts without modifying the original release or its selection index.

The [final reference-constrained choice](../comparisons/reference-compromise-v1/README.md) additionally uses complete saved evaluation histories, recovering a jointly improving menu in every original run. Its 1,920 complete selections are published separately; they must not be assumed to belong to these original final reporting fronts.
