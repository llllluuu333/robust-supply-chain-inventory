"""Meaningful checks for the local, read-only result explainer."""
import copy
from decimal import Decimal
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
import unittest

from inventory_lab import flow, flow_demo
from read_flow_result import summarize

HERE = Path(__file__).resolve().parent


def example():
    raw = json.dumps(flow_demo.synthetic_input(), sort_keys=True, separators=(',', ':')).encode('utf8')
    result = flow.simulate(raw)
    return raw, result


def encoded(data):
    return json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode('utf8')


class ReadResultTests(unittest.TestCase):
    def test_demo_external_orders_and_actual_bytes(self):
        raw, result = example()
        result_bytes = encoded(result)
        summary = summarize(result_bytes)
        self.assertEqual(summary['source_result_sha256'], hashlib.sha256(result_bytes).hexdigest())
        self.assertEqual(summary['source_input_sha256'], hashlib.sha256(raw).hexdigest())
        rows = {row['node']: row for row in summary['nodes']}
        item = rows['Assembler']
        self.assertEqual(Decimal(item['external_requested']), Decimal('3'))
        self.assertEqual(Decimal(item['external_fulfilled_on_day']), Decimal('1.75'))
        self.assertEqual(item['same_day_rate'], '0.583333')
        self.assertEqual(Decimal(item['external_backlog_end']), 0)
        self.assertIsNone(rows['Supplier_A']['same_day_rate'])

    def test_internal_backlog_is_not_external_backlog(self):
        data = {'schema_version': flow.SCHEMA, 'time_unit': 'synthetic_day',
                'parents': {'A': [], 'B': ['A']}, 'lead_times': {'A': 2, 'B': 0},
                'targets': {'A': '0', 'B': '0'}, 'demands': [{'B': '1'}]}
        result = summarize(encoded(flow.simulate(encoded(data))))
        a, b = ({x['node']: x for x in result['nodes']}[n] for n in ('A','B'))
        self.assertEqual(Decimal(a['external_backlog_end']), 0)
        self.assertEqual(Decimal(a['total_backlog_end']), 1)
        self.assertEqual(Decimal(b['external_backlog_end']), 1)
        self.assertEqual(b['same_day_rate'], '0.000000')

    def test_invalid_ledger_and_daily_delivery_rejected(self):
        _, result = example()
        corrupt = copy.deepcopy(result)
        corrupt['daily_trace'][-1]['cumulative']['external_requested']['Assembler'] = '99'
        with self.assertRaises(ValueError): summarize(encoded(corrupt))
        corrupt = copy.deepcopy(result)
        corrupt['daily_trace'][0]['on_day_fulfilled']['Assembler'] = '2'
        with self.assertRaises(ValueError): summarize(encoded(corrupt))
        corrupt = copy.deepcopy(result)
        corrupt['daily_trace'][1]['day'] = 0
        with self.assertRaises(ValueError): summarize(encoded(corrupt))
        corrupt = copy.deepcopy(result)
        corrupt['daily_trace'][0]['day'] = False
        with self.assertRaises(ValueError): summarize(encoded(corrupt))
        corrupt = copy.deepcopy(result)
        corrupt['daily_trace'][-1]['cumulative']['external_delivered']['Assembler'] = '0'
        with self.assertRaises(ValueError): summarize(encoded(corrupt))
        corrupt = copy.deepcopy(result)
        corrupt['input_sha256'] = 'invalid'
        with self.assertRaises(ValueError): summarize(encoded(corrupt))

    def test_bad_json_duplicates_and_nonfinite_rejected(self):
        for content in (b'{"schema_version":"a","schema_version":"b"}', b'{"x":NaN}', b'\xff'):
            with self.subTest(content=content), self.assertRaises((ValueError,UnicodeError)):
                summarize(content)

    def test_cli_is_read_only_and_reports_zero_demand_as_null(self):
        _, result = example()
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'saved.json'; payload = encoded(result); p.write_bytes(payload)
            cmd = [sys.executable, str(HERE / 'read_flow_result.py'), '--input', str(p)]
            run = subprocess.run(cmd, capture_output=True, text=True, encoding='utf8')
            self.assertEqual(run.returncode, 0, run.stderr)
            rows = {r['node']:r for r in json.loads(run.stdout)['nodes']}
            self.assertIsNone(rows['Supplier_A']['same_day_rate'])
            self.assertEqual(p.read_bytes(), payload)

if __name__ == '__main__':
    unittest.main()
