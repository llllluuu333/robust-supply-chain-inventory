"""Versioned, bounded entry point for Decimal material-flow experiments.

The model is a research simulation, not a GSM-equivalence or business system.
No actual costs, service guarantees, data fitting or optimization are inferred.
"""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import platform
import tempfile
from . import __version__
from .flow_engine import FlowSimulatorDecimal, decimal_to_jsonable

SCHEMA = 'inventory_lab.flow.v1'
MAX_NODES = 32
MAX_EDGES = 128
MAX_DAYS = 366
MAX_INPUT_BYTES = 4 * 1024 * 1024
TIME_UNITS = frozenset(('synthetic_day', 'calendar_day', 'assumed_business_day'))


def _reject_constant(value):
    raise ValueError('Non-finite JSON number is not supported: ' + value)


def _unique_object(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError('Duplicate JSON field: ' + k)
        out[k] = v
    return out


def parse_input(content):
    """Parse exact JSON number text and reject duplicates/non-finite constants."""
    if not isinstance(content, bytes) or len(content) > MAX_INPUT_BYTES:
        raise ValueError('Input must be bytes and no larger than 4 MiB')
    return json.loads(content.decode('utf-8-sig'), parse_float=Decimal,
                      parse_constant=_reject_constant, object_pairs_hook=_unique_object)


def simulate(content):
    """Parse original JSON bytes, hash those exact bytes, and run one path.

    The digest is an input identity checksum, not a digital signature.
    """
    data = parse_input(content)
    return _simulate_document(data, hashlib.sha256(content).hexdigest())


def _simulate_document(data, input_sha256):
    """Internal helper; only simulate() exposes provenance to callers."""
    if not isinstance(data, dict) or set(data) != {'schema_version', 'time_unit', 'parents', 'lead_times', 'targets', 'demands'}:
        raise ValueError('Expected the six fields in the flow.v1 input contract')
    if data['schema_version'] != SCHEMA or data['time_unit'] not in TIME_UNITS:
        raise ValueError('Unsupported flow schema or time unit')
    parents = data['parents']; demands = data['demands']
    if not isinstance(parents, dict) or not 1 <= len(parents) <= MAX_NODES:
        raise ValueError('Provide 1 to 32 stages')
    if any(not isinstance(n, str) or not n.strip() or len(n) > 80 for n in parents):
        raise ValueError('Stage names must be nonempty and at most 80 characters')
    if any(not isinstance(p, list) for p in parents.values()) or sum(map(len, parents.values())) > MAX_EDGES:
        raise ValueError('Parent lists must contain at most 128 arcs in total')
    if not isinstance(demands, list) or not 1 <= len(demands) <= MAX_DAYS:
        raise ValueError('Provide 1 to 366 daily demand mappings')
    if not isinstance(input_sha256, str) or len(input_sha256) != 64 or any(c not in '0123456789abcdef' for c in input_sha256):
        raise ValueError('Input SHA-256 must be a lowercase hexadecimal digest')
    simulator = FlowSimulatorDecimal(parents, data['lead_times'], data['targets'])
    for daily in demands:
        simulator.step(daily)
    payload = {'schema_version': 'inventory_lab.flow.result.v1',
               'package_version': __version__, 'input_sha256': input_sha256,
               'python_version': platform.python_version(), 'time_unit': data['time_unit'],
               'precision': 'Decimal 50 significant digits; inexact arithmetic raises',
               'scope': ('Fixed targets and lead times; synthetic or user-supplied divisible units; '
                         'unit-input assembly DAG; unlimited supply and processing; zero transport time; '
                         'FIFO with partial delivery and full backlog; zero initial inventory and in-transit. '
                         'No actual costs or service guarantees, and no proof of equivalence to GSM.'),
               'days': len(simulator.trace), 'nodes': simulator.nodes,
               'daily_trace': simulator.trace}
    return decimal_to_jsonable(payload)


def atomic_write_new(path, payload):
    """Write a new JSON result without replacing an existing file."""
    path = Path(path)
    if path.exists():
        raise FileExistsError('Output already exists; choose another path')
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = None
    try:
        with tempfile.NamedTemporaryFile('w', encoding='utf8', dir=path.parent, delete=False, newline='\n') as f:
            temp = Path(f.name)
            json.dump(payload, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.link(temp, path)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()


def main(argv=None):
    parser = argparse.ArgumentParser(description='Run one bounded Decimal material-flow research scenario')
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError('Input and output must differ')
        if args.input.stat().st_size > MAX_INPUT_BYTES:
            raise ValueError('Input exceeds 4 MiB')
        content = args.input.read_bytes()
        result = simulate(content)
        atomic_write_new(args.output, result)
        print(json.dumps({'output': str(args.output), 'days': result['days'], 'input_sha256': result['input_sha256']}))
        return 0
    except (ValueError, TypeError, KeyError, OSError, RuntimeError, ArithmeticError) as exc:
        print('error: ' + str(exc), file=__import__('sys').stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
