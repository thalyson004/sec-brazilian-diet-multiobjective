"""Fractional whole-meal relaxation of simultaneous nutrient attainment."""
import numpy as np
from scipy.optimize import linprog
from .layout import NUTRIENT_FIELDS


def feasibility_relaxation(model):
    q=np.vstack(model.meal_nutrients);energy=q[:,0];n=len(q)
    A=[-energy,energy];b=[-model.energy_lower,model.energy_upper]
    equalities=np.zeros((6,n));start=0
    for slot,pool in enumerate(model.pools):
        equalities[slot,start:start+len(pool)]=1;start+=len(pool)
    for row in model.target_rows:
        v=q[:,NUTRIENT_FIELDS.index(row['nutrient'])]
        if row['lower'] is not None:A.append(-v);b.append(-row['lower'])
        if row['upper'] is not None:A.append(v);b.append(row['upper'])
        if 'lower_energy_fraction' in row:A.append(row['lower_energy_fraction']/row['kcal_per_g']*energy-v);b.append(0.)
        if 'upper_energy_fraction' in row:A.append(v-row['upper_energy_fraction']/row['kcal_per_g']*energy);b.append(0.)
    result=linprog(np.zeros(n),A_ub=np.asarray(A),b_ub=np.asarray(b),A_eq=equalities,b_eq=np.ones(6),bounds=(0.,1.),method='highs')
    return dict(profile_id=model.instance_id,solver='scipy.optimize.linprog/highs',status=int(result.status),message=result.message,
        all_nutrient_goals_feasible_in_relaxation=bool(result.success),
        scope='One fractional convex combination of observed meals per position; all energy and nutrient inequalities. Binary selection is relaxed.',
        interpretation='Infeasibility rules out simultaneous strict target attainment by any whole-meal combination. Fractional feasibility does not prove existence of an admissible integer menu.')
