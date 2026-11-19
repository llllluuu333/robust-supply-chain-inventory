"""Summarize external demand and ending state from a saved flow.v1 result.

This is a read-only, local example. A saved model output is not proof of real
business performance or data authenticity, and SHA-256 is not a signature.
"""
from __future__ import annotations
import argparse
from decimal import Decimal, InvalidOperation, localcontext
import hashlib
import json
from pathlib import Path
import sys

MAX_BYTES = 100 * 1024 * 1024


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError('Duplicate JSON field')
        obj[key] = value
    return obj


def _reject_constant(value):
    raise ValueError('Non-finite JSON number')


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float, str, Decimal)):
        raise ValueError('Expected nonnegative finite quantity')
    try:
        x = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError('Invalid decimal quantity') from exc
    if (not x.is_finite() or x < 0 or x > Decimal('1e40')
            or (x != 0 and (x.as_tuple().exponent < -60 or len(x.as_tuple().digits) > 60))):
        raise ValueError('Quantity outside supported summary range')
    return x


def summarize(content):
    if not isinstance(content, bytes) or len(content) > MAX_BYTES:
        raise ValueError('Expected a result file of at most 100 MiB')
    data = json.loads(content.decode('utf-8-sig'), parse_float=Decimal,
                      parse_constant=_reject_constant, object_pairs_hook=_unique)
    if not isinstance(data, dict) or data.get('schema_version') != 'inventory_lab.flow.result.v1':
        raise ValueError('Unsupported saved flow result')
    source_hash = data.get('input_sha256')
    if not isinstance(source_hash, str) or len(source_hash) != 64 or any(c not in '0123456789abcdef' for c in source_hash):
        raise ValueError('Invalid source input SHA-256')
    days, nodes, trace = data.get('days'), data.get('nodes'), data.get('daily_trace')
    if (type(days) is not int or not 1 <= days <= 366 or not isinstance(nodes, list)
            or not 1 <= len(nodes) <= 32 or any(not isinstance(n, str) or not n for n in nodes)
            or len(set(nodes)) != len(nodes) or not isinstance(trace, list) or len(trace) != days):
        raise ValueError('Invalid node, day or trace structure')
    fields = ('demand', 'on_day_fulfilled', 'on_hand', 'work_in_process', 'waiting_plan', 'backlog')
    for i, day in enumerate(trace):
        if not isinstance(day, dict) or type(day.get('day')) is not int or day['day'] != i:
            raise ValueError('Trace days must be complete and consecutive from zero')
        for field in fields:
            if not isinstance(day.get(field), dict) or set(day[field]) != set(nodes):
                raise ValueError('Trace fields must contain the same nodes')
    final = trace[-1]
    cumulative = final.get('cumulative')
    if not isinstance(cumulative, dict):
        raise ValueError('Missing cumulative ledger')
    for field in ('external_requested', 'external_delivered'):
        if not isinstance(cumulative.get(field), dict) or set(cumulative[field]) != set(nodes):
            raise ValueError('Cumulative external ledger must contain the same nodes')
    rows = []
    with localcontext() as ctx:
        ctx.prec = 100
        for node in nodes:
            requested = sum((_number(day['demand'][node]) for day in trace), Decimal(0))
            on_day = sum((_number(day['on_day_fulfilled'][node]) for day in trace), Decimal(0))
            if any(_number(day['on_day_fulfilled'][node]) > _number(day['demand'][node]) for day in trace):
                raise ValueError('Same-day fulfillment exceeds same-day demand')
            ledger_requested = _number(cumulative['external_requested'][node])
            ledger_delivered = _number(cumulative['external_delivered'][node])
            if ledger_requested != requested or ledger_delivered > requested or on_day > ledger_delivered:
                raise ValueError('External order ledger disagrees with daily demands')
            unpaid = requested - ledger_delivered
            all_backlog = _number(final['backlog'][node])
            if unpaid > all_backlog:
                raise ValueError('External backlog exceeds total stage backlog')
            rate = None if requested == 0 else str((on_day / requested).quantize(Decimal('0.000001')))
            rows.append({'node': node, 'external_requested': str(requested),
                         'external_fulfilled_on_day': str(on_day), 'same_day_rate': rate,
                         'external_backlog_end': str(unpaid), 'total_backlog_end': str(all_backlog),
                         'finished_on_hand_end': str(_number(final['on_hand'][node])),
                         'work_in_process_end': str(_number(final['work_in_process'][node])),
                         'waiting_for_inputs_end': str(_number(final['waiting_plan'][node]))})
    return {'source_result_sha256': hashlib.sha256(content).hexdigest(),
            'source_input_sha256': source_hash,
            'source_package_version': data.get('package_version'), 'time_unit': data.get('time_unit'),
            'days': days, 'rounding': 'same_day_rate is a fraction rounded to six decimal places; null when external demand is zero',
            'scope': 'Describes saved simulated output only; no real-world service, demand or cost claim. Internal orders and external orders are distinct; the checksum is not a signature.',
            'nodes': rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read a saved inventory_lab flow result')
    parser.add_argument('--input', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.input.stat().st_size > MAX_BYTES:
            raise ValueError('Result file exceeds 100 MiB')
        result = summarize(args.input.read_bytes())
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return 0
    except (OSError, UnicodeError, KeyError, TypeError, ValueError, ArithmeticError) as exc:
        print('error: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
