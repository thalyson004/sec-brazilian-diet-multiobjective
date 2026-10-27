"""Publish all reporting fronts of the calibrated 1,920-run whole-meal study."""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import ExitStack
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import zipfile

import numpy as np

from sec_diet.english_labels import english_food, english_group


PROFILES = ('F30', 'F60', 'M30', 'M60')
POSITIONS = ('Breakfast', 'Morning snack', 'Lunch', 'Afternoon snack', 'Dinner', 'Supper')
META = ('run_id', 'profile_id', 'objective_subset', 'algorithm', 'replicate', 'seed')
MEAL_COLUMNS = tuple('meal_' + name.lower().replace(' ', '_') + '_index' for name in POSITIONS)
OUTCOMES = ('attainment_percent', 'carbon_kg', 'water_l', 'departure_percent')
NORMALIZED = tuple('normalized_' + name for name in 'NCWD')
SEARCH = tuple('search_' + name for name in 'NCWD')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True,
                               allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def csv_rows(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def csv_writer(stack, path, fields):
    stream = stack.enter_context(path.open('w', encoding='utf-8', newline=''))
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    return writer


def physical(raw):
    return dict(zip(OUTCOMES, (float(raw[0]), float(raw[1]) / 1000,
                               float(raw[2]), float(raw[3]) * 100)))


def export(campaign, output):
    if output.exists():
        raise ValueError('Use a new output directory; existing releases are preserved')
    completion = read_json(campaign / 'completion.json')
    study = read_json(campaign / 'study.json')
    design = study['design']
    rows = csv_rows(campaign / 'run-matrix.csv')
    if (design.get('nutrition_objective') != 'capped_attainment_percent'
            or not design.get('penalty_enabled') or design.get('penalty_weight') != 5
            or design['replicates'] != 20
            or tuple(design['objective_subsets']) != ('N,C', 'N,W', 'N,D', 'N,C,W', 'N,C,D', 'N,W,D')
            or tuple(design['algorithms']) != ('NSGA2', 'SPEA2', 'NSGA3', 'SMSEMOA')):
        raise ValueError('This release requires the calibrated four-algorithm, six-scenario main study')
    if (completion['failures'] or completion['complete_runs'] != completion['planned_runs']
            or len(rows) != completion['complete_runs']):
        raise ValueError('A complete campaign is required')
    if tuple(design['profiles']) != PROFILES or len({r['run_id'] for r in rows}) != len(rows):
        raise ValueError('Four profiles and unique run identifiers are required')
    cells = Counter((r['profile_id'], r['objective_subset'], r['algorithm']) for r in rows)
    expected_cells = {(p, s, a) for p in PROFILES for s in design['objective_subsets']
                      for a in design['algorithms']}
    if set(cells) != expected_cells or set(cells.values()) != {design['replicates']}:
        raise ValueError('The run matrix does not cover the complete design')
    interpretation = campaign / 'interpretation'
    source_menus = interpretation / 'all-pareto-menus.jsonl.gz'
    reconstruction = read_json(interpretation / 'manifest.json')
    if (sha256(source_menus) != reconstruction['all_front_sha256']
            or sha256(campaign / 'execution.json') != reconstruction['base_execution_sha256']
            or sha256(campaign / 'article/analysis-manifest.json') != reconstruction['base_analysis_manifest_sha256']):
        raise ValueError('Reconstructed menus do not match the saved campaign')

    output.mkdir(parents=True)
    fronts = {}
    sizes = Counter()
    counts = Counter()
    with ExitStack() as stack:
        index = csv_writer(stack, output / 'runs.csv', META + (
            'front_size', 'archive', 'archive_member', 'source_front_sha256'))
        archives, points, menus = {}, {}, {}
        for profile in PROFILES:
            directory = output / profile
            directory.mkdir()
            archives[profile] = stack.enter_context(zipfile.ZipFile(
                directory / 'fronts.zip', 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6))
            points[profile] = csv_writer(stack, directory / 'points.csv',
                META + ('front_offset', 'candidate_index') + MEAL_COLUMNS + OUTCOMES + NORMALIZED + SEARCH)
            binary = stack.enter_context((directory / 'menus.jsonl.gz').open('wb'))
            compressed = stack.enter_context(gzip.GzipFile(
                fileobj=binary, mode='wb', filename='', mtime=0, compresslevel=6))
            menus[profile] = stack.enter_context(io.TextIOWrapper(compressed, encoding='utf-8', newline='\n'))
        for row in rows:
            run_id, profile = row['run_id'], row['profile_id']
            if Path(run_id).name != run_id or any(c not in '0123456789abcdef' for c in run_id):
                raise ValueError('Unexpected run identifier')
            source = campaign / 'runs' / run_id / 'front.npz'
            with np.load(source, allow_pickle=False) as data:
                front = {key: data[key].copy() for key in ('indices', 'X', 'raw', 'normalized', 'search')}
            n = len(front['indices'])
            if (not n or front['X'].shape != (n, 6) or len(set(front['indices'])) != n
                    or any(front[k].shape != (n, 4) or not np.isfinite(front[k]).all()
                           for k in ('raw', 'normalized', 'search'))):
                raise ValueError('Invalid reporting front: ' + run_id)
            front['lookup'] = {int(v): i for i, v in enumerate(front['indices'])}
            fronts[run_id] = front
            member = run_id + '.npz'
            entry = zipfile.ZipInfo(member, date_time=(1980, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o644 << 16
            archives[profile].writestr(entry, source.read_bytes(),
                compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
            index.writerow(dict(row, front_size=n, archive=profile + '/fronts.zip',
                                archive_member=member, source_front_sha256=sha256(source)))
            for i in range(n):
                values = dict(row, front_offset=i, candidate_index=int(front['indices'][i]))
                values.update(zip(MEAL_COLUMNS, map(int, front['X'][i])))
                values.update(physical(front['raw'][i]))
                values.update(zip(NORMALIZED, map(float, front['normalized'][i])))
                values.update(zip(SEARCH, map(float, front['search'][i])))
                points[profile].writerow(values)
            sizes[profile] += n
            counts[profile] += 1
        by_id = {row['run_id']: row for row in rows}
        seen = set()
        with gzip.open(source_menus, 'rt', encoding='utf-8') as stream:
            for line in stream:
                record = json.loads(line)
                run_id, candidate = record['run_id'], int(record['candidate_index'])
                row, front = by_id[run_id], fronts[run_id]
                key = (run_id, candidate)
                if key in seen or candidate not in front['lookup']:
                    raise ValueError('Duplicate or unknown front menu')
                seen.add(key)
                i = front['lookup'][candidate]
                if (any(str(record[k]) != str(row[k]) for k in META if k != 'seed')
                        or not np.array_equal(record['raw_NCWD'], front['raw'][i])
                        or not np.array_equal(record['normalized_NCWD'], front['normalized'][i])
                        or len(record['meals']) != 6):
                    raise ValueError('Menu metadata or outcomes differ from the saved front')
                public_meals = []
                for slot, meal in enumerate(record['meals']):
                    if int(meal['meal_index']) != int(front['X'][i, slot]):
                        raise ValueError('Menu meal indices differ from the saved genotype')
                    public_meals.append(dict(position=POSITIONS[slot], items=[dict(
                        food_code=item['food_code'], preparation_code=item['preparation_code'],
                        food_name=english_food(item['food_code']),
                        food_group=english_group(item['food_group']), grams=item['grams'],
                        tap_water=item['tap_water']) for item in meal['items']]))
                public = dict(row, replicate=int(row['replicate']), seed=int(row['seed']),
                    front_offset=i, candidate_index=candidate, meal_indices=front['X'][i].tolist(),
                    outcomes=physical(front['raw'][i]),
                    normalized_NCWD=front['normalized'][i].tolist(),
                    search_NCWD=front['search'][i].tolist(), meals=public_meals)
                menus[row['profile_id']].write(json.dumps(public, ensure_ascii=False,
                    separators=(',', ':'), allow_nan=False) + '\n')
        if len(seen) != sum(sizes.values()) or len(seen) != reconstruction['front_menu_count']:
            raise ValueError('The complete front/menu correspondence is missing entries')

    choices = csv_rows(campaign / 'article/diet-selections.csv')
    selection_cells = Counter((r['run_id'], r['selection']) for r in choices)
    expected_rules = {'nutrition_max', 'compromise', 'departure_min'}
    if (set(selection_cells) != {(r['run_id'], q) for r in rows for q in expected_rules}
            or set(selection_cells.values()) != {1}
            or any((r['run_id'], int(r['candidate_index'])) not in seen
                   or any(r[k] != by_id[r['run_id']][k] for k in META) for r in choices)):
        raise ValueError('Saved selections are incomplete or refer outside the released fronts')
    for source, destination in (
            (campaign / 'study.json', output / 'study.json'),
            (campaign / 'execution.json', output / 'execution.json'),
            (campaign / 'completion.json', output / 'completion.json'),
            (campaign / 'article/diet-selections.csv', output / 'selections.csv')):
        shutil.copyfile(source, destination)
    readme = release_readme(counts, sizes)
    (output / 'README.md').write_text(readme, encoding='utf-8', newline='\n')
    manifest = dict(schema_version='1.0', campaign=campaign.name,
        execution_code_revision=read_json(campaign / 'execution.json')['code_revision'],
        exporter_sha256=sha256(Path(__file__)),
        english_labels_sha256=sha256(Path(__file__).resolve().parents[1] / 'docs/profiles/food-labels-en.json'),
        source_execution_sha256=sha256(campaign / 'execution.json'),
        source_analysis_sha256=sha256(campaign / 'article/analysis-manifest.json'),
        source_reconstruction_sha256=sha256(interpretation / 'manifest.json'),
        source_complete_menus_sha256=sha256(source_menus),
        profiles={p: dict(fronts=counts[p], entries=sizes[p]) for p in PROFILES},
        front_count=len(rows), menu_count=len(seen), selection_count=len(choices),
        files={p.relative_to(output).as_posix(): dict(bytes=p.stat().st_size, sha256=sha256(p))
               for p in sorted(output.rglob('*')) if p.is_file()})
    write_json(output / 'manifest.json', manifest)
    return {key: manifest[key] for key in ('front_count', 'menu_count', 'selection_count', 'profiles')}


def release_readme(counts, sizes):
    table = '\n'.join(f'| {p} | {counts[p]} | {sizes[p]} |' for p in PROFILES)
    return f'''# Complete reporting fronts: whole-meal profile study v4.1, penalty 5

This release contains all {sum(counts.values()):,} saved reporting fronts and their {sum(sizes.values()):,} complete daily-menu entries from the finished campaign. Each profile contributes six objective sets (NC, NW, ND, NCW, NCD, NWD), four algorithms (NSGA-II, SPEA2, NSGA-III, SMS-EMOA) and 20 replications. Each run received 16,500 evaluations. Repeated menus within different runs retain their run identities. These computational menus are descriptive research results, not dietary prescriptions.

| Profile | Run fronts | Menu entries |
| --- | ---: | ---: |
{table}

## Files and correspondence

- `runs.csv`: one row per run, including profile, objective set, algorithm, replication, seed, front size, ZIP path/member and the original NPZ SHA-256.
- `<profile>/fronts.zip`: 480 original `front.npz` files named `<run_id>.npz`, preserved byte for byte. A front belongs to its own run and objective set. No cross-run or cross-scenario Pareto filtering is applied.
- `<profile>/points.csv`: one row per front entry, with metadata, candidate identifier, six meal indices, physical outcomes, unpenalized normalized coordinates and penalized search coordinates.
- `<profile>/menus.jsonl.gz`: the same entries with full six-position food/portion lists, English names/groups, food/preparation codes and grams. An empty item list denotes an observed absent position. All foods and portions in a selected meal are preserved.
- `selections.csv`: the original 5,760 rule-specific selections used for dietary summaries, keyed by `run_id` and `candidate_index`. It contains one selection per run for each of `nutrition_max`, `compromise` and `departure_min`.
- `study.json`, `execution.json`, `completion.json`: frozen design, numerical execution provenance/environment and completion counts.
- `manifest.json`: counts, source and exporter hashes, and SHA-256/byte counts for every released file.

Join `runs.csv`, points, menus and selections by `run_id`. Within a run, `candidate_index` is the identifier in the original evaluated-candidate history. `front_offset` is its zero-based row in that run's NPZ arrays. The six `meal_indices` are zero-based indices into the corresponding profile/position pools, in breakfast, morning snack, lunch, afternoon snack, dinner and supper order. Complete published food lists allow inspection without obtaining those pools.

## Objective coordinates and units

All NPZ objective arrays have four columns in N, C, W, D order, including coordinates omitted from a particular search. `raw` stores capped attainment in percent, carbon in **g CO2e/day**, water in L/day, and departure as a dimensionless fraction. `normalized` stores the unpenalized minimization coordinates: N is `1 - attainment_percent/100`, while C/W/D use fixed profile-pool bounds. `search` stores the penalized coordinates associated with those same points. `X` stores six meal indices; `indices` stores candidate identifiers.

The CSV and JSON outcome fields convert carbon to **kg CO2e/day** (`carbon_kg`) and departure to **percent** (`departure_percent`). `attainment_percent` and `water_l` retain percent and L/day. `normalized_NCWD` and `search_NCWD` retain original coordinate values. The ZIPs contain the saved reporting fronts; the larger penalized search archives and complete evaluation histories remain separate local outputs. Reporting fronts are empirical nondominated sets for their own objective subsets, not established true global Pareto fronts.

## Relation to Tables 9 and 10

The optimized side of the observed comparison uses `selection=compromise`: 480 selections per profile. The nutritional selection table separately summarizes all three rules over those same 480 runs. A run has the same weight regardless of front size; rules can choose the same menu. GLOBAL averages the four profile means equally. See the [consolidation guide](../../docs/profiles/TABLE-CONSOLIDATION.md). The complete menus in the [observed comparison](../../comparisons/observed-profile-energy-context/README.md) correspond to the compromise subset here.

## Read the files

Python standard libraries read the CSV, ZIP and compressed JSON Lines files; NumPy reads NPZ arrays. For example, from this release directory:

```python
import csv, gzip, io, json, zipfile
import numpy as np

with open('runs.csv', encoding='utf-8', newline='') as stream:
    run = next(csv.DictReader(stream))
with zipfile.ZipFile(run['archive']) as archive:
    with np.load(io.BytesIO(archive.read(run['archive_member'])), allow_pickle=False) as front:
        print(front['X'], front['raw'])
with gzip.open(run['profile_id'] + '/menus.jsonl.gz', 'rt', encoding='utf-8') as stream:
    menu = next(json.loads(line) for line in stream if json.loads(line)['run_id'] == run['run_id'])
print(menu['outcomes'], menu['meals'])
```

## Reproduce the release

From the standalone repository with the completed numerical campaign and its `interpretation/` export available locally:

```powershell
.venv/Scripts/python scripts/export_public_fronts.py --campaign results/meal-profile-study-v4.1-penalty-5 --output results/public-fronts-reproduction
```

The command starts no optimization, requires a new output directory, checks each reconstructed menu against its saved front and confirms that every saved selection is present. ZIP/GZIP timestamps and output ordering are fixed for reproducible files. Original source data and food-level nutrient coefficients are obtained separately under their source terms. The public release includes optimized food/portion lists and menu-level objectives; source nutrient coefficients and unselected meal pools remain local. To rerun the full experiment, follow [RUNNING.md](../../docs/profiles/RUNNING.md).
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export(args.campaign, args.output), indent=2))


if __name__ == '__main__':
    main()
