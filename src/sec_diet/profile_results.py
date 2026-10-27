"""Profile and global indicators, nutrient gaps, food changes and actual fronts."""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MaxNLocator
import numpy as np
from pymoo.indicators.igd_plus import IGDPlus

from .graphics import configure, export
from .instances import read_json, write_json
from .profile_model import ProfileModel
from .profile_runner import front_indices
from .profile_targets import bounds, targets
from .source_checks import input_info
from .english_labels import english_group

COLORS = {"NSGA2": "#1465a0", "SPEA2": "#db772e", "NSGA3": "#36876a", "SMSEMOA": "#8355a6"}
LABELS = {"NSGA2": "NSGA-II", "SPEA2": "SPEA2", "NSGA3": "NSGA-III", "SMSEMOA": "SMS-EMOA"}
AXES = {"N": "Mean relative nutrient deviation", "C": "Carbon footprint (kg CO2e/day)",
        "W": "Water footprint (L/day)", "D": "Quantity departure (%)"}
NUTRIENT_LABELS={'CHOTOT':'Carbohydrate','PTN':'Protein','LIP':'Total fat','FIBRA':'Fiber','AGSAT':'Saturated fat','AGTRANS':'Trans fat',
    'SODIO':'Sodium','CALCIO':'Calcium','FERRO':'Iron','MAGNESIO':'Magnesium','FOSFORO':'Phosphorus',
    'POTASSIO':'Potassium','COBRE':'Copper','ZINCO':'Zinc','VITA_RAE':'Vitamin A (RAE)',
    'TIAMINA':'Thiamin','RIBOFLAVINA':'Riboflavin','NIACINA':'Niacin (NE)','PIRIDOXAMINA':'Vitamin B6',
    'COBALAMINA':'Vitamin B12','VITD':'Vitamin D','VITE':'Vitamin E','VITC':'Vitamin C'}


def save_csv(path: Path, rows: list[dict]):
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(dict.fromkeys(key for row in rows for key in row)))
        writer.writeheader()
        writer.writerows(rows)


def describe(values):
    a = np.asarray(values, dtype=float)
    return dict(median=float(np.median(a)), q25=float(np.quantile(a, .25)),
                q75=float(np.quantile(a, .75)), minimum=float(a.min()), maximum=float(a.max()))


def contrasts(indicators: list[dict], design: dict):
    indexed = {(r["profile_id"], r["objective_subset"], r["algorithm"], r["replicate"]): r["hypervolume"] for r in indicators}
    result = []
    for scope in design["profiles"] + ["GLOBAL"]:
        for subset in design["objective_subsets"]:
            for first, second in itertools.combinations(design["algorithms"], 2):
                differences = []
                for replicate in range(1, design["replicates"]+1):
                    profiles = design["profiles"] if scope == "GLOBAL" else [scope]
                    differences.append(np.mean([indexed[(p, subset, first, replicate)] - indexed[(p, subset, second, replicate)] for p in profiles]))
                d = np.asarray(differences)
                seed = int(hashlib.sha256(f"{scope}|{subset}|{first}|{second}".encode()).hexdigest()[:8], 16)
                rng = np.random.default_rng(seed)
                observed, extreme = abs(d.mean()), 0
                count = design["analysis"]["permutation_draws"]
                for start in range(0, count, 1000):
                    signs = rng.choice([-1., 1.], size=(min(1000, count-start), len(d)))
                    extreme += int(np.sum(np.abs((signs*d).mean(axis=1)) >= observed-1e-15))
                means = d[rng.integers(0, len(d), size=(design["analysis"]["bootstrap_draws"], len(d)))].mean(axis=1)
                result.append(dict(profile_id=scope, objective_subset=subset, first=first, second=second,
                    mean_hv_difference=float(d.mean()), ci95_lower=float(np.quantile(means, .025)),
                    ci95_upper=float(np.quantile(means, .975)), p_value=(extreme+1)/(count+1),
                    p_holm=None, paired_replicates=len(d)))
    order = np.argsort([r["p_value"] for r in result])
    adjusted = 0.
    for rank, i in enumerate(order):
        adjusted = max(adjusted, min(1., (len(result)-rank)*result[i]["p_value"]))
        result[i]["p_holm"] = adjusted
    return result


