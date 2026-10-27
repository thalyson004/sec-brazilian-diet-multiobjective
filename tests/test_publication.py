"""English descriptions and publication exports for the revised design."""
import tempfile
import unittest
from pathlib import Path
from sec_diet.english_labels import english_food, english_group, food_labels
from sec_diet.diet_figures import export_calibration, export_composition
import numpy as np
from sec_diet.profile_results import plot_fronts, AXES

ROOT=Path(__file__).resolve().parents[1]


class PublicationChecks(unittest.TestCase):
    def test_sparse_three_dimensional_front_has_supported_transparency(self):
        profiles=['F30','F60','M30','M60'];algorithms=['NSGA2','SPEA2','NSGA3','SMSEMOA']
        raw=np.array([[90.,1000.,2000.,1.],[95.,1200.,2600.,1.5],[96.,900.,3400.,2.]])
        representatives={(p,'N,C,W',a):{'raw':raw} for p in profiles for a in algorithms}
        design=dict(profiles=profiles,algorithms=algorithms,objective_subsets=['N,C,W'],nutrition_objective='capped_attainment_percent')
        with tempfile.TemporaryDirectory() as directory:
            previous=AXES['N'];AXES['N']='Nutrient attainment (%)'
            try:plot_fronts(representatives,design,Path(directory))
            finally:AXES['N']=previous
            svg=(Path(directory)/'pareto-3d-f30-N-C-W.svg').read_text(encoding='utf-8')
            self.assertIn('fill-opacity: 0.32',svg)
            self.assertTrue((Path(directory)/'pareto-projections-f30-N-C-W.pdf').exists())

    def test_complete_reviewed_food_dictionary_and_unknown_failures(self):
        labels=food_labels()
        self.assertEqual(len(labels),701)
        self.assertTrue(all(r['source'] and r['english'] for r in labels.values()))
        self.assertEqual(english_food('6300113'),'White rice')
        self.assertEqual(english_group('cereais e leguminosas'),'Cereals and pulses')
        with self.assertRaises(ValueError):english_food('unrecognized')
        with self.assertRaises(ValueError):english_group('unrecognized')

    def test_calibration_and_mass_views_export_vector_figures(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            export_calibration(ROOT/'docs/profiles/penalty-selection.json',root,root/'penalty.tex')
            rows=[dict(profile_id='F30',objective_subset='N,C',algorithm='NSGA2',food_code='6303102',
                       baseline_g=100.,mean_g=120.,sd_g=15.)]
            export_composition(rows,root,root)
            for name in ('penalty-calibration','food-type-mass-f30'):
                self.assertTrue((root/(name+'.pdf')).read_bytes().startswith(b'%PDF-'))
                self.assertIn('<svg',(root/(name+'.svg')).read_text(encoding='utf-8'))
            self.assertIn('120.0',(root/'composition-pairs.tex').read_text(encoding='utf-8'))
