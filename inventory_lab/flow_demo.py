"""Run a self-contained fictional assembly example without external data."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .flow import SCHEMA, atomic_write_new, simulate


def synthetic_input():
    """Invented three-stage DAG, lead times, targets and customer orders."""
    return {'schema_version': SCHEMA, 'time_unit': 'synthetic_day',
            'parents': {'Supplier_A': [], 'Supplier_B': [],
                        'Assembler': ['Supplier_A', 'Supplier_B']},
            'lead_times': {'Supplier_A': 2, 'Supplier_B': 1, 'Assembler': 0},
            'targets': {'Supplier_A': '2', 'Supplier_B': '2', 'Assembler': '1'},
            'demands': [{'Assembler': q} for q in ('1', '0.25', '0', '0.25', '1', '0', '0.5', '0')]}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run a fictional material-flow example')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        data = synthetic_input()
        content = json.dumps(data, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf8')
        result = simulate(content)
        result['demo_input'] = data
        result['demo_input_serialization'] = 'UTF-8 JSON; sorted keys; comma/colon separators without spaces'
        atomic_write_new(args.output, result)
        print(json.dumps({'output': str(args.output), 'days': result['days'],
                          'scope': 'Invented example only; no real business data.'}))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RuntimeError, ArithmeticError) as exc:
        print('error: ' + str(exc), file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
