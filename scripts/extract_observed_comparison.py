"""Extract unchanged, energy-matched POF days and compare saved compromise menus."""
from pathlib import Path
import argparse
import csv
import hashlib
import json
from collections import defaultdict
import numpy as np
from sec_diet.instances import read_json, write_json
from sec_diet.profile_inputs import build_profiles
from sec_diet.profile_model import ProfileModel
from sec_diet.english_labels import english_food, english_group
from sec_diet.publication_outputs import selected_outcomes
from sec_diet.source_checks import input_info

ROOT = Path(__file__).resolve().parents[1]
POSITIONS = ('Breakfast','Morning snack','Lunch','Afternoon snack','Dinner','Supper')
METRICS = [('energy_kcal','Energy (kcal/day)',1),
           ('attainment_percent',r'Mean nutrient attainment (\%)',2),
           ('carbon_kg',r'Carbon footprint (kg CO$_2$e/day)',2),
           ('water_l','Water footprint (L/day)',0),
           ('all_targets_attained',r'Menus attaining all 23 criteria (\%)',2)]
# Retain the existing numerical summaries without displaying the mean target count.
OUTCOME_KEYS = tuple(key for key, _, _ in METRICS) + ('attained_targets',)

def save_csv(path, rows):
    with path.open('w',encoding='utf-8',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)

def outcome(model, x):
    value=model.evaluate(x)
    return dict(energy_kcal=value['nutrients']['ENERGIA_KCAL'],
                attainment_percent=value['adequacy_percent'],attained_targets=value['attained_targets'],
                carbon_kg=value['raw']['C']/1000,water_l=value['raw']['W'],
                all_targets_attained=int(value['all_targets_attained']))

