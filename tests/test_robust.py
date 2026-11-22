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

    def test_terminal_service_cap_changes_optimum_and_defaults_to_zero(self):
        d={"schema_version": "inventory_lab.network.robust.v1",
           "time_unit": "synthetic_day", "nodes": ["customer"], "edges": [],
           "weights": [1], "curves": [[0, 1, 2]],
           "scenarios": [{"name": "base", "T": [2]}], "source_service_caps": {}}
        default = solve(d)
        self.assertEqual(default["S"], [0])
        self.assertAlmostEqual(default["objective"], 2.0)
        d["terminal_service_caps"] = {"customer": 1}
        bounded = solve(d)
        self.assertEqual(bounded["S"], [1])
        self.assertAlmostEqual(bounded["objective"], 1.0)
        d["terminal_service_caps"] = {"customer": 2}
        relaxed = solve(d)
        self.assertEqual(relaxed["S"], [2])
        self.assertAlmostEqual(relaxed["objective"], 0.0)

    def test_terminal_service_cap_rejects_nonterminal_and_invalid(self):
        d=example();d["terminal_service_caps"]={"A": 1}
        with self.assertRaisesRegex(InputError, "Terminal service caps"): validate(d)
        d["terminal_service_caps"]={"M": -1}
        with self.assertRaisesRegex(InputError, "Terminal service caps"): validate(d)
        d["terminal_service_caps"]={"M": True}
        with self.assertRaisesRegex(InputError, "Terminal service caps"): validate(d)

    def test_node_cap_constrains_intermediate_node(self):
        d={"schema_version": "inventory_lab.network.robust.v1",
           "time_unit": "synthetic_day", "nodes": ["A","B","C"],
           "edges": [["A","B"],["B","C"]], "weights": [10,10,1],
           "curves": [[0,1,2,3] for _ in range(3)],
           "scenarios": [{"name": "base", "T": [1,1,1]}], "source_service_caps": {}}
        self.assertAlmostEqual(solve(d)["objective"], 3)
        d["node_service_caps"]={"B": 0}
        result=solve(d)
        self.assertEqual(result["S"][1],0)
        self.assertAlmostEqual(result["objective"], 21)
        d["node_service_caps"]={"B": True}
        with self.assertRaisesRegex(InputError, "Node service caps"): validate(d)
        d["node_service_caps"]={"unknown": 1}
        with self.assertRaisesRegex(InputError, "Node service caps"): validate(d)

    def test_source_and_node_caps_use_tighter_limit(self):
        d=example()
        d["source_service_caps"]["A"]=2
        d["node_service_caps"]={"A":0}
        self.assertEqual(solve(d)["S"][0],0)

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
