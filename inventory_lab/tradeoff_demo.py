"""Compare nominal and robust policies on a fictional supply network."""
import json
import math
from .robust import SCHEMA, solve, _validated

def instance():
    return {
        "schema_version": SCHEMA, "time_unit": "synthetic_day",
        "nodes": ["A", "B", "M"], "edges": [["A", "M"], ["B", "M"]],
        "weights": [8, 5, 5],
        "curves": [[math.sqrt(t) for t in range(9)],
                   [math.sqrt(t) for t in range(9)],
                   [float(t) for t in range(9)]],
        "scenarios": [
            {"name": "nominal", "T": [2, 4, 3]},
            {"name": "delay_A", "T": [3, 4, 3]},
            {"name": "delay_B", "T": [2, 5, 3]}],
        "source_service_caps": {"A": 2, "B": 4}}

def replay(data, solution):
    """Evaluate fixed service times on the stated scenarios, with feasibility checks."""
    si, so = solution["SI"], solution["S"]
    names, idx, edges, parents, children, _, max_t, horizons, _ = _validated(data)
    if (not isinstance(si, list) or not isinstance(so, list)
            or len(si) != len(names) or len(so) != len(names)
            or any(type(x) is not int for x in si + so)):
        raise ValueError("Policy service times must be integer arrays matching nodes")
    if any(si[i] < 0 or si[i] > horizons[i] - max_t[i]
           or so[i] < 0 or so[i] > horizons[i] for i in range(len(names))):
        raise ValueError("Policy service times violate variable bounds")
    if (any(si[idx[x]] != 0 for x in names if not parents[x])
            or any(so[idx[x]] > data.get("terminal_service_caps", {}).get(x, 0)
                   for x in names if not children[x])
            or any(so[idx[a]] > si[idx[b]] for a, b in edges)
            or any(so[idx[n]] > cap for n, cap in data["source_service_caps"].items())
            or any(so[idx[n]] > cap for n, cap in data.get("node_service_caps", {}).items())):
        raise ValueError("Policy violates network or service-cap constraints")
    rows = []
    for scenario in data["scenarios"]:
        tau = [si[i] + t - so[i] for i, t in enumerate(scenario["T"])]
        if any(t < 0 or t >= len(data["curves"][i]) for i, t in enumerate(tau)):
            raise ValueError("Policy has invalid protection period in " + scenario["name"])
        value = math.fsum(data["weights"][i] * data["curves"][i][t]
                          for i, t in enumerate(tau))
        rows.append({"scenario": scenario["name"], "objective": value})
    return rows

def compare():
    data = instance()
    nominal_data = dict(data, scenarios=[data["scenarios"][0]])
    nominal = solve(nominal_data)
    robust = solve(data)
    if not nominal["optimal"] or not robust["optimal"]:
        raise RuntimeError("Comparison requires both models to be solver-certified optimal")
    return {"scope": "Fictional scenario comparison; objectives are not actual costs.",
            "nodes": data["nodes"],
            "nominal": {"SI": nominal["SI"], "S": nominal["S"],
                        "evaluation": replay(data, nominal)},
            "robust": {"SI": robust["SI"], "S": robust["S"],
                       "evaluation": replay(data, robust)}}

if __name__ == "__main__":
    print(json.dumps(compare(), indent=2))
