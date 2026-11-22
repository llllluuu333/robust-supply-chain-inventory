"""Run the finite-scenario inventory model from a JSON file."""
import argparse
import hashlib
import json
import platform
import numpy
import scipy
from pathlib import Path
import sys
from . import __version__
from .flow import atomic_write_new
from .robust import solve

MAX_BYTES = 4 * 1024 * 1024

def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON field: " + key)
        result[key] = value
    return result

def _invalid_constant(value):
    raise ValueError("Non-finite JSON value: " + value)

def main(argv=None):
    parser = argparse.ArgumentParser(description="Solve a finite-scenario inventory model")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--time-limit", type=float, default=60.0)
    args = parser.parse_args(argv)
    try:
        if args.input.resolve() == args.output.resolve():
            raise ValueError("Input and output must differ")
        if args.input.stat().st_size > MAX_BYTES:
            raise ValueError("Input exceeds 4 MiB")
        content = args.input.read_bytes()
        if len(content) > MAX_BYTES:
            raise ValueError("Input exceeds 4 MiB")
        data = json.loads(content.decode("utf-8-sig"), object_pairs_hook=_unique,
                          parse_constant=_invalid_constant)
        result = solve(data, time_limit=args.time_limit)
        payload = {"schema_version": "inventory_lab.network.result.v1",
                   "package_version": __version__,
                   "input_sha256": hashlib.sha256(content).hexdigest(),
                   "environment": {"python": platform.python_version(),
                                   "numpy": numpy.__version__,
                                   "scipy": scipy.__version__,
                                   "time_limit_seconds": args.time_limit},
                   "result": result}
        atomic_write_new(args.output, payload)
        print(json.dumps({"output": str(args.output), "optimal": result["optimal"],
                          "objective": result["objective"], "status": result["status"]}))
        return 0 if result["optimal"] else 2
    except (ValueError, TypeError, KeyError, OSError, RuntimeError, ArithmeticError) as exc:
        print("error: " + str(exc), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
