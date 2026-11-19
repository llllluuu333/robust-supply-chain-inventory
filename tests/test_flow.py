import copy
from decimal import Decimal, localcontext
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from inventory_lab import flow, flow_demo
from inventory_lab.flow_engine import FlowSimulatorDecimal, CONTEXT

D = Decimal
PROJECT = Path(__file__).resolve().parents[1]


class DecimalMaterialFlowTests(unittest.TestCase):
    def test_two_day_processing_and_old_backlog_hand_calculation(self):
        sim = FlowSimulatorDecimal({'A': []}, {'A': 2}, {'A': '1'})
        rows = sim.run([{'A': '1'}, {}, {}])
        self.assertEqual([x['backlog']['A'] for x in rows], [D('1'), D('1'), D('0')])
        self.assertEqual([x['on_day_fulfilled']['A'] for x in rows], [D('0'), D('0'), D('0')])
        self.assertEqual(rows[2]['on_hand']['A'], D('1'))
        self.assertEqual(sim.completed['A'], D('2'))
        self.assertEqual(sim.shipped['A'], D('1'))

    def test_assembly_cannot_start_without_each_input(self):
        sim = FlowSimulatorDecimal({'A': [], 'B': [], 'M': ['A', 'B']},
                                   {'A': 0, 'B': 2, 'M': 0}, {'A': '0', 'B': '0', 'M': '0'})
        first = sim.step({'M': '1'})
        self.assertEqual(sim.started['M'], D('0'))
        self.assertEqual(first['input_stock']['M']['A'], D('1'))
        self.assertEqual(first['input_stock']['M']['B'], D('0'))
        sim.step({}); last = sim.step({})
        self.assertEqual(sim.completed['M'], D('1'))
        self.assertEqual(last['backlog']['M'], D('0'))
        self.assertEqual(last['on_day_fulfilled']['M'], D('0'))

    def test_partial_delivery_obeys_fifo(self):
        sim = FlowSimulatorDecimal({'A': [], 'B': ['A'], 'C': ['A']},
                                   {'A': 3, 'B': 0, 'C': 0}, {'A': '0', 'B': '0', 'C': '0'})
        # Seed one prior completion solely to construct a shared-stock competition.
        sim.H['A'] = sim.started['A'] = sim.created['A'] = sim.completed['A'] = D('1')
        with localcontext(CONTEXT):
            sim._request('B', None, D('2')); sim._request('C', None, D('1')); sim._settle()
        self.assertEqual(sim.received['B']['A'], D('1'))
        self.assertEqual(sim.received['C']['A'], D('0'))
        self.assertEqual([(r.child, r.remaining) for r in sim.queues['A']], [('B', D('1')), ('C', D('1'))])

    def test_small_order_tail_and_large_value_are_preserved(self):
        sim = FlowSimulatorDecimal({'A': []}, {'A': 2}, {'A': '0.0000001'})
        sim.step({}); sim.step({}); row = sim.step({'A': '0.0000001005'})
        self.assertEqual(row['backlog']['A'], D('0.0000000005'))
        self.assertEqual(row['on_day_fulfilled']['A'], D('0.0000001'))
        sim = FlowSimulatorDecimal({'A': []}, {'A': 0}, {'A': '1000000000000'})
        with localcontext() as ctx:
            ctx.prec = 5
            for _ in range(10):
                sim.step({'A': '0.0000001'})
        self.assertEqual(sim.shipped['A'], D('0.000001'))
        self.assertEqual(sim.completed['A'], D('1000000000000.000001'))

    def test_simulated_trace_keeps_decimal_strings_and_cumulative_ledgers(self):
        result = flow.simulate(json.dumps(flow_demo.synthetic_input()).encode('utf8'))
        self.assertEqual(result['schema_version'], 'inventory_lab.flow.result.v1')
        self.assertEqual(result['package_version'], '0.8.0')
        self.assertEqual(result['days'], 8)
        row = result['daily_trace'][0]
        self.assertIsInstance(row['demand']['Assembler'], str)
        self.assertEqual(D(row['cumulative']['external_requested']['Assembler']), D('1'))
        self.assertIn('received', row['cumulative'])
        self.assertIn('consumed', row['cumulative'])
        self.assertIn('no actual costs', result['scope'].lower())

    def test_input_contract_rejects_bad_schema_size_graph_and_numbers(self):
        base = flow_demo.synthetic_input()
        bad = []
        d = copy.deepcopy(base); d['schema_version'] = 'old'; bad.append(d)
        d = copy.deepcopy(base); d['time_unit'] = 'year'; bad.append(d)
        d = copy.deepcopy(base); d['extra'] = 1; bad.append(d)
        d = copy.deepcopy(base); d['demands'] = []; bad.append(d)
        d = copy.deepcopy(base); d['demands'] = [{}] * 367; bad.append(d)
        d = copy.deepcopy(base); d['demands'][0]['unknown'] = 1; bad.append(d)
        d = copy.deepcopy(base); d['targets']['Assembler'] = '1e-31'; bad.append(d)
        d = copy.deepcopy(base); d['parents']['Supplier_A'] = ['Assembler']; bad.append(d)
        for value in bad:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                flow.simulate(json.dumps(value).encode('utf8'))
        with self.assertRaises(ValueError): flow.parse_input(b'{"x": 1, "x": 2}')
        with self.assertRaises(ValueError): flow.parse_input(b'{"x": NaN}')
        with self.assertRaises(ValueError): flow.parse_input(b' ' * (flow.MAX_INPUT_BYTES + 1))

    def test_python_interface_derives_hash_from_exact_input_bytes(self):
        raw = json.dumps(flow_demo.synthetic_input(), separators=(',', ':')).encode('utf8')
        first = flow.simulate(raw)
        changed = raw + b'  '
        second = flow.simulate(changed)
        self.assertEqual(first['input_sha256'], hashlib.sha256(raw).hexdigest())
        self.assertEqual(second['input_sha256'], hashlib.sha256(changed).hexdigest())
        self.assertNotEqual(first['input_sha256'], second['input_sha256'])
        self.assertEqual(first['daily_trace'], second['daily_trace'])
        with self.assertRaises(TypeError):
            flow.simulate(raw, '0' * 64)

    def test_cli_replays_exact_input_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'input.json'; out = root / 'result.json'
            data = flow_demo.synthetic_input()
            raw = json.dumps(data, ensure_ascii=False, indent=2).encode('utf8')
            source.write_bytes(raw)
            env = dict(os.environ); env['PYTHONPATH'] = str(PROJECT)
            cmd = [sys.executable, '-m', 'inventory_lab.flow', '--input', str(source), '--output', str(out)]
            first = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            saved = out.read_bytes(); result = json.loads(saved)
            self.assertEqual(result['input_sha256'], hashlib.sha256(raw).hexdigest())
            self.assertEqual(result['days'], 8)
            again = subprocess.run(cmd, cwd=root, env=env, capture_output=True, text=True)
            self.assertNotEqual(again.returncode, 0)
            self.assertEqual(out.read_bytes(), saved)

    def test_cli_failure_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); source = root / 'input.json'; out = root / 'result.json'
            data = flow_demo.synthetic_input(); data['demands'][0]['Assembler'] = '-1'
            source.write_text(json.dumps(data), encoding='utf8')
            env = dict(os.environ); env['PYTHONPATH'] = str(PROJECT)
            p = subprocess.run([sys.executable, '-m', 'inventory_lab.flow', '--input', str(source), '--output', str(out)],
                               cwd=root, env=env, capture_output=True, text=True)
            self.assertNotEqual(p.returncode, 0)
            self.assertFalse(out.exists())

    def test_packaged_demo_from_outside_source_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder); out = root / 'demo.json'; env = dict(os.environ); env['PYTHONPATH'] = str(PROJECT)
            p = subprocess.run([sys.executable, '-m', 'inventory_lab.flow_demo', '--output', str(out)],
                               cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            saved = json.loads(out.read_text(encoding='utf8'))
            content = json.dumps(saved['demo_input'], sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode('utf8')
            self.assertEqual(saved['input_sha256'], hashlib.sha256(content).hexdigest())
            self.assertEqual(saved['days'], 8)


if __name__ == '__main__':
    unittest.main()
