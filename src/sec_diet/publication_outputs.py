"""Publication summaries from saved meal-study results, without new optimization."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
import csv,hashlib,json,re
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from sec_diet.graphics import configure,export
from sec_diet.instances import read_json,write_json

PROFILES=('F30','F60','M30','M60')
ALGORITHMS=('NSGA2','SPEA2','NSGA3','SMSEMOA')
LABELS=('NSGA-II','SPEA2','NSGA-III','SMS-EMOA')
SUBSETS=('N,C','N,W','N,D','N,C,W','N,C,D','N,W,D')
SELECTIONS=('nutrition_max','compromise','departure_min')

def read_csv(path):
    with path.open(encoding='utf-8',newline='') as stream:return list(csv.DictReader(stream))

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def escaped(value):
    return str(value).replace('&',r'\&').replace('%',r'\%').replace('_',r'\_')

def selected_outcomes(campaign):
    """One record per run and selection rule; repeated menus retain run weights."""
    choices=read_csv(campaign/'article/diet-selections.csv')
    matrix={r['run_id']:r for r in read_csv(campaign/'run-matrix.csv')}
    grouped=defaultdict(list)
    for choice in choices:grouped[choice['run_id']].append(choice)
    result=[]
    for run_id,selected in grouped.items():
        directory=campaign/'runs'/run_id
        with np.load(directory/'front.npz',allow_pickle=False) as f:
            indices=f['indices'];raw=f['raw'];lookup={int(index):i for i,index in enumerate(indices)}
        with np.load(directory/'evaluations.npz',allow_pickle=False) as e:
            attained=e['attained_targets'];shortfall=e['shortfall']
        for choice in selected:
            index=int(choice['candidate_index']);v=raw[lookup[index]]
            result.append(dict(**matrix[run_id],selection=choice['selection'],candidate_index=index,
                attainment_percent=float(v[0]),carbon_kg=float(v[1])/1000,water_l=float(v[2]),departure_percent=float(v[3])*100,
                attained_targets=int(attained[index]),all_targets_attained=int(attained[index]==23),shortfall_fraction=float(shortfall[index])))
    return result

def food_selection(rows):
    """Rank absolute NC mean changes, averaging the four algorithm means equally."""
    scores=defaultdict(list);metadata={}
    excluded=[]
    for r in rows:
        if r['objective_subset']!='N,C':continue
        key=(r['profile_id'],r['food_code']);name=r['food_name']
        if name=='Tap water' or name.lower().startswith('mineral water') or name.lower().startswith('drinking water'):
            excluded.append(r['food_code']);continue
        scores[key].append(float(r['mean_change_g']));metadata[key]=name
    ranked={}
    for profile in PROFILES:
        candidates=[dict(food_code=code,food_name=metadata[(p,code)],mean_change_g=float(np.mean(a))) for (p,code),a in scores.items() if p==profile]
        ranked[profile]=sorted(candidates,key=lambda r:(-abs(r['mean_change_g']),r['food_code']))
    return ranked,sorted(set(excluded))

def attainment_matrix(rows,profile,replicates):
    from .profile_results import NUTRIENT_LABELS
    indexed=defaultdict(list)
    for row in rows:
        if row['profile_id']==profile and row['selection']=='compromise':
            indexed[(row['nutrient'],row['objective_subset'],row['algorithm'])].append(str(row['attained']).lower()=='true')
    columns=[(subset,algorithm) for subset in SUBSETS for algorithm in ALGORITHMS]
    matrix=[]
    for nutrient in NUTRIENT_LABELS:
        values=[]
        for subset,algorithm in columns:
            cell=indexed[(nutrient,subset,algorithm)]
            if len(cell)!=replicates:raise ValueError('Incomplete criterion-attainment display cell')
            values.append(float(np.mean(cell)))
        matrix.append(values)
    return np.array(matrix),list(NUTRIENT_LABELS.values()),columns

def export_publication(campaign:Path,destination:Path|None=None):
    completion=read_json(campaign/'completion.json')
    if completion['complete_runs']!=completion['planned_runs'] or completion['failures']:raise ValueError('A complete campaign is required')
    design=read_json(campaign/'study.json')['design']
    if design['nutrition_objective']!='capped_attainment_percent':raise ValueError('Capped-attainment results are required')
    if tuple(design['profiles'])!=PROFILES or tuple(design['objective_subsets'])!=SUBSETS:
        raise ValueError('The registered four profiles and six objective sets are required')
    expected=len(PROFILES)*len(SUBSETS)*len(ALGORITHMS)*design['replicates']
    if completion['planned_runs']!=expected:raise ValueError('The campaign count differs from the registered design')
    destination=destination or campaign/'publication'
    tables=destination/'tables';figures=destination/'figures';tables.mkdir(parents=True,exist_ok=True);figures.mkdir(parents=True,exist_ok=True)
    from .profile_results import plot_fronts,AXES,export_tables
    indicators = read_csv(campaign / 'article/indicator-summary.csv')
    for row in indicators:
        row['median'] = float(row['median']) if row['median'] else None
    export_tables(indicators, design, tables)
    representatives={}
    for row in read_csv(campaign/'article/figure-run-selections.csv'):
        with np.load(campaign/'runs'/row['run_id']/'front.npz',allow_pickle=False) as front:
            representatives[(row['profile_id'],row['objective_subset'],row['algorithm'])]={'raw':front['raw'].copy()}
    AXES['N']='Nutrient attainment (%)'
    plot_fronts(representatives,design,figures)
    nutrient_rows=read_csv(campaign/'article/nutrient-outcomes.csv')
    configure()
    with plt.rc_context({'font.size':18,'axes.labelsize':18,'xtick.labelsize':18,'ytick.labelsize':18}):
        for profile in PROFILES:
            matrix,nutrient_labels,columns=attainment_matrix(nutrient_rows,profile,design['replicates'])
            fig,ax=plt.subplots(figsize=(14,11),layout='constrained')
            im=ax.imshow(matrix,aspect='auto',vmin=0,vmax=1,cmap='viridis')
            names=dict(zip(ALGORITHMS,LABELS))
            ax.set_xticks(range(len(columns)),[s.replace(',','')+' / '+names[a] for s,a in columns],rotation=90)
            ax.set_yticks(range(len(nutrient_labels)),nutrient_labels)
            ax.set(xlabel='Objective set / algorithm',ylabel='Nutrient criterion')
            fig.colorbar(im,ax=ax,pad=.02,label='Fraction attaining criterion')
            export(fig,figures/('nutrient-attainment-'+profile.lower()+'.pdf'));plt.close(fig)
    outcomes=selected_outcomes(campaign)
    if len(outcomes)!=3*completion['complete_runs']:raise ValueError('Missing dietary selections')
    summary=[]
    for profile in PROFILES+('GLOBAL',):
        for selection in SELECTIONS:
            cell=[r for r in outcomes if r['selection']==selection and (profile=='GLOBAL' or r['profile_id']==profile)]
            a=np.array([[r[k] for k in ('attainment_percent','attained_targets','carbon_kg','water_l','departure_percent','shortfall_fraction')] for r in cell])
            summary.append(dict(profile_id=profile,selection=selection,n=len(cell),all23=sum(r['all_targets_attained'] for r in cell),
                means=dict(zip(('attainment_percent','attained_targets','carbon_kg','water_l','departure_percent','shortfall_fraction'),a.mean(axis=0).tolist())),
                sample_sd=dict(zip(('attainment_percent','attained_targets','carbon_kg','water_l','departure_percent','shortfall_fraction'),a.std(axis=0,ddof=1).tolist()))))
    lines=[r'\begin{table}[t]',r'\centering\small',r'\setlength{\tabcolsep}{3pt}',
        r'\caption{Nutritional outcomes by selection rule. Each rule selects one menu per run: six objective sets $\times$ four algorithms $\times$ '+str(design['replicates'])+r' replications $='+str(expected//4)+r'$ records per profile and '+str(expected)+r' for GLOBAL. Runs have equal weight regardless of front size; selected menus can repeat. GLOBAL gives profiles equal weight. $E_{max}$ is the energy ceiling (kcal/day). All profiles assume low-active activity, with different nutrient targets and meal pools. Count is the mean attained criteria; All 23 gives complete-attainment records/selected records. Max N maximizes attainment, Comp. minimizes distance to the unpenalized normalized origin in the included objectives, and Min D minimizes departure.}',
       r'\label{tab:nutrition-selections}',r'\begin{tabularx}{\columnwidth}{lXrrrr}',r'\toprule',r'Profile & Selection & $E_{max}$ & Attain. (\%) & Count & All 23 \\',r'\midrule']
    names=dict(zip(SELECTIONS,('Max N','Comp.','Min D')))
    for row in summary:
        profile=row['profile_id']
        cap='--' if profile=='GLOBAL' else f"{next(p['maintenance_kcal'] for p in design['profile_definitions'] if p['profile_id']==profile)*(1+design['energy_tolerance_fraction']):.0f}"
        means=row['means'];lines.append(f"{profile} & {names[row['selection']]} & {cap} & {means['attainment_percent']:.2f} & {means['attained_targets']:.2f} & {row['all23']}/{row['n']}"+r' \\')
        if row['selection']=='departure_min':lines.append(r'\addlinespace')
    lines.extend([r'\bottomrule',r'\end{tabularx}',r'\end{table}','']);(tables/'nutrition-selections.tex').write_text('\n'.join(lines),encoding='utf-8')
    rows=read_csv(campaign/'interpretation/food-type-mass-summary.csv');ranked,excluded=food_selection(rows)
    lookup={(r['profile_id'],r['objective_subset'],r['algorithm'],r['food_code']):r for r in rows}
    lines=[r'\begin{table*}[t]',r'\centering\small',r'\setlength{\tabcolsep}{6pt}',
        r'\caption{Largest absolute NC food-type mean change in each profile, selected by the equal-algorithm mean and excluding plain water from this display selection. Baseline is the observed-day mean. NC and ND show daily grams as mean $\pm$ sample SD over '+str(design['replicates'])+r' compromise menus per algorithm, including zeros for absence. $\Delta$ is optimized mean minus baseline; its SD equals the displayed mass SD because the baseline is fixed.}',
        r'\label{tab:dominant-food-changes}',r'\begin{tabular}{@{}lrrrrr@{}}',r'\toprule',
        r'Algorithm & Baseline (g) & NC (g/day) & ND (g/day) & $\Delta$NC (g) & $\Delta$ND (g) \\',r'\midrule']
    food_comparisons=[]
    for profile in PROFILES:
        food=ranked[profile][0];code=food['food_code']
        lines.append(r'\multicolumn{6}{l}{'+profile+': '+escaped(food['food_name'])+' ('+code+r')}\\')
        for algorithm,label in zip(ALGORITHMS,LABELS):
            nc=lookup[(profile,'N,C',algorithm,code)];nd=lookup[(profile,'N,D',algorithm,code)]
            lines.append(label+f" & {float(nc['baseline_g']):.1f} & {float(nc['mean_g']):.1f} $\\pm$ {float(nc['sd_g']):.1f} & {float(nd['mean_g']):.1f} $\\pm$ {float(nd['sd_g']):.1f} & {float(nc['mean_change_g']):+.1f} & {float(nd['mean_change_g']):+.1f}"+r' \\')
            food_comparisons.append(dict(profile_id=profile,algorithm=algorithm,food=food,nc=nc,nd=nd))
        lines.append(r'\addlinespace')
    lines.extend([r'\bottomrule',r'\end{tabular}',r'\end{table*}','']);(tables/'dominant-food-changes.tex').write_text('\n'.join(lines),encoding='utf-8')
    configure();chosen=ranked['F30'][:3]
    fig,axes=plt.subplots(2,2,figsize=(12,9),layout='constrained',sharey=True)
    colors=('#1465a0','#db772e','#36876a')
    for ax,algorithm,label in zip(axes.flat,ALGORITHMS,LABELS):
        for i,(food,color) in enumerate(zip(chosen,colors)):
            cell=[lookup[('F30',s,algorithm,food['food_code'])] for s in SUBSETS]
            ax.errorbar(np.arange(6)+(i-1)*.2,[float(r['mean_g']) for r in cell],yerr=[float(r['sd_g']) for r in cell],fmt='o',capsize=3,color=color,label=food['food_name'],ms=5)
        ax.set_xticks(np.arange(6),[s.replace(',','') for s in SUBSETS]);ax.set(xlabel='Objective set',ylabel='Daily mass (g)');ax.text(0,1.03,label,transform=ax.transAxes);ax.grid(axis='y',alpha=.18)
    handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside upper center',ncol=1,frameon=False)
    export(fig,figures/'dominant-food-types-f30.pdf');plt.close(fig)
    # One compact outcomes table per illustrative menu set, without changing foods.
    index=read_csv(campaign/'interpretation/example-menu-index.csv');examples=[]
    for item in index:
        choices=[r for r in outcomes if r['run_id']==item['run_id'] and r['candidate_index']==int(item['candidate_index']) and r['selection']=='compromise']
        if len(choices)!=1:raise ValueError('Example menu is not its recorded compromise selection')
        examples.append(dict(**choices[0],example_source=item))
    for subset in SUBSETS:
        lines=[r'\begin{center}\small',r'\begin{tabular}{@{}lrrrr@{}}',r'\toprule',r'Outcome & F30 & F60 & M30 & M60 \\',r'\midrule']
        cell={r['profile_id']:r for r in examples if r['objective_subset']==subset}
        for key,label,fmt in [('attainment_percent',r'Attainment (\%)','.2f'),('attained_targets','Attained criteria (of 23)','d'),('carbon_kg',r'Carbon (kg CO$_2$e/day)','.2f'),('water_l','Water footprint (L/day)','.0f'),('departure_percent',r'Quantity departure (\%)','.1f')]:
            lines.append(label+' & '+' & '.join(format(cell[p][key],fmt) for p in PROFILES)+r' \\')
        lines.extend([r'\bottomrule',r'\end{tabular}',r'\end{center}','']);(tables/('menu-outcomes-'+subset.replace(',','').lower()+'.tex')).write_text('\n'.join(lines),encoding='utf-8')
        source=campaign/'interpretation/tables'/('example-menu-'+subset.replace(',','').lower()+'.tex')
        menu_text=source.read_text(encoding='utf-8')
        # Earlier campaign reconstructions used a justified meal-name column.
        menu_text = menu_text.replace(r'@{}p{.075\textwidth}',
                                      r'@{}>{\raggedright\arraybackslash}p{.075\textwidth}')
        # Units and the empty-position convention appear once in the appendix
        # introduction, rather than in six nearly identical long captions.
        caption = (r'\caption{Illustrative ' + subset.replace(',', '') +
                   r' six-position menus for all four profiles, using the representative NSGA-II ideal-distance rule. '
                   r'Foods retain observed portions; outcome rows describe these exact menus.}')
        menu_text = re.sub(r'\\caption\{[^\n]*\}', lambda _: caption, menu_text, count=1)
        footer=[r'\midrule',r'\multicolumn{5}{l}{Physical outcomes of the illustrated menu}\\']
        for key,label,fmt in [('attainment_percent',r'A (\%)','.2f'),('attained_targets','Targets','d'),('carbon_kg','C (kg)','.2f'),('water_l','W (L)','.0f'),('departure_percent',r'D (\%)','.1f')]:
            footer.append(label+' & '+' & '.join(format(cell[p][key],fmt) for p in PROFILES)+r' \\')
        menu_text=menu_text.replace(r'\end{longtable}','\n'.join(footer)+'\n'+r'\end{longtable}')
        (tables/source.name).write_text(menu_text,encoding='utf-8')
    write_json(destination/'nutrition-selection-summary.json',summary)
    staple_source=campaign/'interpretation/tables/composition-pairs.tex'
    staple_text=staple_source.read_text(encoding='utf-8').replace(r'\begin{table*}[t]',r'\begin{table}[pos=htbp]').replace(r'\end{table*}',r'\end{table}')
    (tables/staple_source.name).write_text(staple_text,encoding='utf-8')
    write_json(destination/'food-display-selection.json',dict(rule='Largest absolute NC mean change relative to baseline, equal algorithm weights; post hoc descriptive display selection',ranked=ranked,excluded_plain_water_codes=excluded))
    write_json(destination/'food-display-comparisons.json',food_comparisons)
    write_json(destination/'example-menu-outcomes.json',examples)
    manifest=dict(execution=read_json(campaign/'execution.json'),completion=completion,publication_script_sha256=digest(Path(__file__)),
       renderer_sha256=digest(Path(__file__).with_name('profile_results.py')),graphics_sha256=digest(Path(__file__).with_name('graphics.py')),
       input_hashes={str(p.relative_to(campaign)):digest(p) for p in [campaign/'article/analysis-manifest.json',campaign/'interpretation/manifest.json',campaign/'article/diet-selections.csv',campaign/'interpretation/food-type-mass-summary.csv'] if p.exists()},
       selection_rows=len(outcomes),food_summary_rows=len(rows),files={str(p.relative_to(destination)):digest(p) for p in destination.rglob('*') if p.is_file() and p.name!='publication-manifest.json'})
    write_json(destination/'publication-manifest.json',manifest)
    return manifest

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--campaign',type=Path,required=True);parser.add_argument('--output',type=Path)
    args=parser.parse_args();print(json.dumps(export_publication(args.campaign,args.output),indent=2))
