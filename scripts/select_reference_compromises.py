"""Select joint improvements from complete saved evaluation histories."""
from pathlib import Path
from collections import defaultdict
import argparse, csv, gzip, hashlib, io, json
import numpy as np
from sec_diet.profile_model import ProfileModel
from sec_diet.compromise_selection import select_reference_distance
from sec_diet.english_labels import english_food, english_group
from sec_diet.publication_outputs import selected_outcomes

PROFILES=('F30','F60','M30','M60')
METRICS=('energy_kcal','attainment_percent','attained_targets','carbon_kg','water_l','departure_percent','all_targets_attained')
POSITIONS=('Breakfast','Morning snack','Lunch','Afternoon snack','Dinner','Supper')

def read(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,sort_keys=True,indent=2,ensure_ascii=False,allow_nan=False)+'\n',encoding='utf-8',newline='\n')
def rows(path):
    with path.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
def csv_write(path,data):
    with path.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(data[0]),lineterminator='\n');w.writeheader();w.writerows(data)

def export(campaign,comparison,sensitivity,output):
    if output.exists():raise ValueError('Use a new output directory')
    design=read(campaign/'study.json')['design'];completion=read(campaign/'completion.json')
    if completion['failures'] or completion['complete_runs']!=1920:raise ValueError('Complete original main campaign required')
    execution=read(campaign/'execution.json');ref=read(sensitivity/'observed-departure-reference.json')
    if sha(campaign/'execution.json')!=ref['source_execution_sha256'] or sha(comparison/'observed-outcomes.csv')!=ref['source_observed_outcomes_sha256']:
        raise ValueError('Observed references differ from the original campaign')
    dirs=[p for p in (campaign/'inputs').iterdir() if p.is_dir() and all((p/(v+'.json')).exists() for v in PROFILES)]
    if len(dirs)!=1 or sha(dirs[0]/'manifest.json')!=execution['instance_manifest_sha256']:raise ValueError('Original input pools required')
    models={p:ProfileModel(read(dirs[0]/(p+'.json')),design) for p in PROFILES}
    legacy=read(sensitivity/'summary.json');observed=read(comparison/'comparison-summary.json')
    bases={p:np.array([legacy[p]['observed_means'][k] for k in ('attainment_percent','carbon_kg','water_l','departure_percent')]) for p in PROFILES}
    selections=[];menus=[];nutrients=[];masses=defaultdict(list)
    for row in rows(campaign/'run-matrix.csv'):
        run=row['run_id'];p=row['profile_id'];model=models[p];source=campaign/'runs'/run/'evaluations.npz'
        with np.load(source,allow_pickle=False) as f:
            eligible=np.flatnonzero(np.all(f['constraints']<=1e-10,axis=1))
            raw=f['raw'][eligible];norm=f['normalized'][eligible]
            physical=raw*np.array([1,.001,1,100])
            i=select_reference_distance(physical,norm,bases[p],eligible)
            if i is None:raise ValueError('No joint-improvement choice in run '+run)
            if np.any((norm<=norm[i]).all(axis=1)&(norm<norm[i]).any(axis=1)):
                raise ValueError('Selected reference compromise is dominated in the full four-coordinate pool')
            candidate=int(eligible[i]);genome=f['X'][candidate].copy();normalized=norm[i].copy()
            saved_attained=int(f['attained_targets'][candidate]);shortfall=float(f['shortfall'][candidate])
        value=model.evaluate(genome)
        current=np.array([value['adequacy_percent'],value['raw']['C']/1000,value['raw']['W'],100*value['raw']['D']])
        if not value['feasible'] or not np.allclose(current,physical[i],rtol=1e-12,atol=1e-12) or value['attained_targets']!=saved_attained:
            raise ValueError('Selected evaluated menu differs on rescoring')
        if not np.allclose([value['normalized'][k] for k in 'NCWD'],normalized,rtol=1e-12,atol=1e-12):raise ValueError('Normalization differs')
        with np.load(campaign/'runs'/run/'front.npz',allow_pickle=False) as f:in_front=bool(candidate in f['indices'])
        gains=(bases[p]-physical)/bases[p];gains[:,0]=(physical[:,0]-bases[p][0])/(100-bases[p][0])
        record=dict(row,candidate_index=candidate,candidate_in_original_front=in_front,
            reference_eligible_candidates=int((gains>1e-12).all(axis=1).sum()),
            energy_kcal=value['nutrients']['ENERGIA_KCAL'],attainment_percent=current[0],attained_targets=saved_attained,
            carbon_kg=current[1],water_l=current[2],departure_percent=current[3],
            all_targets_attained=int(saved_attained==23),shortfall_fraction=shortfall,evaluations_sha256=sha(source))
        selections.append(record)
        meal_records=[];grams=defaultdict(float)
        for slot,j in enumerate(genome):
            meal=model.pools[slot][int(j)];items=[]
            for item in meal['items']:
                grams[item['food_code']]+=float(item['grams'])
                items.append(dict(food_code=item['food_code'],preparation_code=item['preparation_code'],
                    food_name=english_food(item['food_code']),food_group=english_group(item['food_group']),
                    grams=item['grams'],tap_water=item['tap_water']))
            meal_records.append(dict(position=POSITIONS[slot],items=items))
        menus.append(dict(record,selection='reference_compromise',meal_indices=genome.tolist(),
            normalized_NCWD=normalized.tolist(),meals=meal_records))
        masses[(p,row['objective_subset'],row['algorithm'])].append(grams)
        for nutrient,v in model.nutrient_outcomes(model.nutrient_vector(genome)).items():
            unit=next(t['unit'] for t in model.target_rows if t['nutrient']==nutrient)
            nutrients.append(dict(row,candidate_index=candidate,nutrient=nutrient,unit=unit,**v))
    summary={}
    for p in PROFILES+('GLOBAL',):
        cell=[r for r in selections if p=='GLOBAL' or r['profile_id']==p]
        summary[p]=dict(n=len(cell),means={k:float(np.mean([r[k] for r in cell])) for k in METRICS},
            sample_sd={k:float(np.std([r[k] for r in cell],ddof=1)) for k in METRICS},
            all23=sum(r['all_targets_attained'] for r in cell),selected_from_original_front=sum(r['candidate_in_original_front'] for r in cell))
    old=selected_outcomes(campaign);old_summary=[]
    for p in PROFILES+('GLOBAL',):
        for q in ('nutrition_max','compromise','departure_min'):
            cell=[r for r in old if r['selection']==q and (p=='GLOBAL' or r['profile_id']==p)]
            old_summary.append(dict(profile_id=p,selection=q,n=len(cell),all23=sum(r['all_targets_attained'] for r in cell),
                attainment_percent=float(np.mean([r['attainment_percent'] for r in cell])),
                attained_targets=float(np.mean([r['attained_targets'] for r in cell]))))
    food_meta={}
    for r in rows(campaign/'interpretation/food-type-mass-summary.csv'):
        food_meta[(r['profile_id'],r['food_code'])]=(r['food_name'],r['food_group'],float(r['baseline_g']))
    food_rows=[]
    for (p,s,a),cell in sorted(masses.items()):
        if len(cell)!=20:raise ValueError('Incomplete food-mass cell')
        for (profile,code),(name,group,b) in food_meta.items():
            if profile!=p:continue
            v=np.array([m.get(code,0.) for m in cell])
            food_rows.append(dict(profile_id=p,objective_subset=s,algorithm=a,selection='reference_compromise',
                food_code=code,food_name=name,food_group=group,replicates=20,present_replicates=int(np.count_nonzero(v)),
                mean_g=float(v.mean()),sd_g=float(v.std(ddof=1)),baseline_g=b,mean_change_g=float(v.mean()-b)))
    output.mkdir(parents=True)
    csv_write(output/'run-selections.csv',selections);csv_write(output/'nutrient-outcomes.csv',nutrients)
    csv_write(output/'food-type-mass-summary.csv',food_rows)
    write(output/'summary.json',summary);write(output/'original-selection-summary.json',old_summary)
    with (output/'complete-menus.jsonl.gz').open('wb') as binary:
        with gzip.GzipFile(fileobj=binary,filename='',mtime=0,mode='wb') as gz:
            with io.TextIOWrapper(gz,encoding='utf-8',newline='\n') as target:
                for menu in menus:target.write(json.dumps(menu,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
    for name,text in render_tables(summary,old_summary,observed,legacy,design).items():
        (output/name).write_text(text,encoding='utf-8',newline='\n')
    (output/'README.md').write_text(render_readme(summary),encoding='utf-8',newline='\n')
    write(output/'manifest.json',dict(rule='Strict observed-mean improvement in N/C/W/D, then minimum fixed unpenalized four-coordinate ideal distance over all energy-feasible evaluated candidates, including initialization; ties use candidate ID',
        execution_sha256=sha(campaign/'execution.json'),source_observed_sha256=sha(comparison/'observed-outcomes.csv'),
        source_reference_sha256=sha(sensitivity/'observed-departure-reference.json'),
        source_interpretation_sha256=sha(campaign/'interpretation/manifest.json'),
        source_matrix_sha256=sha(campaign/'run-matrix.csv'),
        source_original_selections_sha256=sha(campaign/'article/diet-selections.csv'),
        script_sha256=sha(Path(__file__)),selector_sha256=sha(Path(__file__).resolve().parents[1]/'src/sec_diet/compromise_selection.py'),
        run_count=len(selections),food_summary_rows=len(food_rows),
        files={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(output.iterdir()) if p.is_file()}))
    return summary

def render_tables(summary,old,observed,legacy,design):
    lines=[r'\begin{table*}[pos=h]',r'\centering\small',r'\setlength{\tabcolsep}{3pt}',
        r'\caption{Observed diets, original ideal-distance selections and reference-constrained compromises (Ref.). Each optimized profile row summarizes six objective sets $\times$ four algorithms $\times$ 20 runs. Ref. uses all energy-feasible evaluated menus and requires improvement in A, C, W and D over observed profile means. Original ideal selections use the final reporting fronts. All profiles assume low-active activity. $E_{max}$ and mean energy E are kcal/day; A is capped nutrient attainment (\%), C carbon (kg CO$_2$e/day), W water (L/day), D departure (\%) and All 23 simultaneous attainment (\%). D is a relative mass distance and can exceed 100\%. GLOBAL gives profiles equal weight.}',
        r'\label{tab:observed-comparison}',r'\begin{tabularx}{\textwidth}{lXrrrrrrrr}',r'\toprule',
        r'Profile & Diets & $n$ & $E_{max}$ & E & A & C & W & D & All 23 \\',r'\midrule']
    nutrition=[r'\begin{table*}[pos=t]',r'\centering\small',r'\setlength{\tabcolsep}{3pt}',
        r'\caption{Mean nutrient attainment and complete-attainment counts under four decision rules. Each rule selects one menu from each of 480 runs per profile and 1920 for GLOBAL, with equal run and profile weights. Max N, Ideal and Min D use the original final reporting fronts; Ref. uses all energy-feasible evaluated menus with strict observed-reference improvement. $E_{max}$ is the energy ceiling (kcal/day). A is mean capped attainment (\%); All 23 counts selections attaining every criterion. All profiles assume low-active activity with different nutrient targets and meal pools.}',
        r'\label{tab:nutrition-selections}',r'\begin{tabularx}{\textwidth}{Xr*{4}{rr}}',r'\toprule',
        r'Profile & $E_{max}$ & \multicolumn{2}{c}{Max N} & \multicolumn{2}{c}{Ideal} & \multicolumn{2}{c}{Min D} & \multicolumn{2}{c}{Ref.} \\',
        r'\cmidrule(lr){3-4}\cmidrule(lr){5-6}\cmidrule(lr){7-8}\cmidrule(lr){9-10}',
        r' & & A & All 23 & A & All 23 & A & All 23 & A & All 23 \\',r'\midrule']
    lookup={(r['profile_id'],r['selection']):r for r in old}
    for p in PROFILES+('GLOBAL',):
        cap='--' if p=='GLOBAL' else f"{observed[p]['conditions']['energy_upper_kcal']:.0f}"
        for key,label in [('observed','Observed'),('optimized','Ideal'),('reference','Ref.')]:
            cell=summary[p] if key=='reference' else observed[p][key]
            v=dict(cell['means'])
            if key!='reference':
                v['departure_percent']=legacy[p]['observed_means']['departure_percent'] if key=='observed' else legacy[p]['methods']['original_distance']['conditional_equal_profile_means' if p=='GLOBAL' else 'conditional_means']['departure_percent']
            lines.append(f"{p} & {label} & {cell['n']} & {cap} & {v['energy_kcal']:.1f} & {v['attainment_percent']:.2f} & {v['carbon_kg']:.2f} & {v['water_l']:.0f} & {v['departure_percent']:.1f} & {100*v['all_targets_attained']:.2f}"+r' \\')
        lines.append(r'\midrule')
        values=[p,cap]
        for key in ('nutrition_max','compromise','departure_min','reference'):
            r=lookup[(p,key)] if key!='reference' else dict(summary[p],**summary[p]['means'])
            values.extend([f"{r['attainment_percent']:.2f}",f"{r['all23']}/{r['n']}"])
        nutrition.append(' & '.join(values)+r' \\')
        nutrition.append(r'\midrule')
    lines[-1]=r'\bottomrule';lines.extend([r'\end{tabularx}',r'\end{table*}',''])
    nutrition[-1]=r'\bottomrule';nutrition.extend([r'\end{tabularx}',r'\end{table*}',''])
    return {'observed-comparison.tex':'\n'.join(lines),'nutrition-selections.tex':'\n'.join(nutrition)}

def render_readme(summary):
    data='\n'.join(f"| {p} | {summary[p]['n']} | {summary[p]['means']['attainment_percent']:.2f} | "
        f"{summary[p]['means']['carbon_kg']:.3f} | {summary[p]['means']['water_l']:.1f} | "
        f"{summary[p]['means']['departure_percent']:.2f} |" for p in PROFILES+('GLOBAL',))
    return '''# Reference-constrained compromises from complete evaluated histories

This retrospective decision analysis uses the completed v4.1 penalty-5 campaign. It repeats no optimization and preserves the original final reporting fronts and their indicator/food analyses. It selects one reference-constrained compromise from each of the 1,920 original runs, using **all energy-feasible evaluated menus**, including initialization. This candidate pool is larger than the original final shortage-prioritized reporting front. Only 14 of the new selections occur in those original final fronts.

## Selection rule and reference

For each profile, first require higher capped nutrient attainment, lower carbon, lower water and lower departure than the matching energy-restricted observed group means. A relative gain must exceed 1e-12 for each coordinate, a floating-point tolerance. The observed days and energy bands are unchanged. D is compared with the observed mean individual-day distance to the original aggregate profile vector, not with the zero distance of that aggregate itself. These references are in [the sensitivity release](../compromise-selection-v1/observed-departure-reference.json).

Among eligible candidates, minimize Euclidean distance to zero in all four original unpenalized normalized coordinates: N is `1-A/100`, and C/W/D use the original fixed profile-pool bounds. Smaller original candidate identifier resolves exact ties. This retains the original normalization while introducing explicit reference-improvement requirements and protecting every measured coordinate. The script checks that the selected point is not dominated in four coordinates by any energy-feasible evaluated candidate in that run. It can lie outside a run's original two-/three-objective final reporting front.

If a run has no eligible menu, the selector returns no choice and the release command stops rather than fabricating a complete comparison. In this campaign every run provides a valid choice. Higher summary attainment than the observed mean does not establish complete nutritional adequacy. The new choices average 95.67% attainment, versus 97.98% for the original ideal-distance choices and 75.78% observed. None of the new reference choices meets all 23 criteria. The gain in jointly protected outcomes therefore accompanies a nutritional trade-off relative to the original choice, which must be reported.

| Profile | Selected runs | Attainment (%) | Carbon (kg CO2e/day) | Water (L/day) | Departure (%) |
| --- | ---: | ---: | ---: | ---: | ---: |
''' + data + '''

All four outcomes improve over their profile's observed means in **each individual selected menu**, not only in the profile averages. This is a comparison against reference means, not a paired intervention or a population effect. GLOBAL gives the four equally sized profiles equal weight. D is a relative mass distance and can exceed 100%; it is not a validated acceptability probability.

## Files and relation to the manuscript

- `run-selections.csv`: all 1,920 choices, metadata, candidate identifiers, energy, physical outcomes, attained-criterion counts, shortage values, eligible-pool size, membership in the original final front and SHA-256 of the original evaluation file.
- `complete-menus.jsonl.gz`: the same choices with their six original meal indices, full English food/portion lists and fixed normalized coordinates. Join by `run_id` and `candidate_index`.
- `nutrient-outcomes.csv`: all 23 nutrient outcomes per selected menu, with amounts, lower/upper targets, deficits, excesses and attainment.
- `food-type-mass-summary.csv`: food-code daily grams, means and sample SD over 20 reference choices per profile/scenario/algorithm, including zeros for absence. `baseline_g` uses the original full retained profile cohort, as in the original food analysis, rather than the smaller energy-matched comparison subset.
- `summary.json`: means, SD, sample counts and complete-attainment counts by profile and globally.
- `original-selection-summary.json`: original Max N, ideal-distance and Min D summaries, retained for the combined nutritional table.
- `observed-comparison.tex`, `nutrition-selections.tex`: current manuscript Tables 9 and 10. Ideal denotes the original front-based compromise; Ref. denotes the new complete-history reference-constrained choice. The original and new numbers must not be attributed to the same decision rule.
- `manifest.json`: source/reference, script, selector and output hashes. Original evaluation-file hashes are recorded separately for each run.

The original [1,920 final reporting fronts](../../fronts/README.md) remain published without alteration. The [front-restricted sensitivity](../compromise-selection-v1/README.md) explains why choosing only from those final fronts could not achieve joint improvement in all four outcomes for every profile. The archive distinction, rather than new optimizer execution, makes the additional choice possible.

## Reproduce

With the completed original numerical campaign and its original input pools/reconstruction locally available, run from the standalone repository:

```powershell
.venv/Scripts/python scripts/select_reference_compromises.py --campaign results/meal-profile-study-v4.1-penalty-5 --comparison comparisons/observed-profile-energy-context --sensitivity comparisons/compromise-selection-v1 --output results/reference-compromise-reproduction
```

Use a new output directory. The script rescores every selected genotype with the original model and checks its outcomes, energy feasibility and saved nutrient count before publishing it. Copy the two generated table files to a manuscript checkout when updating Tables 9 and 10. [RUNNING.md](../../docs/profiles/RUNNING.md) describes reconstructing and executing the original study. The published choice/food/nutrient files can be inspected without the private source pools; independently obtained source data are needed to reconstruct the complete histories and rescore nutrients. Food-level source nutrient coefficients and full evaluation histories are not included in this release.
'''

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('campaign','comparison','sensitivity','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    result=export(args.campaign,args.comparison,args.sensitivity,args.output)
    print(json.dumps(result,indent=2))
