"""Finite strength/density selection on constant objective coordinates."""
import unittest
import numpy as np
from pymoo.core.population import Population
from pymoo.algorithms.moo.spea2 import SPEA2Survival
from sec_diet.stable_spea2 import StableSPEA2Survival


class SPEA2StabilityChecks(unittest.TestCase):
    def test_constant_coordinates_have_finite_internal_fitness(self):
        for F in (np.ones((12,2)),np.column_stack((np.ones(12),np.arange(12))),
                  np.column_stack((np.ones(12),np.arange(12),np.arange(12)[::-1]))):
            pop=Population.new(F=F.astype(float))
            with np.errstate(divide='raise',invalid='raise'):
                result=StableSPEA2Survival()._do(None,pop,n_survive=6)
            self.assertEqual(len(result),6)
            self.assertTrue(np.isfinite(pop.get('SPEA_F')).all())

    def test_positive_span_matches_original_survival(self):
        rng=np.random.default_rng(91)
        F=rng.uniform(size=(30,3))
        first,second=Population.new(F=F.copy()),Population.new(F=F.copy())
        original=SPEA2Survival(normalize=True)._do(None,first,n_survive=12)
        corrected=StableSPEA2Survival()._do(None,second,n_survive=12)
        np.testing.assert_allclose(first.get('SPEA_F'),second.get('SPEA_F'))
        np.testing.assert_array_equal(original.get('F'),corrected.get('F'))
