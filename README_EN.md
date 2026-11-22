# Robust Multi-Echelon Inventory Optimisation

[中文](README.md)

A research prototype for inventory placement under uncertain lead times. A finite-scenario mixed-integer programme chooses shared service times to minimise the worst-case weighted demand buffer across scenarios. An independent material-flow simulator tracks orders, inventory and backlog. It does not automatically consume the optimisation policy or prove equivalence to the guaranteed-service model.

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

Outputs are never overwritten; use a new filename on repeated runs. The robust CLI records the input SHA-256, solver status, objective, bounds, service decisions and scenario costs. Exit code 0 means optimal according to solver status and numerical tolerance checks, 2 means this check did not pass, and 1 indicates an input or runtime error. This is not an exact mathematical proof.

The fictional example has two suppliers and one assembly stage under three lead-time scenarios. Its worst-case weighted objective is approximately **4.7641**, agreeing with independent enumeration. This is a model value, not actual business cost or savings.

## Nominal versus robust decision

A second fictional two-supplier example solves a nominal and a robust model, then evaluates both fixed policies under the same scenarios:

| Policy | Nominal objective | Worst of three scenarios |
| --- | ---: | ---: |
| Nominal | 32.0711 | 40.0711 |
| Robust | 36.3137 | 38.8564 |

This example illustrates a trade-off within the specified scenarios, not actual cost savings or a guarantee of future performance. Run it with:

~~~bash
python -m inventory_lab.tradeoff_demo
~~~

## Model and inputs

For node i in scenario ω, the protection period is τᵢω = SIᵢ + Tᵢω − Sᵢ. The model minimises max_ω Σᵢ hᵢ bᵢ(τᵢω), subject to common integer service-time decisions, arc constraints, nonnegative protection periods, boundary conditions and optional source service caps.

Use [the synthetic JSON input](examples/synthetic_robust.json) as a template. The node ordering fixes the order of weights, buffer curves and each scenario's processing times. Edges must form a DAG. Processing times are nonnegative integers; curves start at zero, are nondecreasing and must cover the longest calculated horizon. Up to 32 nodes, 128 arcs and 16 scenarios are supported. Inputs are assumptions, not automatically estimated parameters. Unknown input fields are rejected; capacity constraints, transportation and shortage costs are not modelled.

## Verify

~~~bash
python -m unittest discover -s tests -v
python -m unittest discover -s examples -p test_read_flow_result.py -v
~~~

## Research scope

The [working paper](paper/主论文工作稿.md) examines a Willems case structure with separately mapped sales or order series. These sources do not describe one enterprise; evaluation periods were explored and are not blind tests. Third-party source data, case topology parameters and internal evidence files are excluded pending permission checks, so the paper's empirical results cannot be fully reproduced from this repository alone. The paper is not submission-ready.

The repository has no specified code or manuscript licence; public access does not itself grant reuse rights.
