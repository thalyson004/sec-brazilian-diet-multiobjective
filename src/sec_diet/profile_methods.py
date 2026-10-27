"""Export the frozen profile definitions, target table and methodological workflow."""

from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

from .graphics import configure, export
from .profile_targets import bounds, targets
from .profile_results import NUTRIENT_LABELS
from .instances import read_json


def export_literature(design: dict, destination: Path):
    """Render reviewed comparison cells and the matching present-study design."""
    register=Path(__file__).resolve().parents[2]/'docs/literature/comparison.json'
    rows=read_json(register)['rows']
    if design.get('profiles'):
        present=('Present profile study',
            'POF 2017--2018; women and men aged 30 and 60; six categorical whole-meal positions; four evolutionary algorithms.',
            'Six pairs/triples containing capped attainment of 23 nutrient criteria with calibrated shortage penalties; carbon, water and departure from profile consumption.',
            f"Matched comparison: {design['replicates']} replicates per profile/scenario/algorithm; nutritional gaps, food-group changes and actual fronts are reported from complete runs.")
    else:
        present=('Present respondent-day study',
            'POF 2017--2018; 24 observed adult respondent-days; quantity changes within each day; four evolutionary algorithms.',
            'Fiber/sodium deviation, carbon, water and departure; six pairs and four triples under quantity/energy bounds.',
            'Twenty matched replicates per instance/scenario/algorithm; indicators, dietary summaries and front attainment.')
    def tex(value):
        return value.replace('&',r'\&').replace('%',r'\%').replace('_',r'\_')
    lines=[r'\begin{tabularx}{\textwidth}{*{4}{>{\raggedright\arraybackslash}X}}',r'\toprule',
        r'Representative work & Input and method & Objectives / nutritional treatment & Evaluation scope \\',r'\midrule']
    for row in rows:
        cells=[tex(row['label'])+r' \cite{'+row['citation_key']+'}',
            tex(row['input_method']),tex(row['objectives_constraints']),tex(row['evaluation_scope'])]
        # Shorten names within the table; the section defines the algorithms.
        cells=[v.replace('nondominated sorting genetic algorithm II','NSGA-II')
                 .replace('strength Pareto evolutionary algorithm 2','SPEA2') for v in cells]
        lines.append(' & '.join(cells)+r' \\');lines.append(r'\midrule')
    lines.append(' & '.join(map(tex,present))+r' \\')
    lines.extend([r'\bottomrule',r'\end{tabularx}'])
    destination.mkdir(parents=True,exist_ok=True)
    (destination/'literature-comparison.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    if not design.get('profiles'):
        lower,upper=design['benchmark']['energy_band_relative_to_modeled_baseline']
        aspirations=design['objectives']['nutrient_aspirations']
        rows=[('Energy','kcal/day',f'${lower:g}E_b$--${upper:g}E_b$','Hard constraint','Study-defined interval'),
              ('Fiber','g/day',f"at least {aspirations['fiber_min_g_per_day']:g}",'Optimized deficit',r'\cite{who2018healthydiet}'),
              ('Sodium','mg/day',f"at most {aspirations['sodium_max_mg_per_day']:g}",'Optimized excess',r'\cite{who2018healthydiet}')]
        lines=[r'\begin{tabularx}{\textwidth}{l l X X X}',r'\toprule',r'Criterion & Unit & Rule & Enforcement & Basis \\',r'\midrule']
        for row in rows:
            lines.append(' & '.join(row)+r' \\');lines.append(r'\midrule')
        lines.extend([r'\bottomrule',r'\end{tabularx}'])
        (destination/'benchmark-targets.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def export_methods(catalogue: dict, design: dict, destination: Path):
    destination.mkdir(parents=True,exist_ok=True)
    export_literature(design,destination)
    lines=[r'\begin{tabularx}{\textwidth}{lrrrrlrX}',r'\toprule',r'Profile & Age & Height (m) & Weight (kg) & BMI & Activity & Energy (kcal/day) & Basis \\',r'\midrule']
    for p in catalogue['profiles']:
        activity=p['physical_activity'].replace('_',' ')
        lines.append(f"{p['profile_id']} & {p['age_years']} & {p['height_m']:.3f} & {p['weight_kg']:.2f} & {p['bmi_kg_m2']:.1f} & {activity} & {p['maintenance_kcal']:.1f}"+r' & \cite{'+p['height_citation_key']+','+p['bmi_citation_key']+','+p['energy_citation_key']+r'} \\')
        lines.append(r'\midrule')
    lines.extend([r'\bottomrule',r'\end{tabularx}'])
    (destination/'profile-definitions.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assumptions=[
        ('Membership','Women and men at exactly 30 and 60 years; recorded sex and age select the food records.',r'Study scenarios; survey fields \cite{ibge2020pof}.'),
        ('Health and physiology','Apparently healthy, nonsmoking, nonpregnant and nonlactating reference adults.',r'Reference-intake scope \cite{healthcanada2025vitamins,healthcanada2025elements}; no respondent diagnosis.'),
        ('Dietary pattern','Observed profile foods and preparations, with no imposed vegetarian or vegan exclusion.',r'Observed-consumption basis \cite{ibge2020pof}; conditional on source linkage.'),
        ('Height','Historical national median in sex-specific 30--34 and 55--64 age bands.',r'POF 2008--2009, Table 1.1 \cite{ibge2010anthropometry}.'),
        ('Weight and BMI',r'Weight = $24h^2$; body mass index (BMI) = 24 kg/m$^2$.',r'Study choice within adult/older-adult eutrophy intervals \cite{brasil2004sisvan}.'),
        ('Physical activity','Low active, assumed for all four profiles.',r'Common scenario choice; the equation category is defined in \cite{nases2023energy}.'),
        ('Energy goal',f"Weight maintenance; energy within {100*design['energy_tolerance_fraction']:g}"+r'\% of the calculated requirement.',r'Maintenance equations \cite{nases2023energy}; the interval is a modeling tolerance.'),
        ('Meal eligibility','Positive quantities and complete source linkage; six positions with absent meals empty.',r'Study inclusion rule, conditional on the available POF records \cite{ibge2020pof}.')]
    lines=[r'\begin{tabularx}{\textwidth}{l*{2}{>{\raggedright\arraybackslash}X}}',r'\toprule',r'Characteristic & Definition & Source or modeling rationale \\',r'\midrule']
    for characteristic,definition,basis in assumptions:
        lines.append(' & '.join((characteristic,definition,basis))+r' \\')
        lines.append(r'\midrule')
    lines.extend([r'\bottomrule',r'\end{tabularx}'])
    (destination/'profile-assumptions.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    tables=[targets(p) for p in catalogue['profiles']]
    lines=[r'\begin{tabularx}{\textwidth}{lllrrrrX}',r'\toprule',r'Nutrient & Unit & Type & F30 & F60 & M30 & M60 & Source \\',r'\midrule']
    tolerance=design['energy_tolerance_fraction']
    energy_cells=[f"{p['maintenance_kcal']*(1-tolerance):.0f}--{p['maintenance_kcal']*(1+tolerance):.0f}" for p in catalogue['profiles']]
    lines.append('Energy & kcal & Hard range & '+' & '.join(energy_cells)+r' & \cite{nases2023energy} \\')
    lines.append(r'\midrule')
    for index,row in enumerate(tables[0]):
        cells=[]
        for profile,table in zip(catalogue['profiles'],tables):
            low,high=bounds(table[index],profile['maintenance_kcal'])
            def number(value):
                return f'{value:.2f}'.rstrip('0').rstrip('.')
            if low is None:cell=r'$\leq '+number(high)+r'$'
            elif high is None:cell=r'$\geq '+number(low)+r'$'
            else:cell=number(low)+'--'+number(high)
            cells.append(cell)
        nutrient=NUTRIENT_LABELS[row['nutrient']]
        unit=row['unit'].replace('ug',r'$\mu$g').replace('mg alpha-tocopherol','mg')
        kind={'RDA and UL':'RDA/UL','RDA and AMDR':'RDA/AMDR','AMDR intersected with WHO maximum':'AMDR/WHO',
              'AI intersected with WHO minimum':'AI/WHO','WHO recommended maximum':'WHO max'}.get(row['recommendation_type'],row['recommendation_type'])
        lines.append(nutrient+' & '+unit+' & '+kind+' & '+' & '.join(cells)+r' & \cite{'+row['citation_key']+r'} \\')
        lines.append(r'\midrule')
    lines.extend([r'\bottomrule',r'\end{tabularx}'])
    (destination/'nutrient-targets.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    configure()
    fig,ax=plt.subplots(figsize=(12,12))
    ax.set(xlim=(0,12),ylim=(0,12));ax.axis('off')
    labels=[
        '1 Dietary records\nPOF 2017-2018\nExact sex and age',
        '2 Reference profiles\nHeight, BMI and activity\nMaintenance energy',
        '3 Nutrient goals\n23 capped criteria\nNC, NW, ND and triples',
        '4 Observed meals\nSix position-specific pools\nObserved whole meals',
        f'5 Penalty calibration\n6 weights / 864 reduced runs\nSelected weight {design.get("penalty_weight",0):g}',
        f'6 Evolutionary comparison\n4 algorithms / {design["replicates"]} replicates\n{design["evaluations"]:,} evaluations per run',
        '7 Fronts and complete menus\nPhysical and search coordinates\nSix recorded meal portions',
        '8 Dietary interpretation\nNutrient gaps and food grams\nIndicators / profile comparisons']
    positions=[(.4,9.7),(6.3,9.7),(6.3,6.7),(.4,6.7),(.4,3.7),(6.3,3.7),(6.3,.7),(.4,.7)]
    for text,(x,y) in zip(labels,positions):
        ax.add_patch(FancyBboxPatch((x,y),5.2,1.8,boxstyle='round,pad=.12',facecolor='#edf4fa',edgecolor='#5c83a6',linewidth=1.2))
        ax.text(x+.25,y+.9,text,va='center',ha='left',fontsize=16,linespacing=1.7,color='#17304d')
    arrows=[((5.7,10.6),(6.1,10.6)),((8.9,9.45),(8.9,8.7)),((6.1,7.6),(5.7,7.6)),
            ((3,6.45),(3,5.7)),((5.7,4.6),(6.1,4.6)),((8.9,3.45),(8.9,2.7)),((6.1,1.6),(5.7,1.6))]
    for start,end in arrows:ax.add_patch(FancyArrowPatch(start,end,arrowstyle='-|>',mutation_scale=18,color='#41566e'))
    export(fig,destination/'methodology-flow.pdf');plt.close(fig)


def export_preparation(manifest: dict, destination: Path):
    """Export the observed pool sizes from the exact prepared inputs."""
    destination.mkdir(parents=True, exist_ok=True)
    lines=[r'\begin{tabularx}{\linewidth}{@{}Xrrrrrrr@{}}',r'\toprule',
           r'Profile & Respondents & B & AM & L & PM & D & S \\',r'\midrule']
    for profile in manifest['profiles']:
        values=[profile['profile_id'],profile['selected_distinct_respondents'],*profile['pool_sizes']]
        lines.extend([' & '.join(map(str,values))+r' \\',r'\midrule'])
    lines.extend([r'\bottomrule',r'\end{tabularx}'])
    (destination/'prepared-meal-pools.tex').write_text('\n'.join(lines)+'\n',encoding='utf-8')
