"""Compare nominal and robust policies on a fictional supply network."""
import json
import math
from .robust import SCHEMA, solve

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
    names = data["nodes"]
    idx = {name: i for i, name in enumerate(names)}
    if (any(si[idx[a]] < so[idx[b]] for b, a in data["edges"])
            or any(so[idx[n]] > cap for n, cap in data["source_service_caps"].items())):
        raise ValueError("Policy violates network or source-cap constraints")
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
