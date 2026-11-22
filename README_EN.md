# Robust Multi-Echelon Inventory Optimisation

[中文](README.md)

A research prototype for inventory placement under uncertain lead times. A finite-scenario mixed-integer programme chooses shared service times to minimise the worst-case weighted demand buffer across scenarios. An independent material-flow simulator tracks orders, inventory and backlog.

**Python · SciPy / HiGHS · mixed-integer optimisation · simulation**

## Try it

Requires Python 3.10 or later.

~~~bash
python -m pip install .
python -m inventory_lab.robust_demo
python -m inventory_lab.robust_cli --input examples/synthetic_robust.json --output outputs/robust_result.json
python -m inventory_lab.flow_demo --output outputs/flow_demo.json
python examples/read_flow_result.py --input outputs/flow_demo.json
~~~

Outputs are never overwritten; use a new filename on repeated runs. The robust CLI records the input SHA-256, solver status, objective, bounds, service decisions and scenario costs. Exit code 0 means certified optimal, 2 means not certified optimal, and 1 indicates an input or runtime error.

The fictional example has two suppliers and one assembly stage under three lead-time scenarios. Its worst-case weighted objective is approximately **4.7641**, agreeing with independent enumeration. This is a model value, not actual business cost or savings.

## Model and inputs

For node i in scenario ω, the protection period is τᵢω = SIᵢ + Tᵢω − Sᵢ. The model minimises max_ω Σᵢ hᵢ bᵢ(τᵢω), subject to common integer service-time decisions, arc constraints, nonnegative protection periods, boundary conditions and optional source service caps.

Use [the synthetic JSON input](examples/synthetic_robust.json) as a template. The node ordering fixes the order of weights, buffer curves and each scenario's processing times. Edges must form a DAG. Processing times are nonnegative integers; curves start at zero, are nondecreasing and must cover the longest calculated horizon. Up to 32 nodes, 128 arcs and 16 scenarios are supported. Inputs are assumptions, not automatically estimated parameters.

## Verify

~~~bash
python -m unittest discover -s tests -v
python -m unittest discover -s examples -p test_read_flow_result.py -v
~~~

## Research scope

The [working paper](paper/主论文工作稿.md) examines a Willems case structure with separately mapped sales or order series. These sources do not describe one enterprise; evaluation periods were explored and are not blind tests. Third-party source data, case topology parameters and internal evidence files are excluded pending permission checks, so the paper's empirical results cannot be fully reproduced from this repository alone. The paper is not submission-ready.

The repository has no specified code or manuscript licence; public access does not itself grant reuse rights.
