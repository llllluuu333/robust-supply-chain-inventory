import itertools
import math
import unittest
from inventory_lab.robust import InputError, solve, validate
from inventory_lab.robust_demo import example

class RobustTests(unittest.TestCase):
    def test_against_enumeration(self):
        d=example()
        r=solve(d)
        self.assertTrue(r["optimal"])
        best=math.inf
        for sa,sb,sim in itertools.product(range(3),range(2),range(5)):
            if sa>sim or sb>sim:
                continue
            costs=[]
            for scenario in d["scenarios"]:
                ta,tb,tm=scenario["T"]
                tau=[ta-sa,tb-sb,sim+tm]
                if min(tau)<0 or max(tau)>=8:
                    break
                costs.append(sum(w*c[t] for w,c,t in zip(d["weights"],d["curves"],tau)))
            if len(costs)==len(d["scenarios"]):
                best=min(best,max(costs))
        self.assertAlmostEqual(r["recomputed_worst"],best,places=6)

    def test_reject_unsupported_model_and_scenario_fields(self):
        d=example();d["capacity_constraints"]={"A": 0}
        with self.assertRaisesRegex(InputError, "Unsupported input fields"): validate(d)
        d=example();d["scenarios"][0]["delay_uncertainty"]=2
        with self.assertRaisesRegex(InputError, "Scenario must contain"): validate(d)

    def test_reject_cycle(self):
        d=example();d["edges"].append(["M","A"])
        with self.assertRaises(InputError): validate(d)

    def test_reject_unknown_endpoint(self):
        d=example();d["edges"].append(["unknown","M"])
        with self.assertRaises(InputError): validate(d)

    def test_reject_cap_at_non_source(self):
        d=example();d["source_service_caps"]["M"]=1
        with self.assertRaises(InputError): validate(d)

    def test_reject_duplicate_nodes_and_edges(self):
        d=example();d["nodes"].append("A")
        with self.assertRaises(InputError): validate(d)

if __name__=="__main__": unittest.main()