def scaled_front(front):
    values = front.copy()
    values[:, 1] /= 1000
    values[:, 3] *= 100
    return values


def export_front_rows(figure, axes, destination: Path, *, legend=None):
    """Export vector panel rows without resampling or changing the plotted data.

    Both rows retain one common horizontal extent and the original axis limits.
    A repeated legend makes each two-profile strip independently readable.
    """
    from matplotlib.transforms import Bbox

    # Freeze the layout before taking renderer bounds or replacing the legend.
    figure.canvas.draw()
    figure.set_layout_engine(None)
    for item in list(figure.legends):
        item.remove()
    renderer = figure.canvas.get_renderer()
    boxes = [Bbox.union([ax.get_tightbbox(renderer) for ax in row]) for row in axes]
    left = min(box.x0 for box in boxes)
    right = max(box.x1 for box in boxes)
    for index, box in enumerate(boxes, 1):
        # The crop can extend into the neighboring row's label area. Hide that
        # row while drawing so no unrelated tick labels enter the strip.
        active = set(axes[index - 1])
        for ax in figure.axes:
            ax.set_visible(ax in active)
        artists = []
        if legend is not None:
            handles, labels = legend
            anchor = figure.transFigure.inverted().transform(((left + right) / 2, box.y1 + 12))
            item = figure.legend(handles, labels, loc="lower center", bbox_to_anchor=anchor,
                                 ncol=4, frameon=False, borderaxespad=0)
            figure.canvas.draw()
            artists.append(item)
            box = Bbox.union([box, item.get_window_extent(renderer)])
        crop = Bbox.from_extents(left - 10, box.y0 - 10, right + 10, box.y1 + 10)
        export(figure, destination.with_name(f"{destination.stem}-row-{index}.pdf"),
               bbox_inches=crop.transformed(figure.dpi_scale_trans.inverted()))
        for item in artists:
            item.remove()
    for ax in figure.axes:
        ax.set_visible(True)


