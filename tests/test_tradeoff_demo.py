import unittest
from inventory_lab.tradeoff_demo import compare

class TradeoffDemoTests(unittest.TestCase):
    def test_nominal_and_robust_tradeoff(self):
        r = compare()
        n = r["nominal"]["evaluation"]
        b = r["robust"]["evaluation"]
        self.assertEqual([x["scenario"] for x in n], ["nominal", "delay_A", "delay_B"])
        self.assertEqual([x["scenario"] for x in b], ["nominal", "delay_A", "delay_B"])
        self.assertLess(n[0]["objective"], b[0]["objective"])
        self.assertGreater(max(x["objective"] for x in n), max(x["objective"] for x in b))
        self.assertAlmostEqual(max(x["objective"] for x in n), 40.0710678119, places=6)
        self.assertAlmostEqual(max(x["objective"] for x in b), 38.8564064606, places=6)

if __name__ == "__main__":
    unittest.main()
