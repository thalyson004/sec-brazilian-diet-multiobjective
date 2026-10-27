"""Publication views of calibration and repeated-run food quantities."""
from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from .graphics import configure, export

ALGORITHMS=('NSGA2','SPEA2','NSGA3','SMSEMOA')
LABELS=('NSGA-II','SPEA2','NSGA-III','SMS-EMOA')
SETS=('N,C','N,W','N,D','N,C,W','N,C,D','N,W,D')
FOODS=('6303102','6300113','6803201')
NAMES=('Beans','White rice','Mango')
COLORS=('#1465a0','#db772e','#36876a')


def export_composition(rows, destination: Path, tables: Path):
    configure()
    destination.mkdir(parents=True,exist_ok=True)
    lookup={(r['profile_id'],r['objective_subset'],r['algorithm'],r['food_code']):r for r in rows}
    fig,axes=plt.subplots(2,2,figsize=(12,9),layout='constrained',sharey=True)
    for ax,algorithm,label in zip(axes.flat,ALGORITHMS,LABELS):
        for i,(food,name,color) in enumerate(zip(FOODS,NAMES,COLORS)):
            cell=[lookup.get(('F30',s,algorithm,food),{'mean_g':0.,'sd_g':0.}) for s in SETS]
            ax.errorbar(np.arange(6)+(i-1)*.2,[r['mean_g'] for r in cell],
                yerr=[r['sd_g'] for r in cell],fmt='o',capsize=3,color=color,label=name,ms=5)
        ax.set_xticks(np.arange(6),[s.replace(',','') for s in SETS])
        ax.set(xlabel='Objective set',ylabel='Daily mass (g)')
        ax.text(0,1.03,label,transform=ax.transAxes)
        ax.grid(axis='y',alpha=.18)
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='outside upper center',ncol=3,frameon=False)
    export(fig,destination/'food-type-mass-f30.pdf');plt.close(fig)
    lines=[r'\begin{table*}[t]',r'\centering\small',r'\setlength{\tabcolsep}{4pt}',
      r'\caption{Beans and white-rice daily grams in NC and ND compromise menus. Values are mean $\pm$ sample standard deviation over 20 runs; absence contributes zero. Baseline means use retained observed days. Each food code combines its preparations.}',
      r'\label{tab:composition-pairs}',r'\begin{tabular}{@{}llrrrrrr@{}}',r'\toprule',
      r' & & \multicolumn{3}{c}{Beans (g/day)} & \multicolumn{3}{c}{White rice (g/day)} \\',
      r'Profile & Algorithm & Baseline & NC & ND & Baseline & NC & ND \\',r'\midrule']
    for profile in ('F30','F60','M30','M60'):
        for algorithm,label in zip(ALGORITHMS,LABELS):
            cells=[]
            for food in FOODS[:2]:
                nc=lookup.get((profile,'N,C',algorithm,food),{'mean_g':0.,'sd_g':0.,'baseline_g':0.})
                nd=lookup.get((profile,'N,D',algorithm,food),{'mean_g':0.,'sd_g':0.})
                cells.extend([f"{nc['baseline_g']:.1f}",f"{nc['mean_g']:.1f} $\\pm$ {nc['sd_g']:.1f}",f"{nd['mean_g']:.1f} $\\pm$ {nd['sd_g']:.1f}"])
            lines.append(profile+' & '+label+' & '+' & '.join(cells)+r' \\')
        lines.append(r'\addlinespace')
    lines.extend([r'\bottomrule',r'\end{tabular}',r'\end{table*}',''])
    (tables/'composition-pairs.tex').write_text('\n'.join(lines),encoding='utf-8')


def export_calibration(selection_path: Path, destination: Path, table_path: Path):
    selection=json.loads(selection_path.read_text(encoding='utf-8'))
    rows=selection['summaries'];configure();destination.mkdir(parents=True,exist_ok=True)
    x=np.arange(len(rows));chosen=selection['selected_weight']
    fig,axes=plt.subplots(1,3,figsize=(13,4.6),layout='constrained')
    for ax,metric,label in zip(axes,('mean_adequacy_percent','mean_attained_targets','other_objective_mean'),
         ('Mean nutrient attainment (%)','Fully attained criteria (of 23)','Mean non-nutritional outcome')):
        ax.plot(x,[r[metric] for r in rows],'-o',color='#1465a0',lw=1.8)
        index=next(i for i,r in enumerate(rows) if r['weight']==chosen)
        ax.scatter([index],[rows[index][metric]],s=95,facecolors='none',edgecolors='#db772e',linewidth=2,zorder=4)
        ax.set_xticks(x,[f"{r['weight']:g}" for r in rows]);ax.set(xlabel='Penalty weight',ylabel=label)
        ax.grid(alpha=.18)
    export(fig,destination/'penalty-calibration.pdf');plt.close(fig)
    lines=[r'\begin{table}[t]',r'\centering\small',r'\caption{Reduced matched penalty study: 144 runs per weight. Attainment is capped at 100\%; count is the mean fully attained criteria. Other denotes the mean included non-nutritional normalized outcome (lower is better).}',
       r'\label{tab:penalty}',r'\begin{tabular}{@{}rrrr@{}}',r'\toprule',r'Weight & Attainment (\%) & Count & Other \\',r'\midrule']
    for r in rows:
        lines.append(f"{r['weight']:g} & {r['mean_adequacy_percent']:.2f} & {r['mean_attained_targets']:.2f} & {r['other_objective_mean']:.4f}"+r' \\')
    lines.extend([r'\bottomrule',r'\end{tabular}',r'\end{table}',''])
    table_path.parent.mkdir(parents=True,exist_ok=True);table_path.write_text('\n'.join(lines),encoding='utf-8')
