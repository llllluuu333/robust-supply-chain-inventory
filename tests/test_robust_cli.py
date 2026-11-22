import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]

class RobustCLITests(unittest.TestCase):
    def test_solve_and_do_not_overwrite(self):
        example = ROOT / "examples" / "synthetic_robust.json"
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "result.json"
            args = [sys.executable, "-m", "inventory_lab.robust_cli",
                    "--input", str(example), "--output", str(output)]
            first = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            result = json.loads(output.read_text(encoding="utf8"))
            self.assertTrue(result["result"]["optimal"])
            self.assertEqual(result["environment"]["time_limit_seconds"], 60.0)
            self.assertTrue(result["environment"]["python"])
            self.assertTrue(result["environment"]["numpy"])
            self.assertTrue(result["environment"]["scipy"])
            self.assertAlmostEqual(result["result"]["objective"], 4.7641016151, places=6)
            self.assertEqual(result["input_sha256"], hashlib.sha256(example.read_bytes()).hexdigest())
            before = output.read_bytes()
            second = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertEqual(output.read_bytes(), before)

    def test_duplicate_input_rejected_without_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "input.json"
            output = Path(tmp) / "result.json"
            source.write_text('{"nodes":[],"nodes":[]}', encoding="utf8")
            result = subprocess.run([sys.executable, "-m", "inventory_lab.robust_cli",
                                     "--input", str(source), "--output", str(output)],
                                    cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())

if __name__ == "__main__":
    unittest.main()
