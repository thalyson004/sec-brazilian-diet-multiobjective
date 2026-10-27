"""Whole-meal semantics, source grouping, categorical adapters and rescoring."""
import copy
import itertools
import tempfile
import unittest
from pathlib import Path
import numpy as np
from sec_diet.instances import read_json,write_json
from sec_diet.layout import NUTRIENT_FIELDS
from sec_diet.profile_inputs import meal_slot,assemble_profile
from sec_diet.profile_model import ProfileModel
from sec_diet.profile_runner import execute_task,initial_population,run_plan,validate_run
from sec_diet.profile_pipeline import configuration
from sec_diet.profile_targets import targets

ROOT=Path(__file__).resolve().parents[1]


def controlled():
    catalogue=read_json(ROOT/'docs/profiles/catalogue.json')
    design=configuration(catalogue,18,2)
    design['profiles']=['F30'];design['implementation']['population_size']=6
    design['implementation']['offspring_per_step']={a:6 for a in design['algorithms']};design['implementation']['offspring_per_step']['SMSEMOA']=1
    design['implementation']['nsga3_das_dennis_partitions']={'2':5,'3':2}
    pools=[];variables=[]
    for slot in range(6):
        pool=[]
        for option in range(3):
            q=np.ones(len(NUTRIENT_FIELDS))*2;q[0]=300+40*option
            pool.append(dict(meal_id=f'{slot}-{option}',slot=str(slot),nutrients=q.tolist(),carbon_gco2e=100+10*option,water_l=30+option,
                items=[dict(food_code=str(slot),preparation_code='1',grams=100+20*option,food_group='Invented group',tap_water=False)]))
        pools.append(pool);variables.append(dict(food_code=str(slot),preparation_code='1',occasion_code=str(slot),food_group='Invented group'))
    observed=[list(v) for v in itertools.islice(itertools.product(range(3),repeat=6),30)]
    baseline=np.mean([[100+20*i for i in x] for x in observed],axis=0)
    instance=dict(schema_version='3.0',profile=catalogue['profiles'][0],meal_slots=['breakfast','morning_snack','lunch','afternoon_snack','dinner','supper'],meal_pools=pools,variables=variables,baseline_g=baseline.tolist(),observed_diets=observed)
    return instance,design


