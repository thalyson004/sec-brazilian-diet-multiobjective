"""Select six complete observed meals, preserving every recorded portion."""
from __future__ import annotations
import numpy as np
from .layout import NUTRIENT_FIELDS
from .profile_targets import bounds,targets


class ProfileModel:
    def __init__(self,instance,design):
        if instance.get('schema_version')!='3.0':raise ValueError('Whole-meal instances are required; previous food-level inputs cannot be reused')
        self.instance,self.design=instance,design
        self.capped_attainment=design.get('nutrition_objective')=='capped_attainment_percent'
        self.penalty_weight=float(design.get('penalty_weight',0.))
        if not np.isfinite(self.penalty_weight) or self.penalty_weight<0:
            raise ValueError('Penalty weight must be finite and nonnegative')
        self._evaluation_cache={}
        self.profile=instance['profile'];self.instance_id=self.profile['profile_id']
        self.baseline=np.asarray(instance['baseline_g'],dtype=float)
        self.groups=np.asarray([v['food_group'] for v in instance['variables']])
        self.pools=instance['meal_pools']
        if len(self.pools)!=6 or any(not pool for pool in self.pools):raise ValueError('Six nonempty position pools are required')
        self.upper_bounds=np.asarray([len(pool)-1 for pool in self.pools],dtype=int)
        self.initial_pool=np.asarray(instance['observed_diets'],dtype=int)
        if self.initial_pool.ndim!=2 or self.initial_pool.shape[1]!=6:raise ValueError('An observed diet must have six meal indices')
        self.sampling_pool=np.unique(self.initial_pool,axis=0)
        if len(self.sampling_pool)<design['implementation']['population_size']:raise ValueError('Too few distinct observed days for matched initialization')
        self.target_rows=targets(self.profile);self.meal_limits={}
        self.energy_lower=(1-design['energy_tolerance_fraction'])*self.profile['maintenance_kcal']
        self.energy_upper=(1+design['energy_tolerance_fraction'])*self.profile['maintenance_kcal']
        self.meal_nutrients=[np.asarray([m['nutrients'] for m in pool],dtype=float) for pool in self.pools]
        self.meal_carbon=[np.asarray([m['carbon_gco2e'] for m in pool]) for pool in self.pools]
        self.meal_water=[np.asarray([m['water_l'] for m in pool]) for pool in self.pools]
        positions={(v['food_code'],v['preparation_code'],int(v['occasion_code'])):i for i,v in enumerate(instance['variables'])}
        self.meal_quantities=[]
        for slot,pool in enumerate(self.pools):
            matrix=np.zeros((len(pool),len(self.baseline)))
            for j,meal in enumerate(pool):
                for item in meal['items']:
                    if not item['tap_water']:matrix[j,positions[(item['food_code'],item['preparation_code'],slot)]]+=item['grams']
            self.meal_quantities.append(matrix)
        arrays=self.meal_nutrients+self.meal_carbon+self.meal_water+self.meal_quantities+[self.baseline]
        if any(not np.isfinite(a).all() or (a<0).any() for a in arrays):raise ValueError('Invalid meal values')
        if any(a.shape!=(len(pool),len(NUTRIENT_FIELDS)) for a,pool in zip(self.meal_nutrients,self.pools)):raise ValueError('Invalid nutrient dimensions')
        if self.baseline.sum()<=0:raise ValueError('Positive reference food mass is required')
        for x in self.initial_pool:self.indices(x)
        qmax=sum(a.max(axis=0) for a in self.meal_nutrients)
        maxima=[]
        for row in self.target_rows:
            low,high=bounds(row,self.energy_lower);amount=qmax[NUTRIENT_FIELDS.index(row['nutrient'])]
            maxima.append(max(1. if low else 0.,max(0,amount-high)/high if high else 0.))
        upper=sum(a.max(axis=0) for a in self.meal_quantities)
        dmax=np.maximum(self.baseline,np.abs(upper-self.baseline)).sum()/self.baseline.sum()
        self.normalization=np.asarray([np.mean(maxima),sum(a.max() for a in self.meal_carbon),sum(a.max() for a in self.meal_water),dmax])
        if self.capped_attainment:self.normalization[0]=100.
        if (self.normalization<=0).any():raise ValueError('Positive objective bounds are required')

    @property
    def n_var(self):return 6

    def indices(self,x):
        a=np.asarray(x)
        if a.shape!=(6,) or not np.isfinite(a).all() or not np.equal(a,np.round(a)).all() or (a<0).any() or (a>self.upper_bounds).any():
            raise ValueError('Candidate must select one valid integer meal index per position')
        return a.astype(int)

    def repair(self,vectors):
        return np.clip(np.rint(vectors),0,self.upper_bounds).astype(int)

    def nutrient_vector(self,x):
        idx=self.indices(x);return sum(a[i] for a,i in zip(self.meal_nutrients,idx))

    def quantity_vector(self,x):
        idx=self.indices(x);return sum(a[i] for a,i in zip(self.meal_quantities,idx))

    def nutrient_outcomes(self,q):
        result={}
        for row in self.target_rows:
            low,high=bounds(row,max(float(q[0]),1e-12));amount=float(q[NUTRIENT_FIELDS.index(row['nutrient'])])
            deficit=max(0,low-amount) if low is not None else 0.;excess=max(0,amount-high) if high is not None else 0.
            relative=(deficit/low if low else 0)+(excess/high if high else 0)
            tol=self.design['target_attainment_relative_tolerance']
            attained=(low is None or amount>=low*(1-tol)) and (high is None or amount<=high*(1+tol))
            lower_coverage=min(amount/low,1.) if low else 1.
            upper_compliance=min(high/amount,1.) if high and amount>0 else 1.
            result[row['nutrient']]=dict(amount=amount,lower=low,upper=high,deficit=deficit,excess=excess,
                relative_violation=relative,attainment_percent=100*min(lower_coverage,upper_compliance),
                shortfall_fraction=1-lower_coverage,attained=bool(attained))
        return result

    def evaluate(self,x):
        idx=self.indices(x);key=tuple(idx)
        if key in self._evaluation_cache:return self._evaluation_cache[key]
        q=self.nutrient_vector(idx);grams=self.quantity_vector(idx);outcomes=self.nutrient_outcomes(q)
        adequacy=float(np.mean([v['attainment_percent'] for v in outcomes.values()]))
        shortfall=float(np.mean([v['shortfall_fraction'] for v in outcomes.values() if v['lower'] is not None]))
        raw=np.asarray([adequacy if self.capped_attainment else np.mean([v['relative_violation'] for v in outcomes.values()]),
            sum(a[i] for a,i in zip(self.meal_carbon,idx)),sum(a[i] for a,i in zip(self.meal_water,idx)),
            np.abs(grams-self.baseline).sum()/self.baseline.sum()])
        constraints=[(self.energy_lower-q[0])/self.profile['maintenance_kcal'],(q[0]-self.energy_upper)/self.profile['maintenance_kcal']]
        normalized=raw/self.normalization
        if self.capped_attainment:normalized[0]=1-adequacy/100
        search=normalized.copy()
        if self.capped_attainment:search[1:]+=self.penalty_weight*shortfall
        result=dict(nutrients=dict(zip(NUTRIENT_FIELDS,map(float,q))),raw=dict(zip('NCWD',map(float,raw))),
            normalized=dict(zip('NCWD',map(float,normalized))),
            search_normalized=dict(zip('NCWD',map(float,search))),
            adequacy_percent=adequacy,shortfall_fraction=shortfall,
            constraints=list(map(float,constraints)),
            feasible=bool(max(constraints)<=1e-10),structural_violation=0.,
            attained_targets=sum(v['attained'] for v in outcomes.values()),all_targets_attained=all(v['attained'] for v in outcomes.values()))
        if len(self._evaluation_cache)<32768:self._evaluation_cache[key]=result
        return result
