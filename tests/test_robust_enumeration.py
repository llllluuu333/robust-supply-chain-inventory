"""Compare the MILP with independent exhaustive service-time enumeration."""
import itertools
import math
import unittest

from inventory_lab.robust import SCHEMA, solve


def enumerate_optimum(data):
    """Enumerate a broad finite domain without using solver horizon logic."""
    names = data["nodes"]
    idx = {name: i for i, name in enumerate(names)}
    edges = data["edges"]
    parent = {name: set() for name in names}
    child = {name: set() for name in names}
    for a, b in edges:
        parent[b].add(a)
        child[a].add(b)

    # Sum of maximum node processing times bounds all path lengths, including
    # disconnected graphs. This deliberately does not reuse the MILP's M_i.
    max_time = [max(s["T"][i] for s in data["scenarios"]) for i in range(len(names))]
    horizon = sum(max_time)
    si_ranges = [range(horizon + 1) if parent[name] else range(1) for name in names]
    so_ranges = [
        range(min(horizon, data["source_service_caps"].get(name, horizon)) + 1)
        if child[name] else range(1) for name in names
    ]
    best = math.inf
    for si in itertools.product(*si_ranges):
        for so in itertools.product(*so_ranges):
            if any(so[idx[a]] > si[idx[b]] for a, b in edges):
                continue
            costs = []
            for scenario in data["scenarios"]:
                tau = [si[i] + scenario["T"][i] - so[i] for i in range(len(names))]
                if any(t < 0 or t >= len(data["curves"][i]) for i, t in enumerate(tau)):
                    break
                costs.append(sum(data["weights"][i] * data["curves"][i][t]
                                 for i, t in enumerate(tau)))
            if len(costs) == len(data["scenarios"]):
                best = min(best, max(costs))
    return best


def instance(nodes, edges, scenarios, weights, caps):
    return {
        "schema_version": SCHEMA,
        "time_unit": "synthetic_day",
        "nodes": nodes,
        "edges": [list(edge) for edge in edges],
        "weights": weights,
        # Different monotone nonlinear node costs exercise more than linear sums.
        "curves": [[(1.0 + i / 4) * math.sqrt(t) for t in range(16)]
                   for i in range(len(nodes))],
        "scenarios": [{"name": f"s{i}", "T": list(times)}
                      for i, times in enumerate(scenarios)],
        "source_service_caps": caps,
    }


class EnumeratedNetworkTests(unittest.TestCase):
    def test_network_shapes_and_scenarios_match_independent_enumeration(self):
        cases = [
            ("single", instance(["A"], [], [(1,), (2,)], [1.0], {})),
            ("chain", instance(["A", "B", "C"], [("A", "B"), ("B", "C")],
                               [(1, 1, 1), (2, 1, 1), (1, 2, 1)],
                               [1.0, 2.0, 1.5], {"A": 1})),
            ("merge", instance(["A", "B", "C"], [("A", "C"), ("B", "C")],
                               [(1, 1, 1), (2, 1, 1), (1, 2, 1)],
                               [1.0, 1.5, 3.0], {"A": 1, "B": 1})),
            ("branch", instance(["A", "B", "C"], [("A", "B"), ("A", "C")],
                                [(1, 1, 1), (2, 1, 1)],
                                [2.0, 1.0, 1.5], {"A": 1})),
            ("disconnected", instance(["A", "B", "C"], [("A", "B")],
                                      [(1, 1, 1), (2, 1, 1)],
                                      [1.0, 3.0, 1.5], {"A": 1})),
            ("zero_weights", instance(["A", "B"], [("A", "B")],
                                      [(1, 1), (2, 1)], [0.0, 0.0], {})),
        ]
        for label, data in cases:
            with self.subTest(case=label):
                expected = enumerate_optimum(data)
                actual = solve(data)
                self.assertTrue(actual["optimal"], actual)
                self.assertAlmostEqual(actual["recomputed_worst"], expected, places=6)
                self.assertAlmostEqual(actual["objective"], expected, places=6)
                self.assertLessEqual(actual["reconstructed_relative_gap"], 1e-7)


if __name__ == "__main__":
    unittest.main()