class WholeMealChecks(unittest.TestCase):
    def test_mapping_keeps_named_meals_and_splits_snacks(self):
        self.assertEqual([meal_slot(c,'') for c in ['1','2','4','5']],[0,2,4,5])
        self.assertEqual(meal_slot('3','11H'),1);self.assertEqual(meal_slot('3','12H'),3)
        self.assertEqual([meal_slot('6',str(h)+'H') for h in [4,9,11,14,17,21,0]],[0,1,2,3,4,5,5])
        with self.assertRaises(ValueError):meal_slot('3','')
        with self.assertRaises(ValueError):meal_slot('9','25H')

    def test_missing_positions_are_empty_and_amounts_are_not_refit(self):
        instance,design=controlled();q=np.arange(len(NUTRIENT_FIELDS),dtype=float);q[0]=400
        state=dict(items={('a','1',0):[125.,q],('b','1',2):[250.,q*2]})
        result=assemble_profile(instance['profile'],[(('synthetic',),state)],{('a','1'):'G',('b','1'):'G'},{('a','1'):(2.,3.),('b','1'):(4.,5.)})
        self.assertEqual(result['observed_diets'],[[0]*6])
        for slot in [1,3,4,5]:
            self.assertEqual(result['meal_pools'][slot][0]['items'],[])
            self.assertEqual(result['meal_pools'][slot][0]['nutrients'],[0.]*len(q))
        self.assertEqual(result['meal_pools'][0][0]['items'][0]['grams'],125.)
        np.testing.assert_array_equal(result['meal_pools'][2][0]['nutrients'],q*2)

    def test_six_indices_select_complete_meals(self):
        instance,design=controlled();model=ProfileModel(instance,design);x=np.array([0,1,2,0,1,2])
        expected=sum(np.asarray(instance['meal_pools'][s][i]['nutrients']) for s,i in enumerate(x))
        np.testing.assert_array_equal(model.nutrient_vector(x),expected)
        np.testing.assert_array_equal(model.quantity_vector(x),[100,120,140,100,120,140])
        self.assertEqual(model.n_var,6)
        for bad in [np.array([.5]*6),np.array([3]*6),np.array([-1]*6)]:
            with self.assertRaises(ValueError):model.evaluate(bad)

    def test_complete_reference_nutrient_list(self):
        instance,_=controlled();names={r['nutrient'] for r in targets(instance['profile'])}
        self.assertTrue({'CHOTOT','PTN','LIP','FIBRA','VITA_RAE','VITC','VITD','VITE','TIAMINA','RIBOFLAVINA','NIACINA','PIRIDOXAMINA','COBALAMINA','CALCIO','MAGNESIO','SODIO'}<=names)
        self.assertEqual(len(names),23)

    def test_four_algorithms_in_two_and_three_dimensions_rescore_integer_meals(self):
        instance,design=controlled();model=ProfileModel(instance,design);provenance={'controlled':True}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'instance.json';write_json(source,instance)
            for subset in ['N,C','N,C,W']:
                design['objective_subsets']=[subset]
                rows=run_plan(design)
                initial=None
                for algorithm in design['algorithms']:
                    row=next(r for r in rows if r['algorithm']==algorithm and r['replicate']==1)
                    points=initial_population(model,row,design)
                    if initial is None:initial=points
                    else:np.testing.assert_array_equal(initial,points)
                    destination=root/(subset.replace(',','-')+algorithm)
                    state=execute_task(row,design,str(source),str(destination),provenance,False)
                    self.assertEqual(state['metrics']['actual_evaluations'],18)
                    with np.load(destination/'evaluations.npz') as data:
                        self.assertEqual(data['X'].shape,(18,6));self.assertTrue(np.equal(data['X'],np.round(data['X'])).all())
                    validate_run(destination,row,design,instance,provenance)
                    state=execute_task(row,design,str(source),str(destination),provenance,True)
                    self.assertEqual(state['state'],'retained')

    def test_complete_meal_analysis_outputs_include_actual_menus_and_vector_fronts(self):
        from sec_diet.profile_results import summarize
        instance,design=controlled();catalogue=read_json(ROOT/'docs/profiles/catalogue.json')
        design['profiles']=[p['profile_id'] for p in catalogue['profiles']]
        design['objective_subsets']=['N,C','N,C,W']
        design['analysis']['permutation_draws']=99;design['analysis']['bootstrap_draws']=99
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);inputs=root/'inputs';inputs.mkdir();runs=root/'runs';rows=run_plan(design)
            for profile in catalogue['profiles']:
                current=copy.deepcopy(instance);current['profile']=profile
                for pool in current['meal_pools']:
                    for meal in pool:meal['nutrients'][0]=profile['maintenance_kcal']/6
                write_json(inputs/(profile['profile_id']+'.json'),current)
            for row in rows:
                execute_task(row,design,str(inputs/(row['profile_id']+'.json')),str(runs/row['run_id']),{'controlled':True},False)
            destination=root/'article';summarize(runs,inputs,rows,design,destination)
            from sec_diet.profile_methods import export_preparation
            export_preparation({'profiles':[{'profile_id':'F30','selected_distinct_respondents':30,'pool_sizes':[3]*6}]},destination/'methods')
            self.assertIn('F30 & 30 & 3 & 3 & 3 & 3 & 3 & 3',(destination/'methods/prepared-meal-pools.tex').read_text())
            self.assertEqual(read_json(destination/'analysis-manifest.json')['completed_runs'],64)
            menus=[__import__('json').loads(line) for line in (destination/'selected-menus.jsonl').read_text().splitlines()]
            self.assertEqual(len(menus),64*3)
            self.assertTrue(all(len(menu['meals'])==6 for menu in menus))
            self.assertTrue(list((destination/'figures').glob('pareto-2d-*.svg')))
            self.assertTrue(list((destination/'figures').glob('pareto-3d-*.pdf')))
            self.assertTrue((destination/'nutrient-outcomes.csv').is_file())
            self.assertTrue((destination/'food-group-changes.csv').is_file())
            self.assertTrue((destination/'paired-contrasts.csv').is_file())
