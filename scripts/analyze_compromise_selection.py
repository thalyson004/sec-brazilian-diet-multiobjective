"""Compare saved-front selection rules and bound attainable joint improvement."""
from __future__ import annotations

import argparse
from collections import defaultdict
import csv
import gzip
import hashlib
import io
import json
from pathlib import Path

import numpy as np

from sec_diet.compromise_selection import reference_gains, select_reference_compromise


PROFILES = ('F30', 'F60', 'M30', 'M60')
METRICS = ('attainment_percent', 'carbon_kg', 'water_l', 'departure_percent')
METHODS = ('original_distance', 'all_four_distance', 'reference_NCW', 'reference_NCWD',
           'minimum_water_bound', 'minimum_departure_bound')


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False,
                               allow_nan=False) + '\n', encoding='utf-8', newline='\n')


def read_csv(path):
    with path.open(encoding='utf-8', newline='') as stream:
        return list(csv.DictReader(stream))


def write_csv(path, rows):
    with path.open('w', encoding='utf-8', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def observed_departures(campaign, comparison, front_manifest):
    from sec_diet.profile_model import ProfileModel
    execution = read_json(campaign / 'execution.json')
    if digest(campaign / 'execution.json') != front_manifest['source_execution_sha256']:
        raise ValueError('Departure reference must use the released numerical campaign')
    directories = [p for p in (campaign / 'inputs').iterdir()
                   if p.is_dir() and all((p / (v + '.json')).exists() for v in PROFILES)]
    if len(directories) != 1 or digest(directories[0] / 'manifest.json') != execution['instance_manifest_sha256']:
        raise ValueError('Cannot identify the executed profile inputs')
    design = read_json(campaign / 'study.json')['design']
    models = {p: ProfileModel(read_json(directories[0] / (p + '.json')), design) for p in PROFILES}
    rows = []
    for row in read_csv(comparison / 'observed-outcomes.csv'):
        model = models[row['profile_id']]
        value = model.evaluate(model.initial_pool[int(row['retained_day_index'])])
        expected = (value['adequacy_percent'], value['raw']['C'] / 1000, value['raw']['W'])
        if not np.allclose(expected, [float(row[k]) for k in METRICS[:3]], rtol=1e-12, atol=1e-12):
            raise ValueError('Observed day differs from the executed pool')
        rows.append(dict(profile_id=row['profile_id'], observed_day_id=row['observed_day_id'],
                         retained_day_index=int(row['retained_day_index']),
                         departure_percent=value['raw']['D'] * 100))
    return dict(definition='Original D of each energy-matched observed day relative to the full retained profile mean food/preparation/position vector; excludes tap water',
                source_execution_sha256=digest(campaign / 'execution.json'),
                source_observed_outcomes_sha256=digest(comparison / 'observed-outcomes.csv'),
                source_input_manifest_sha256=execution['instance_manifest_sha256'],
                generator_sha256=digest(Path(__file__)), rows=rows)


def analyze(fronts, comparison, output, campaign=None, departure_reference=None):
    if output.exists():
        raise ValueError('Use a new output directory; previous results are preserved')
    fm = read_json(fronts / 'manifest.json')
    for name in ['runs.csv', 'selections.csv'] + [p + '/points.csv' for p in PROFILES]:
        if digest(fronts / name) != fm['files'][name]['sha256']:
            raise ValueError('Released input hash mismatch: ' + name)
    reference = (observed_departures(campaign, comparison, fm) if campaign else read_json(departure_reference))
    if (reference['source_execution_sha256'] != fm['source_execution_sha256']
            or reference['source_observed_outcomes_sha256'] != digest(comparison / 'observed-outcomes.csv')):
        raise ValueError('Departure reference belongs to different observations or execution')
    observed = read_csv(comparison / 'observed-outcomes.csv')
    departures = {(r['profile_id'], r['observed_day_id']): r['departure_percent'] for r in reference['rows']}
    if set(departures) != {(r['profile_id'], r['observed_day_id']) for r in observed}:
        raise ValueError('Observed departure reference does not cover the comparator')
    original = {r['run_id']: int(r['candidate_index']) for r in read_csv(fronts / 'selections.csv')
                if r['selection'] == 'compromise'}
    records, summaries, cells, selections = [], {}, defaultdict(list), defaultdict(list)
    runs = read_csv(fronts / 'runs.csv')
    for profile in PROFILES:
        obs = [r for r in observed if r['profile_id'] == profile]
        base = np.array([np.mean([float(r[k]) for r in obs]) for k in METRICS[:3]] +
                        [np.mean([departures[(profile, r['observed_day_id'])] for r in obs])])
        grouped = defaultdict(list)
        for row in read_csv(fronts / profile / 'points.csv'):
            grouped[row['run_id']].append(row)
        if set(grouped) != {r['run_id'] for r in runs if r['profile_id'] == profile}:
            raise ValueError('Incomplete profile run coverage')
        for run_id, points in grouped.items():
            points.sort(key=lambda r: int(r['front_offset']))
            v = np.array([[float(r[k]) for k in METRICS] for r in points])
            norm = np.array([[float(r['normalized_' + k]) for k in 'NCWD'] for r in points])
            ids = np.array([int(r['candidate_index']) for r in points])
            gains = reference_gains(v, base)
            original_index = int(np.flatnonzero(ids == original[run_id])[0])
            columns = ['NCWD'.index(k) for k in points[0]['objective_subset'].split(',')]
            if original_index != int(np.argmin(np.linalg.norm(norm[:, columns], axis=1))):
                raise ValueError('Saved compromise differs from its stated distance rule')
            selected = dict(original_distance=original_index,
                all_four_distance=int(np.argmin(np.linalg.norm(norm, axis=1))),
                reference_NCW=select_reference_compromise(v, base, ids),
                reference_NCWD=select_reference_compromise(v, base, ids, protect_departure=True),
                minimum_water_bound=int(np.argmin(v[:, 2])),
                minimum_departure_bound=int(np.argmin(v[:, 3])))
            for method, i in selected.items():
                row = points[0]
                record = {k: row[k] for k in ('run_id', 'profile_id', 'objective_subset', 'algorithm', 'replicate', 'seed')}
                record.update(method=method, available=i is not None,
                    candidate_index=int(ids[i]) if i is not None else '',
                    improves_NCW=bool((gains[i, :3] > 1e-12).all()) if i is not None else False,
                    improves_NCWD=bool((gains[i] > 1e-12).all()) if i is not None else False)
                record.update({k: float(v[i, j]) if i is not None else '' for j, k in enumerate(METRICS)})
                records.append(record)
                cells[(profile, row['objective_subset'], row['algorithm'], method)].append(record)
                if method.startswith('reference_') and i is not None:
                    selections[(run_id, int(ids[i]))].append(method)
        summaries[profile] = dict(observed_n=len(obs), observed_means=dict(zip(METRICS, map(float, base))),
                                  planned_runs=len(grouped), methods={})
        for method in METHODS:
            rows = [r for r in records if r['profile_id'] == profile and r['method'] == method]
            available = [r for r in rows if r['available']]
            summaries[profile]['methods'][method] = dict(
                available_runs=len(available), missing_runs=len(rows) - len(available),
                improves_NCW=sum(r['improves_NCW'] for r in rows),
                improves_NCWD=sum(r['improves_NCWD'] for r in rows),
                conditional_means={k: float(np.mean([r[k] for r in available])) if available else None for k in METRICS})
    global_summary = dict(observed_n=len(observed), planned_runs=len(runs),
        observed_means={k: float(np.mean([summaries[p]['observed_means'][k] for p in PROFILES])) for k in METRICS}, methods={})
    for method in METHODS:
        group = [summaries[p]['methods'][method] for p in PROFILES]
        global_summary['methods'][method] = {k: sum(r[k] for r in group)
                                            for k in ('available_runs', 'missing_runs', 'improves_NCW', 'improves_NCWD')}
        global_summary['methods'][method]['conditional_equal_profile_means'] = {
            k: float(np.mean([r['conditional_means'][k] for r in group]))
            if all(r['conditional_means'][k] is not None for r in group) else None for k in METRICS}
    summaries['GLOBAL'] = global_summary
    output.mkdir(parents=True)
    write_json(output / 'observed-departure-reference.json', reference)
    write_json(output / 'summary.json', summaries)
    write_csv(output / 'run-selections.csv', records)
    cell_rows = []
    for (p, s, a, m), group in sorted(cells.items()):
        cell_rows.append(dict(profile_id=p, objective_subset=s, algorithm=a, method=m,
            planned_runs=len(group), available_runs=sum(r['available'] for r in group),
            improves_NCW=sum(r['improves_NCW'] for r in group), improves_NCWD=sum(r['improves_NCWD'] for r in group)))
    write_csv(output / 'coverage-by-cell.csv', cell_rows)
    menu_count = 0
    with (output / 'selected-menus.jsonl.gz').open('wb') as binary:
        with gzip.GzipFile(fileobj=binary, filename='', mtime=0, mode='wb') as compressed:
            with io.TextIOWrapper(compressed, encoding='utf-8', newline='\n') as target:
                for p in PROFILES:
                    if digest(fronts / p / 'menus.jsonl.gz') != fm['files'][p + '/menus.jsonl.gz']['sha256']:
                        raise ValueError('Released menus hash mismatch')
                    with gzip.open(fronts / p / 'menus.jsonl.gz', 'rt', encoding='utf-8') as source:
                        for line in source:
                            menu = json.loads(line)
                            for method in selections.get((menu['run_id'], menu['candidate_index']), []):
                                target.write(json.dumps(dict(menu, selection_method=method), ensure_ascii=False,
                                    separators=(',', ':'), allow_nan=False) + '\n')
                                menu_count += 1
    if menu_count != sum(len(v) for v in selections.values()):
        raise ValueError('Conditional menu export is incomplete')
    (output / 'compromise-feasibility.tex').write_text(render_table(summaries), encoding='utf-8', newline='\n')
    (output / 'README.md').write_text(render_readme(summaries), encoding='utf-8', newline='\n')
    write_json(output / 'manifest.json', dict(analysis='Retrospective reference-based selection sensitivity; no optimization rerun',
        source_front_manifest_sha256=digest(fronts / 'manifest.json'),
        source_observed_outcomes_sha256=digest(comparison / 'observed-outcomes.csv'),
        script_sha256=digest(Path(__file__)),
        selector_sha256=digest(Path(__file__).resolve().parents[1] / 'src/sec_diet/compromise_selection.py'),
        conditional_menu_count=menu_count,
        files={p.name: dict(bytes=p.stat().st_size, sha256=digest(p)) for p in sorted(output.iterdir()) if p.is_file()}))
    return summaries


def render_table(summary):
    lines = [r'\begin{table*}[pos=htbp]', r'\centering\small',
        r'\caption{Post-selection limits and availability of joint improvements on the saved reporting fronts. Water values are mean L/day. Min. W independently selects the lowest-water member of each run front, providing a lower bound for any one-menu-per-run selection. $\Delta$ compares that bound with the observed mean. Joint NCW and NCWD count fronts with simultaneous improvement over the profile observed means in the corresponding physical outcomes; these are protected outcomes, not new search scenarios. GLOBAL averages profile means equally and sums counts.}',
        r'\label{tab:compromise-feasibility}', r'\begin{tabularx}{\textwidth}{Xrrrrrr}',
        r'\toprule', r'Profile & Observed W & Comp. W & Min. W & $\Delta$ (\%) & Joint NCW & Joint NCWD \\', r'\midrule']
    for p in PROFILES + ('GLOBAL',):
        row = summary[p]
        key = 'conditional_equal_profile_means' if p == 'GLOBAL' else 'conditional_means'
        b = row['observed_means']['water_l']
        old = row['methods']['original_distance'][key]['water_l']
        low = row['methods']['minimum_water_bound'][key]['water_l']
        n = row['planned_runs']
        ncw = row['methods']['reference_NCW']['available_runs']
        ncwd = row['methods']['reference_NCWD']['available_runs']
        lines.append(f'{p} & {b:.1f} & {old:.1f} & {low:.1f} & {100*(low/b-1):+.2f} & {ncw}/{n} & {ncwd}/{n}' + r' \\')
        lines.append(r'\midrule')
    lines[-1] = r'\bottomrule'
    lines.extend([r'\end{tabularx}', r'\end{table*}', ''])
    return '\n'.join(lines)


def render_readme(summary):
    rows = []
    for p in PROFILES:
        r = summary[p]
        b = r['observed_means']['water_l']
        old = r['methods']['original_distance']['conditional_means']['water_l']
        low = r['methods']['minimum_water_bound']['conditional_means']['water_l']
        rows.append(f"| {p} | {b:.1f} | {old:.1f} | {low:.1f} | {100*(low/b-1):+.2f}% | "
                    f"{r['methods']['reference_NCW']['available_runs']}/480 | "
                    f"{r['methods']['reference_NCWD']['available_runs']}/480 |")
    return '''# Reference-based compromise selection: retrospective feasibility analysis

The original `compromise` rule minimizes Euclidean distance to zero in the unpenalized normalized coordinates included in each run. It has no observed-baseline improvement constraints. Water is omitted from that distance in NC, ND and NCD. Including all four coordinates also does not ensure improvement relative to observed diets.

## Coverage and a bound on possible selection changes

| Profile | Observed W | Original W | Lowest possible mean W | Change from observed | Joint NCW fronts | Joint NCWD fronts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
''' + '\n'.join(rows) + '''

Water is in L/day. The lower bound takes the minimum-water point from each of the original 480 fronts, then averages with the same equal run weights. Every one-point-per-run selection has mean water at least this bound. F30 and M60 exceed their observed means even at this bound. This proves a limitation of post-selection on these saved fronts, not infeasibility of improved diets in the complete meal-combination space. Conditional successes must not replace all 480 runs while retaining that denominator.

## Implemented alternative

The front-restricted sensitivity function `select_reference_compromise` in `src/sec_diet/compromise_selection.py` first requires strict improvement relative to the matching observed profile means: higher capped nutrient attainment, lower carbon and lower water. `protect_departure=True` also requires lower D. A relative gain must exceed 1e-12, solely a floating-point comparison tolerance. This maximin sensitivity is separate from the final history-based, reference-constrained ideal-distance selection.

For eligible menus, the nutritional gain is `(A - observed_A)/(100 - observed_A)`. Carbon, water and optional departure gains are `(observed_value - value)/observed_value`. The rule maximizes the smallest gain, then the sum of gains, then prefers the smaller original candidate identifier. This is an explicit retrospective decision rule with equal priority to its dimensionless improvement coordinates, not a clinically validated preference model. It has no penalty-weight change and starts no optimization. If there is no eligible point it returns `None`, without a worsening fallback or another run's menu.

The observed reference uses the same sex, exact age and energy-matched days as the original comparison. Higher attainment means improvement of the capped summary score; it does not establish that all 23 criteria are met. For D, the reference is the mean of those individuals' departures from the original profile food/preparation/position mean vector. It is not the zero departure of that aggregate vector. `observed-departure-reference.json` provides every observed D outcome and the execution/input hashes. It was derived from the executed local pools with the unchanged original D function; nutrient/footprint scores were matched against the published observed outcomes before accepting a day.

## Files and interpretation

- `run-selections.csv`: every original run for every assessed rule. Missing joint-improvement choices remain explicit (`available=False`, empty candidate/outcome fields).
- `coverage-by-cell.csv`: availability and joint-improvement counts separately for every profile, objective set and algorithm; each cell retains its 20 planned runs.
- `summary.json`: observed references, all-run and conditional summaries, and per-profile/global coverage. Global means give profiles equal weight. Conditional means use only eligible runs and have a different algorithm/scenario mixture from the full campaign; they are not replacement estimates for Tables 9 and 10.
- `selected-menus.jsonl.gz`: all available NCW and NCWD reference-rule selections, with complete published food/portion lists and an explicit `selection_method`. The same menu can occur under both rules or in different runs.
- `compromise-feasibility.tex`: generated manuscript table reporting the lower bound and joint-improvement availability.
- `manifest.json`: source-release, observed-data, script, selector and output hashes.

`original_distance` recovers the saved selections; `all_four_distance` assesses including N/C/W/D in the distance. `minimum_water_bound` and `minimum_departure_bound` provide coordinate-wise bounds rather than joint-compromise recommendations. The two front-restricted reference rules have conditional coverage of 1,202/1,920 (NCW) and 635/1,920 (NCWD). The original optimization, fronts, calibration, original dietary selections and indicators remain unchanged. These conditional summaries must not be described as the Ref. rows of the main tables: [the final reference compromise](../reference-compromise-v1/README.md) uses all energy-feasible evaluated candidates, including alternatives omitted from the original final fronts.

## Reproduce using only published data

From the standalone repository:

```powershell
.venv/Scripts/python scripts/analyze_compromise_selection.py --fronts fronts/meal-profile-study-v4.1-penalty-5 --comparison comparisons/observed-profile-energy-context --departure-reference comparisons/compromise-selection-v1/observed-departure-reference.json --output results/compromise-selection-reproduction
```

To derive the observed D reference again from the completed original local campaign, replace `--departure-reference ...` with `--campaign results/meal-profile-study-v4.1-penalty-5`. The output directory must be new. [RUNNING.md](../../docs/profiles/RUNNING.md) describes complete source reconstruction and execution. The lower bounds concern only the original reporting fronts. The complete evaluated histories contain further alternatives, allowing the separate reference-constrained ideal-distance rule to provide a joint improvement in all 1,920 runs without repeating optimization. Improving all measured criteria is a different decision requirement from optimizing pairs/triples; reporting archives and complete evaluated candidate pools must be distinguished explicitly.
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fronts', type=Path, required=True)
    parser.add_argument('--comparison', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--campaign', type=Path, help='Derive observed D from the original local campaign')
    source.add_argument('--departure-reference', type=Path, help='Use the published observed-day D reference')
    args = parser.parse_args()
    summary = analyze(args.fronts, args.comparison, args.output, args.campaign, args.departure_reference)
    print(json.dumps({p: dict(observed_water=r['observed_means']['water_l'],
        reference_NCW=r['methods']['reference_NCW']['available_runs'],
        reference_NCWD=r['methods']['reference_NCWD']['available_runs']) for p, r in summary.items()}, indent=2))


if __name__ == '__main__':
    main()
