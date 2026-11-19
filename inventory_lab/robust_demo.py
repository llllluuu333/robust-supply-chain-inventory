"""Solve an invented finite-scenario network without third-party data."""
import json
import math
from .robust import SCHEMA, solve

def example():
    return {
        "schema_version": SCHEMA, "time_unit": "synthetic_day",
        "nodes": ["A", "B", "M"],
        "edges": [["A", "M"], ["B", "M"]],
        "weights": [1.0, 1.3, 2.0],
        "curves": [[math.sqrt(t) for t in range(8)] for _ in range(3)],
        "scenarios": [
            {"name": "nominal", "T": [2, 1, 1]},
            {"name": "delay_A", "T": [3, 1, 1]},
            {"name": "delay_B", "T": [2, 2, 1]},
        ],
        "source_service_caps": {"A": 2, "B": 1},
    }

if __name__ == "__main__":
    print(json.dumps(solve(example()), ensure_ascii=False, indent=2))
