"""Display selection and reconstruction checks using artificial saved results."""
import tempfile
import unittest
from pathlib import Path
import numpy as np
from sec_diet.instances import write_json
from sec_diet.publication_outputs import food_selection,selected_outcomes,export_publication,attainment_matrix


class PublicationSummaryChecks(unittest.TestCase):
    def test_food_ranking_uses_absolute_equal_algorithm_changes_and_excludes_plain_water(self):
        rows=[]
        for profile in ('F30','F60','M30','M60'):
            for algorithm in ('NSGA2','SPEA2','NSGA3','SMSEMOA'):
                for code,name,change in [('1','Example food',-10),('2','Coconut water',5),('3','Tap water',500),('4','Mineral water, unspecified',100)]:
                    rows.append(dict(profile_id=profile,objective_subset='N,C',algorithm=algorithm,food_code=code,food_name=name,mean_change_g=change))
        ranked,excluded=food_selection(rows)
        self.assertEqual(ranked['F30'][0]['food_code'],'1')
        self.assertEqual(ranked['F30'][0]['mean_change_g'],-10)
        self.assertEqual([r['food_code'] for r in ranked['F30']],['1','2'])
        self.assertEqual(excluded,['3','4'])

    def test_selected_indices_reconstruct_physical_units_and_target_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'article').mkdir();(root/'runs/r1').mkdir(parents=True)
            (root/'run-matrix.csv').write_text('run_id,profile_id,objective_subset,algorithm,replicate,seed\nr1,F30,"N,C",NSGA2,1,7\n',encoding='utf-8')
            (root/'article/diet-selections.csv').write_text('run_id,selection,candidate_index\nr1,compromise,1\n',encoding='utf-8')
            np.savez(root/'runs/r1/front.npz',indices=np.array([1]),raw=np.array([[80.,2000.,300.,.5]]))
            np.savez(root/'runs/r1/evaluations.npz',attained_targets=np.array([0,12]),shortfall=np.array([1.,.2]))
            row=selected_outcomes(root)[0]
            self.assertEqual(row['attainment_percent'],80.)
            self.assertEqual(row['carbon_kg'],2.)
            self.assertEqual(row['water_l'],300.)
            self.assertEqual(row['departure_percent'],50.)
            self.assertEqual(row['attained_targets'],12)
            self.assertEqual(row['all_targets_attained'],0)

    def test_partial_campaign_cannot_enter_publication(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);write_json(root/'completion.json',dict(planned_runs=2,complete_runs=1,failures=['r2']))
            with self.assertRaisesRegex(ValueError,'complete campaign'):export_publication(root)

    def test_attainment_matrix_uses_independent_menu_frequency_and_requires_every_cell(self):
        from sec_diet.profile_results import NUTRIENT_LABELS
        from sec_diet.publication_outputs import ALGORITHMS,SUBSETS
        rows=[dict(profile_id='F30',selection='compromise',nutrient=n,objective_subset=s,algorithm=a,attained=value)
              for n in NUTRIENT_LABELS for s in SUBSETS for a in ALGORITHMS for value in ('True','False')]
        matrix,labels,columns=attainment_matrix(rows,'F30',2)
        self.assertEqual(matrix.shape,(23,24))
        np.testing.assert_array_equal(matrix,np.full((23,24),.5))
        with self.assertRaisesRegex(ValueError,'Incomplete'):attainment_matrix(rows[:-1],'F30',2)


if __name__=='__main__':unittest.main()
