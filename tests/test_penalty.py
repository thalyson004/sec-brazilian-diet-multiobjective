"""Capped attainment, effective shortage pressure and separate front archives."""
import copy
import tempfile
import unittest
from pathlib import Path
import numpy as np
from test_meals import controlled
from sec_diet.layout import NUTRIENT_FIELDS
from sec_diet.profile_model import ProfileModel
from sec_diet.profile_runner import execute_task, run_plan
from sec_diet.instances import write_json


class PenaltyChecks(unittest.TestCase):
    def test_lower_attainment_caps_at_one_without_penalizing_safe_surplus(self):
        instance, design = controlled()
        model = ProfileModel(instance, design)
        q = np.ones(len(NUTRIENT_FIELDS))
        q[0] = instance["profile"]["maintenance_kcal"]
        vitamin = NUTRIENT_FIELDS.index("VITC")
        for amount, expected in [(37.5, 50), (60, 80), (75, 100), (112.5, 100)]:
            q[vitamin] = amount
            outcome = model.nutrient_outcomes(q)["VITC"]
            self.assertAlmostEqual(outcome["attainment_percent"], expected)
            self.assertAlmostEqual(outcome["shortfall_fraction"], 1-expected/100)
        q[vitamin] = 3000
        self.assertAlmostEqual(model.nutrient_outcomes(q)["VITC"]["attainment_percent"], 2000/3000*100)

    def test_upper_only_goals_reward_remaining_below_the_limit(self):
        instance, design = controlled()
        model = ProfileModel(instance, design)
        q = np.ones(len(NUTRIENT_FIELDS))
        q[0] = instance["profile"]["maintenance_kcal"]
        sodium = NUTRIENT_FIELDS.index("SODIO")
        for amount, expected in [(0, 100), (1000, 100), (2000, 100), (4000, 50)]:
            q[sodium] = amount
            self.assertAlmostEqual(model.nutrient_outcomes(q)["SODIO"]["attainment_percent"], expected)

    def test_weight_changes_search_coordinates_after_normalization(self):
        instance, design = controlled()
        unpenalized = ProfileModel(instance, design).evaluate([1]*6)
        design["penalty_weight"] = 25.
        design["penalty_enabled"] = True
        penalized = ProfileModel(instance, design).evaluate([1]*6)
        self.assertEqual(unpenalized["raw"], penalized["raw"])
        self.assertEqual(unpenalized["normalized"], penalized["normalized"])
        self.assertEqual(penalized["search_normalized"]["N"], penalized["normalized"]["N"])
        for objective in "CWD":
            self.assertAlmostEqual(penalized["search_normalized"][objective] - penalized["normalized"][objective],
                                   25*penalized["shortfall_fraction"])
        self.assertGreater(penalized["shortfall_fraction"], 0)

    def test_penalized_adapter_files_recompute_for_all_algorithms(self):
        instance, design = controlled()
        design["penalty_weight"] = 10.
        design["penalty_enabled"] = True
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_json(root/"instance.json", instance)
            for subset in ["N,C", "N,C,D"]:
                design["objective_subsets"] = [subset]
                for row in [r for r in run_plan(design) if r["replicate"] == 1]:
                    directory = root/(subset.replace(",","-")+row["algorithm"])
                    state = execute_task(row, design, str(root/"instance.json"), str(directory), {"test":True}, False)
                    self.assertTrue(state["metrics"]["complete"])
                    with np.load(directory/"evaluations.npz") as data:
                        self.assertTrue(np.all(data["search"][:,1:] >= data["normalized"][:,1:]))
                        self.assertTrue(np.any(data["search"][:,1:] > data["normalized"][:,1:]))
                    self.assertTrue((directory/"search-front.npz").exists())