def plot_fronts(representative: dict, design: dict, destination: Path):
    configure()
    markers = {"NSGA2": "o", "SPEA2": "s", "NSGA3": "^", "SMSEMOA": "D"}
    for subset in design["objective_subsets"]:
        names = subset.split(",")
        columns = ["NCWD".index(n) for n in names]
        if len(names) == 2:
            fig, axes = plt.subplots(2, 2, figsize=(12, 10), layout="constrained")
            nonempty = [scaled_front(representative[(p,subset,a)]["raw"]) for p in design["profiles"] for a in design["algorithms"]
                        if len(representative[(p,subset,a)]["raw"])]
            shared = np.vstack(nonempty) if nonempty else np.zeros((1,4))
            limits = [(float(shared[:,j].min()),float(shared[:,j].max())) for j in columns]
            for ax, profile in zip(axes.flat, design["profiles"]):
                for algorithm in design["algorithms"]:
                    values = scaled_front(representative[(profile, subset, algorithm)]["raw"])
                    order=np.argsort(values[:,columns[0]])
                    ax.plot(values[order,columns[0]],values[order,columns[1]],color=COLORS[algorithm],lw=1.4,alpha=.8)
                    ax.scatter(values[:, columns[0]], values[:, columns[1]], s=22, marker=markers[algorithm],
                               color=COLORS[algorithm], alpha=.75, label=LABELS[algorithm])
                ax.set(xlabel=AXES[names[0]], ylabel=AXES[names[1]])
                for setter,(low,high) in zip((ax.set_xlim,ax.set_ylim),limits):
                    pad=max((high-low)*.04,1e-5);setter(low-pad,high+pad)
                ax.text(0, 1.04, profile, transform=ax.transAxes)
                ax.grid(alpha=.18)
            handles, labels = axes[0,0].get_legend_handles_labels()
            fig.legend(handles, labels, loc="outside upper center", ncol=4, frameon=False)
            export(fig, destination/f"pareto-2d-{subset.replace(',', '-')}.pdf")
            export_front_rows(fig, axes, destination/f"pareto-2d-{subset.replace(',', '-')}.pdf",
                              legend=(handles, labels))
            plt.close(fig)
        else:
            for profile in design["profiles"]:
                fig = plt.figure(figsize=(13, 11))
                all_values = [scaled_front(representative[(profile, subset, a)]["raw"]) for a in design["algorithms"]]
                available = np.vstack([v for v in all_values if len(v)]) if any(len(v) for v in all_values) else np.zeros((1,4))
                limits = [(float(available[:,j].min()), float(available[:,j].max())) for j in columns]
                for index, algorithm in enumerate(design["algorithms"], 1):
                    values = all_values[index-1]
                    ax = fig.add_subplot(2,2,index, projection="3d")
                    if len(values)>=3:
                        _, unique = np.unique(values[:,columns[:2]],axis=0,return_index=True)
                        mesh_values=values[np.sort(unique)]
                        xy=mesh_values[:,columns[:2]]
                        if np.linalg.matrix_rank(xy-xy.mean(axis=0))>=2:
                            import matplotlib.tri as mtri
                            triangulation=mtri.Triangulation(xy[:,0],xy[:,1])
                            span=np.maximum(np.ptp(xy,axis=0),1e-12)
                            edges=xy[triangulation.triangles]/span
                            gaps=np.max(np.linalg.norm(edges-np.roll(edges,1,axis=1),axis=2),axis=1)
                            distances=np.linalg.norm((xy[:,None,:]-xy[None,:,:])/span,axis=2)
                            np.fill_diagonal(distances,np.inf)
                            spacing=float(np.median(distances.min(axis=1)))
                            triangulation.set_mask(gaps>max(.90,2*spacing))
                            if np.any(~triangulation.mask):
                                ax.plot_trisurf(triangulation,mesh_values[:,columns[2]],color=COLORS[algorithm],
                                    alpha=.32,linewidth=.5,edgecolor=COLORS[algorithm],shade=False)
                    ax.scatter(values[:, columns[0]], values[:, columns[1]], values[:, columns[2]],
                               s=22, color=COLORS[algorithm], marker=markers[algorithm], depthshade=False)
                    short_axes={"N":"Attainment (%)","C":"Carbon (kg CO2e/day)","W":"Water (L/day)","D":"Departure (%)"}
                    ax.set(xlabel=short_axes[names[0]], ylabel=short_axes[names[1]], zlabel=short_axes[names[2]])
                    for setter, (low, high) in zip((ax.set_xlim, ax.set_ylim, ax.set_zlim), limits):
                        pad = max((high-low)*.04, 1e-5)
                        setter(low-pad, high+pad)
                    ax.view_init(32, -55)
                    for axis in (ax.xaxis,ax.yaxis,ax.zaxis):
                        axis.set_major_locator(MaxNLocator(nbins=4))
                        axis.labelpad=10
                    ax.set_box_aspect((1, 1, .85), zoom=.90)
                    ax.tick_params(labelsize=16)
                    ax.text2D(.5, 1.02, LABELS[algorithm], transform=ax.transAxes, ha="center")
                fig.subplots_adjust(left=.02, right=.98, bottom=.08, top=.93, hspace=.15, wspace=.10)
                export(fig, destination/f"pareto-3d-{profile.lower()}-{subset.replace(',', '-')}.pdf")
                export_front_rows(fig, np.array(fig.axes).reshape(2, 2),
                                  destination/f"pareto-3d-{profile.lower()}-{subset.replace(',', '-')}.pdf")
                plt.close(fig)
                fig, axes = plt.subplots(1,3, figsize=(14,5.5), layout="constrained")
                for ax, pair in zip(axes, itertools.combinations(columns, 2)):
                    for algorithm, values in zip(design["algorithms"], all_values):
                        projected=values[:,list(pair)].copy()
                        if pair[0]==0 and design.get('nutrition_objective')=='capped_attainment_percent':projected[:,0]*=-1
                        envelope=values[front_indices(projected)]
                        order=np.argsort(envelope[:,pair[0]])
                        ax.plot(envelope[order,pair[0]],envelope[order,pair[1]],color=COLORS[algorithm],lw=1.5,alpha=.8)
                        ax.scatter(values[:, pair[0]], values[:, pair[1]], s=20, color=COLORS[algorithm],
                                   marker=markers[algorithm], alpha=.75, label=LABELS[algorithm])
                    ax.set(xlabel=AXES["NCWD"[pair[0]]], ylabel=AXES["NCWD"[pair[1]]])
                    ax.grid(alpha=.18)
                handles, labels = axes[0].get_legend_handles_labels()
                fig.legend(handles, labels, loc="outside upper center", ncol=4, frameon=False)
                export(fig, destination/f"pareto-projections-{profile.lower()}-{subset.replace(',', '-')}.pdf")
                plt.close(fig)