def table(summary, profiles, detailed=False):
    if not detailed:
        lines=[r'\begin{table*}[pos=h]',r'\centering\small',r'\setlength{\tabcolsep}{3pt}',
          r'\caption{Observed and optimized diets by reference profile and across profiles. Each optimized profile row uses one compromise selection per run: six objective sets $\times$ four algorithms $\times$ 20 replications $=480$ records, with equal run weights. All four profiles assume low-active physical activity. $E_{max}$ is the profile energy ceiling; $E$ is mean intake, both in kcal/day. $A$ is capped attainment (\%), C carbon (kg CO$_2$e/day), W water (L/day), and All 23 simultaneous attainment (\%). GLOBAL averages the four profile means equally and has no shared energy ceiling. Nutrient targets and meal pools differ between profiles.}',
          r'\label{tab:observed-comparison}',r'\begin{tabularx}{\textwidth}{lXrrrrrrr}',r'\toprule',
          r'Profile & Diets & $n$ & $E_{max}$ & $E$ & $A$ & C & W & All 23 \\',r'\midrule']
        for profile in profiles:
            cap='--' if profile=='GLOBAL' else f"{summary[profile]['conditions']['energy_upper_kcal']:.0f}"
            for name,label in [('observed','Observed'),('optimized','Optimized')]:
                row=summary[profile][name];v=row['means']
                lines.append(f"{profile} & {label} & {row['n']} & {cap} & {v['energy_kcal']:.1f} & {v['attainment_percent']:.2f} & {v['carbon_kg']:.2f} & {v['water_l']:.0f} & {100*v['all_targets_attained']:.2f}"+r' \\')
            lines.append(r'\midrule')
        lines[-1]=r'\bottomrule';lines.extend([r'\end{tabularx}',r'\end{table*}',''])
        return '\n'.join(lines)
    environment='table' if detailed else 'table*'
    lines=['\\begin{'+environment+'}[pos=h]',r'\centering\small',
           r'\caption{'+('Profile-specific comparison of observed days and optimized compromise selections: one menu per run across six objective sets, four algorithms and 20 replications, with equal run weights.' if detailed else
           r'Observed days and optimized compromise menus under the same profile-specific energy intervals and 23 nutrient criteria. Global means give each profile equal weight; the complete-attainment row is a percentage of menus.')+'}',
           r'\label{tab:observed-'+('profiles' if detailed else 'comparison')+'}',
           r'\begin{tabularx}{\textwidth}{Xrr}',r'\toprule',r'Indicator & Observed diets & Optimized diets \\',r'\midrule']
    for profile in profiles:
        a,b=summary[profile]['observed'],summary[profile]['optimized']
        if detailed:
            lines.append(r'\multicolumn{3}{l}{'+profile+f": {a['n']} observed days; {b['n']} optimized menus"+r'}\\')
        for key,label,decimals in METRICS:
            scale=100 if key=='all_targets_attained' else 1
            lines.append(label+f" & {a['means'][key]*scale:.{decimals}f} & {b['means'][key]*scale:.{decimals}f}"+r' \\')
            lines.append(r'\midrule')
    lines[-1]=r'\bottomrule';lines.extend([r'\end{tabularx}','\\end{'+environment+'}',''])
    return '\n'.join(lines)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pof',type=Path,required=True)
    parser.add_argument('--footprints',type=Path,required=True)
    parser.add_argument('--campaign',type=Path,help='Optional completed campaign: also compare optimized menus. Without it, extract observed diets only.')
    parser.add_argument('--profile',choices=('F30','F60','M30','M60'),action='append')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('Use a new output directory; existing comparisons are preserved')
    protocol_path=ROOT/'docs/profiles/observed-comparison-protocol.json'
    protocol=read_json(protocol_path);design=protocol['design']
    if args.campaign:
        if read_json(args.campaign/'study.json')['design']!=design:raise ValueError('Campaign differs from the released comparison protocol')
        completion=read_json(args.campaign/'completion.json')
        if completion['failures'] or completion['complete_runs']!=completion['planned_runs']:
            raise ValueError('The reference campaign is incomplete')
    catalogue=read_json(ROOT/'docs/profiles/catalogue.json')
    if catalogue['profiles']!=design['profile_definitions']:raise ValueError('Profile definitions differ from the executed study')
    cache=ROOT/'results/observed-comparison-preparation'/input_info(protocol_path)['sha256'][:12]
    print('Reconstructing the original retained POF cohort from the source archive...',flush=True)
    preparation=build_profiles(args.pof,args.footprints,catalogue,design,cache)
    profiles=args.profile or design['profiles']
    if len(set(profiles))!=len(profiles):raise ValueError('Repeated profile')
    models={};observed=[];menus=[];flow=[];source_profile={}
    for profile in profiles:
        instance=read_json(cache/(profile+'.json'))
        signature=hashlib.sha256(json.dumps(instance,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
        if signature!=protocol['instances_canonical_sha256'][profile]:
            raise ValueError('Reconstructed source cohort differs from the numerical campaign: '+profile)
        model=ProfileModel(instance,design);models[profile]=model
        used_ids=set();count=0
        for index,x in enumerate(model.initial_pool):
            value=model.evaluate(x)
            if not value['feasible']:continue
            meals=[model.pools[slot][int(j)] for slot,j in enumerate(x)]
            source_ids=set.intersection(*(set(m['source_day_ids']) for m in meals))-used_ids
            if not source_ids:raise ValueError('Cannot identify an unchanged observed source day')
            source_id=min(source_ids);used_ids.add(source_id)
            if source_id in source_profile:raise ValueError('An observed source day was assigned to multiple profiles')
            source_profile[source_id]=profile
            row=dict(profile_id=profile,observed_day_id=source_id,retained_day_index=index,**outcome(model,x))
            observed.append(row);count+=1
            # Publish quantities and identifiers, not source nutrient coefficients.
            public_meals=[]
            for slot,meal in enumerate(meals):
                public_meals.append(dict(position=POSITIONS[slot],items=[dict(food_code=i['food_code'],
                    preparation_code=i['preparation_code'],food_name=english_food(i['food_code']),
                    food_group=english_group(i['food_group']),grams=i['grams']) for i in meal['items']]))
            menus.append(dict(**row,meals=public_meals))
        if not count:raise ValueError('No energy-matched observed days for '+profile)
        flow.append(dict(profile_id=profile,age_years=model.profile['age_years'],sex_code=model.profile['sex_code'],
            physical_activity=model.profile['physical_activity'],maintenance_kcal=model.profile['maintenance_kcal'],
            retained_respondents=len(model.initial_pool),energy_lower_kcal=model.energy_lower,energy_upper_kcal=model.energy_upper,
            matched_respondents=count,excluded_energy=len(model.initial_pool)-count))
    optimized=[];optimized_menus=[]
    choices=[r for r in selected_outcomes(args.campaign) if r['selection']=='compromise' and r['profile_id'] in profiles] if args.campaign else []
    # Read each saved genotype to recover energy; all other outcomes are checked against its saved values.
    for row in choices:
        with np.load(args.campaign/'runs'/row['run_id']/'front.npz',allow_pickle=False) as f:
            matches=np.flatnonzero(f['indices']==row['candidate_index'])
            if len(matches)!=1:raise ValueError('Ambiguous saved optimized selection')
            genome=f['X'][matches[0]].copy()
            values=outcome(models[row['profile_id']],genome)
        for key in values:
            if key!='energy_kcal' and not np.isclose(values[key],row[key],rtol=1e-12,atol=1e-12):
                raise ValueError('Saved optimized outcome differs on rescoring: '+key)
        model=models[row['profile_id']]
        if not model.energy_lower-1e-8<=values['energy_kcal']<=model.energy_upper+1e-8:raise ValueError('Optimized menu outside matched energy interval')
        optimized.append(dict(profile_id=row['profile_id'],run_id=row['run_id'],objective_subset=row['objective_subset'],algorithm=row['algorithm'],replicate=row['replicate'],**values))
        public_meals=[]
        for slot,j in enumerate(genome):
            meal=model.pools[slot][int(j)]
            public_meals.append(dict(position=POSITIONS[slot],items=[dict(food_code=i['food_code'],
                preparation_code=i['preparation_code'],food_name=english_food(i['food_code']),
                food_group=english_group(i['food_group']),grams=i['grams']) for i in meal['items']]))
        optimized_menus.append(dict(**optimized[-1],meal_indices=genome.tolist(),meals=public_meals))
    summary={}
    groups=[('observed',observed)]+([('optimized',optimized)] if args.campaign else [])
    for profile in profiles:
        summary[profile]=dict(conditions=dict(age_years=models[profile].profile['age_years'],
            sex_code=models[profile].profile['sex_code'],physical_activity=models[profile].profile['physical_activity'],
            maintenance_kcal=models[profile].profile['maintenance_kcal'],
            energy_lower_kcal=models[profile].energy_lower,energy_upper_kcal=models[profile].energy_upper))
        for name,rows in groups:
            cell=[r for r in rows if r['profile_id']==profile]
            if name=='optimized' and len(cell)!=len(design['objective_subsets'])*len(design['algorithms'])*design['replicates']:
                raise ValueError('Missing optimized selections')
            summary[profile][name]=dict(n=len(cell),means={k:float(np.mean([r[k] for r in cell])) for k in OUTCOME_KEYS},
                sample_sd={k:float(np.std([r[k] for r in cell],ddof=1)) for k in OUTCOME_KEYS})
    summary['GLOBAL']={name:dict(n=sum(summary[p][name]['n'] for p in profiles),
        means={k:float(np.mean([summary[p][name]['means'][k] for p in profiles])) for k in OUTCOME_KEYS}) for name,_ in groups}
    args.output.mkdir(parents=True)
    save_csv(args.output/'selection-flow.csv',flow)
    save_csv(args.output/'observed-outcomes.csv',observed)
    if optimized:save_csv(args.output/'optimized-outcomes.csv',optimized)
    for profile in profiles:write_json(args.output/(profile+'-complete-diets.json'),[m for m in menus if m['profile_id']==profile])
    if optimized_menus:
        with (args.output/'optimized-complete-diets.jsonl').open('w',encoding='utf-8',newline='\n') as stream:
            for menu in optimized_menus:stream.write(json.dumps(menu,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n')
    write_json(args.output/'comparison-summary.json',summary)
    if args.campaign:
        (args.output/'observed-comparison.tex').write_text(table(summary,profiles+['GLOBAL']),encoding='utf-8')
        (args.output/'observed-profiles.tex').write_text(table(summary,profiles,True),encoding='utf-8')
    write_json(args.output/'manifest.json',dict(rule='Original retained respondent/day cohort, then hard-energy filter; no rescaling or nutrient/footprint selection; equal-profile global means',
        matched_profiles=profiles,design=design,source_hashes=preparation['sources'],
        original_execution=input_info(args.campaign/'execution.json') if args.campaign else None,
        protocol_sha256=input_info(protocol_path)['sha256'],script_sha256=input_info(Path(__file__))['sha256'],
        files={p.name:input_info(p) for p in args.output.iterdir() if p.is_file()}))
    print(json.dumps(dict(selection=flow,global_means=summary['GLOBAL']),indent=2))

if __name__=='__main__':main()