def summarize(run_root: Path, instance_root: Path, rows: list[dict], design: dict, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    AXES["N"]="Nutrient attainment (%)" if design.get("nutrition_objective")=="capped_attainment_percent" else "Mean relative nutrient deviation"
    models = {p: ProfileModel(read_json(instance_root/f"{p}.json"), design) for p in design["profiles"]}
    fronts, indicators, nutrient_rows, group_rows, choices, attainment = {}, [], [], [], [], []
    selected_menus=[]
    for row in rows:
        directory = run_root/row["run_id"]
        metrics = read_json(directory/"metrics.json")
        if not metrics["complete"]:
            raise ValueError("A partial run cannot enter the completed-study analysis")
        with np.load(directory/"front.npz", allow_pickle=False) as data:
            front = {k:data[k].copy() for k in ("indices", "X", "raw", "normalized")}
        fronts[row["run_id"]] = front
        indicators.append(dict(**row, hypervolume=metrics["hypervolume"], igd_plus=None,
            wall_seconds=metrics["wall_seconds"], front_size=len(front["X"]),
            feasible_evaluations=metrics["feasible_evaluations"], evaluations=metrics["actual_evaluations"]))
        model = models[row["profile_id"]]
        if not len(front["X"]):
            choices.append(dict(**row, selection="empty_front", candidate_index=None))
            for target in model.target_rows:
                attainment.append(dict(**row, nutrient=target["nutrient"], front_size=0, attained_fraction=0.))
            continue
        outcomes = [model.nutrient_outcomes(model.nutrient_vector(x)) for x in front["X"]]
        for target in model.target_rows:
            nutrient = target["nutrient"]
            attainment.append(dict(**row, nutrient=nutrient, front_size=len(outcomes),
                attained_fraction=float(np.mean([q[nutrient]["attained"] for q in outcomes]))))
        columns = ["NCWD".index(n) for n in row["objective_subset"].split(",")]
        nbest = int(np.lexsort((front["normalized"][:,3], front["normalized"][:,2],
                               front["normalized"][:,1], front["normalized"][:,0]))[0])
        selected = {("nutrition_max" if model.capped_attainment else "nutrition_min"): nbest,
                    "compromise": int(np.argmin(np.linalg.norm(front["normalized"][:,columns], axis=1))),
                    "departure_min": int(np.argmin(front["raw"][:,3]))}
        baseline_mass = model.baseline.sum()
        for selection, index in selected.items():
            x = front["X"][index]
            choices.append(dict(**row, selection=selection, candidate_index=int(front["indices"][index])))
            selected_menus.append(dict(**row,selection=selection,candidate_index=int(front["indices"][index]),
                meals=[dict(position=model.instance["meal_slots"][slot],**model.pools[slot][int(meal_index)]) for slot,meal_index in enumerate(x)]))
            for target in model.target_rows:
                nutrient_rows.append(dict(**row, selection=selection, nutrient=target["nutrient"], unit=target["unit"],
                                          **outcomes[index][target["nutrient"]]))
            for group in sorted(set(model.groups)):
                idx = model.groups == group
                grams = model.quantity_vector(x)
                base, final = float(model.baseline[idx].sum()), float(grams[idx].sum())
                base_share, final_share = base/baseline_mass, final/grams.sum() if grams.sum() else 0.
                group_rows.append(dict(**row, selection=selection, food_group=group, baseline_g=base, optimized_g=final,
                    change_g=final-base, relative_change_percent=100*(final-base)/base if base else None,
                    baseline_mass_share=base_share, optimized_mass_share=final_share,
                    share_change_percentage_points=100*(final_share-base_share)))
    representatives = {}
    for profile in design["profiles"]:
        for subset in design["objective_subsets"]:
            pool_rows = [r for r in indicators if r["profile_id"] == profile and r["objective_subset"] == subset]
            columns = ["NCWD".index(n) for n in subset.split(",")]
            values = [fronts[r["run_id"]]["normalized"][:,columns] for r in pool_rows if len(fronts[r["run_id"]]["X"])]
            reference = np.vstack(values) if values else np.empty((0,len(columns)))
            reference = reference[front_indices(reference)]
            np.savez_compressed(destination/f"reference-front-{profile}-{subset.replace(',', '-')}.npz", normalized=reference)
            for r in pool_rows:
                front = fronts[r["run_id"]]["normalized"][:,columns]
                r["igd_plus"] = float(IGDPlus(reference)(front)) if len(reference) and len(front) else None
            for algorithm in design["algorithms"]:
                candidates = [r for r in pool_rows if r["algorithm"] == algorithm]
                median = np.median([r["hypervolume"] for r in candidates])
                chosen = min(candidates, key=lambda r:(abs(r["hypervolume"]-median),r["run_id"]))
                representatives[(profile, subset, algorithm)] = dict(run_id=chosen["run_id"], **fronts[chosen["run_id"]])
    summaries = []
    for profile in design["profiles"] + ["GLOBAL"]:
        for subset in design["objective_subsets"]:
            for algorithm in design["algorithms"]:
                selected = [r for r in indicators if r["objective_subset"]==subset and r["algorithm"]==algorithm
                            and (profile=="GLOBAL" or r["profile_id"]==profile)]
                for metric in ("hypervolume", "igd_plus", "wall_seconds", "front_size"):
                    if profile == "GLOBAL":
                        # Equal-profile means per paired replicate, never population weighting.
                        values=[]
                        for rep in range(1,design["replicates"]+1):
                            cell=[r[metric] for r in selected if r["replicate"]==rep]
                            if all(v is not None for v in cell):values.append(float(np.mean(cell)))
                    else:values=[r[metric] for r in selected if r[metric] is not None]
                    summaries.append(dict(profile_id=profile, objective_subset=subset, algorithm=algorithm,
                        metric=metric, available_replicates=len(values), **(describe(values) if values else {k:None for k in ("median","q25","q75","minimum","maximum")})))
    with (destination/"selected-menus.jsonl").open("w",encoding="utf-8") as stream:
        for menu in selected_menus:stream.write(json.dumps(menu,allow_nan=False)+"\n")
    save_csv(destination/"run-indicators.csv", indicators)
    save_csv(destination/"indicator-summary.csv", summaries)
    save_csv(destination/"paired-contrasts.csv", contrasts(indicators,design))
    save_csv(destination/"nutrient-outcomes.csv", nutrient_rows)
    save_csv(destination/"food-group-changes.csv", group_rows)
    save_csv(destination/"nutrient-summary.csv", dietary_summary(nutrient_rows,design,"nutrient",
              ("amount","deficit","excess","relative_violation","attainment_percent","shortfall_fraction","attained")))
    save_csv(destination/"food-group-summary.csv", dietary_summary(group_rows,design,"food_group",
              ("baseline_g","optimized_g","change_g","share_change_percentage_points")))
    save_csv(destination/"front-target-attainment.csv", attainment)
    save_csv(destination/"diet-selections.csv", choices)
    save_csv(destination/"figure-run-selections.csv", [dict(profile_id=p, objective_subset=s, algorithm=a, run_id=v["run_id"])
                for (p,s,a),v in representatives.items()])
    save_csv(destination/"baseline-nutrients.csv", [dict(profile_id=p,nutrient=n,**v)
                for p,m in models.items() for n,v in m.nutrient_outcomes(np.mean([m.nutrient_vector(x) for x in m.initial_pool],axis=0)).items()])
    save_csv(destination/"nutrient-targets.csv", [dict(profile_id=p,**row, lower_at_eer=bounds(row,m.profile["maintenance_kcal"])[0],
                upper_at_eer=bounds(row,m.profile["maintenance_kcal"])[1]) for p,m in models.items() for row in m.target_rows])
    figures=destination/"figures"
    plot_fronts(representatives,design,figures)
    convergence(run_root,rows,design,destination,figures)
    plot_summaries(summaries, nutrient_rows, group_rows, design, figures, models)
    export_tables(summaries, design, destination/"tables")
    write_json(destination/"analysis-manifest.json", dict(study_id=design["study_id"],
        planned_runs=len(rows), completed_runs=len(indicators), objective_evaluations=sum(r["evaluations"] for r in indicators),
        statistical_unit="matched optimizer replicate within a fixed dietary profile; no population inference",
        global_rule="equal weight for each of the four profiles within a replicate",
        figure_rule="actual nondominated front from the run closest to its algorithm's median hypervolume; run-ID tie break",
        diet_selection_rule="maximum capped nutrient attainment; nearest unpenalized normalized origin in included objectives; departure minimum" if design.get('nutrition_objective')=='capped_attainment_percent' else "nutrition minimum; nearest normalized origin in optimized objectives; departure minimum",
        reference_rule="pooled nondominated fronts of all algorithms and replicates within the same profile and subset",
        files={str(p.relative_to(destination)):input_info(p) for p in destination.rglob('*') if p.is_file() and p.name!='analysis-manifest.json'}))


def dietary_summary(rows,design,category,metrics):
    result=[]
    indexed=defaultdict(dict)
    availability=defaultdict(set)
    for row in rows:
        key=(row['objective_subset'],row['algorithm'],row['selection'],row[category],row['replicate'])
        indexed[key][row['profile_id']]=row
        availability[(row['objective_subset'],row['algorithm'],row['selection'],row['replicate'])].add(row['profile_id'])
    families=sorted({key[:4] for key in indexed})
    for scope in design['profiles']+['GLOBAL']:
        for subset,algorithm,selection,name in families:
            for metric in metrics:
                values=[]
                for rep in range(1,design['replicates']+1):
                    cell=indexed.get((subset,algorithm,selection,name,rep),{})
                    if scope=='GLOBAL':
                        # A missing food group is a zero amount; an empty front
                        # is an unavailable dietary representative, never zero.
                        expected=design['profiles']
                        if category=='food_group':
                            available_profiles=availability[(subset,algorithm,selection,rep)]
                            if len(available_profiles)!=len(expected):continue
                            values.append(float(np.mean([cell[p][metric] if p in cell else 0. for p in expected])))
                        elif all(p in cell for p in expected):
                            values.append(float(np.mean([cell[p][metric] for p in expected])))
                    elif scope in cell:
                        values.append(float(cell[scope][metric]))
                if values:
                    result.append(dict(profile_id=scope,objective_subset=subset,algorithm=algorithm,
                        selection=selection,**{category:name},metric=metric,available_replicates=len(values),**describe(values)))
    return result


def convergence(run_root,rows,design,destination,figures):
    from pymoo.indicators.hv import HV
    checkpoints=np.unique(np.linspace(design['implementation']['population_size'],design['evaluations'],10,dtype=int))
    records=[]
    for row in rows:
        with np.load(run_root/row['run_id']/'evaluations.npz',allow_pickle=False) as data:
            values=data['normalized'];search=data['search'] if 'search' in data else values
            feasible=np.all(data['constraints']<=1e-10,axis=1)
            columns=['NCWD'.index(n) for n in row['objective_subset'].split(',')]
            for count in checkpoints:
                available=values[:count][feasible[:count]][:,columns]
                penalized=search[:count][feasible[:count]][:,columns]
                eligible=front_indices(penalized)
                front=available[eligible][front_indices(available[eligible])]
                hv=float(HV(ref_point=np.full(len(columns),1.1))(front)) if len(front) else 0.
                records.append(dict(**row,evaluation_count=int(count),hypervolume=hv))
    save_csv(destination/'convergence.csv',records)
    for subset in design['objective_subsets']:
        fig,axes=plt.subplots(2,2,figsize=(12,10),layout='constrained')
        for ax,profile in zip(axes.flat,design['profiles']):
            for algorithm in design['algorithms']:
                cells=[[r['hypervolume'] for r in records if (r['profile_id'],r['objective_subset'],r['algorithm'],r['evaluation_count'])==(profile,subset,algorithm,int(c))] for c in checkpoints]
                median=np.median(cells,axis=1);low=np.quantile(cells,.25,axis=1);high=np.quantile(cells,.75,axis=1)
                ax.plot(checkpoints,median,color=COLORS[algorithm],label=LABELS[algorithm]);ax.fill_between(checkpoints,low,high,color=COLORS[algorithm],alpha=.12)
            ax.set(xlabel='Objective-function evaluations',ylabel='Hypervolume');ax.text(0,1.04,profile,transform=ax.transAxes);ax.grid(alpha=.18)
        handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside upper center',ncol=4,frameon=False)
        export(fig,figures/f"convergence-{subset.replace(',','-')}.pdf");plt.close(fig)


def plot_summaries(summaries, nutrients, groups, design, destination, models):
    for metric,label in [("hypervolume","Hypervolume"),("igd_plus","IGD+"),("wall_seconds","Wall time (s)")]:
        fig,axes=plt.subplots(2,2,figsize=(13,10),layout="constrained")
        x=np.arange(len(design["objective_subsets"]))
        for ax,profile in zip(axes.flat,design["profiles"]):
            for index,algorithm in enumerate(design["algorithms"]):
                rows=[next(r for r in summaries if (r["profile_id"],r["objective_subset"],r["algorithm"],r["metric"])==(profile,s,algorithm,metric)) for s in design["objective_subsets"]]
                med=np.asarray([r["median"] if r["median"] is not None else np.nan for r in rows])
                lower=np.asarray([r["q25"] if r["q25"] is not None else np.nan for r in rows])
                upper=np.asarray([r["q75"] if r["q75"] is not None else np.nan for r in rows])
                ax.errorbar(x+(index-1.5)*.16,med,yerr=[med-lower,upper-med],fmt='o',color=COLORS[algorithm],label=LABELS[algorithm],capsize=3)
            ax.set_xticks(x,[s.replace(',','') for s in design["objective_subsets"]])
            ax.set_ylabel(label);ax.text(0,1.04,profile,transform=ax.transAxes);ax.grid(alpha=.18)
            if metric=="wall_seconds":ax.set_yscale('log')
        handles,labels=axes[0,0].get_legend_handles_labels();fig.legend(handles,labels,loc='outside upper center',ncol=4,frameon=False)
        export(fig,destination/f"profile-{metric.replace('_','-')}.pdf");plt.close(fig)
    # Nutrient attainment and food-group shifts of the compromise diets.
    for profile in design["profiles"]:
        names=sorted(r['nutrient'] for r in models[profile].target_rows)
        columns=[(s,a) for s in design['objective_subsets'] for a in design['algorithms']]
        matrix=np.full((len(names),len(columns)),np.nan)
        for i,n in enumerate(names):
            for j,(s,a) in enumerate(columns):
                cell=[r for r in nutrients if (r['profile_id'],r['objective_subset'],r['algorithm'],r['selection'],r['nutrient'])==(profile,s,a,'compromise',n)]
                matrix[i,j]=sum(r['attained'] for r in cell)/design['replicates']
        fig,ax=plt.subplots(figsize=(14,11),layout='constrained')
        im=ax.imshow(matrix,vmin=0,vmax=1,cmap='viridis',aspect='auto')
        ax.set_yticks(range(len(names)),[NUTRIENT_LABELS[n] for n in names]);ax.set_xticks(range(len(columns)),[s.replace(',','')+' / '+LABELS[a] for s,a in columns],rotation=65,ha='right')
        fig.colorbar(im,ax=ax,label='Fraction of planned replicates attaining target')
        export(fig,destination/f"nutrient-attainment-{profile.lower()}.pdf");plt.close(fig)
        food_names=sorted(set(models[profile].groups))
        matrix=np.full((len(food_names),len(columns)),np.nan)
        for i,g in enumerate(food_names):
            for j,(s,a) in enumerate(columns):
                cell=[r['share_change_percentage_points'] for r in groups if (r['profile_id'],r['objective_subset'],r['algorithm'],r['selection'],r['food_group'])==(profile,s,a,'compromise',g)]
                if cell:matrix[i,j]=np.median(cell)
        limit=max(float(np.nanmax(np.abs(matrix))) if np.isfinite(matrix).any() else 1.,.01)
        fig,ax=plt.subplots(figsize=(15,10),layout='constrained')
        im=ax.imshow(matrix,vmin=-limit,vmax=limit,cmap='RdBu_r',aspect='auto')
        ax.set_yticks(range(len(food_names)),[english_group(g) for g in food_names]);ax.set_xticks(range(len(columns)),[s.replace(',','')+' / '+LABELS[a] for s,a in columns],rotation=65,ha='right')
        fig.colorbar(im,ax=ax,label='Food-group mass-share change (percentage points)')
        export(fig,destination/f"food-group-change-{profile.lower()}.pdf");plt.close(fig)


def export_tables(summaries, design, destination):
    destination.mkdir(parents=True,exist_ok=True)
    for metric in ('hypervolume','igd_plus','wall_seconds'):
        lines=[r'\begin{tabularx}{\linewidth}{@{}ll*{6}{>{\raggedleft\arraybackslash}X}@{}}',r'\toprule',
               'Profile & Algorithm & '+' & '.join(s.replace(',','') for s in design['objective_subsets'])+r' \\',r'\midrule']
        for profile in design['profiles']+['GLOBAL']:
            for algorithm in design['algorithms']:
                cell=[next(r for r in summaries if (r['profile_id'],r['objective_subset'],r['algorithm'],r['metric'])==(profile,subset,algorithm,metric)) for subset in design['objective_subsets']]
                numbers=[f"{r['median']:.4g}" if r['median'] is not None else '--' for r in cell]
                lines.append(profile+' & '+LABELS[algorithm]+' & '+' & '.join(numbers)+r' \\')
            lines.append(r'\midrule')
        lines.pop()
        lines.extend([r'\bottomrule',r'\end{tabularx}'])
        (destination/(metric.replace('_','-')+'.tex')).write_text('\n'.join(lines)+'\n',encoding='utf-8')
