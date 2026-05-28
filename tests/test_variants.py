from __future__ import annotations

import unittest

from remotetrade.variants import file_suffix, load_limit_paper_variants


class VariantsTest(unittest.TestCase):
    def test_loads_limit_paper_variants(self) -> None:
        variants = load_limit_paper_variants("normal:0.001:1.0,loose:0.0005:0.5")

        self.assertEqual(len(variants), 2)
        self.assertEqual(variants[0].id, "normal")
        self.assertEqual(variants[1].min_net_spread_pct, 0.0005)

    def test_builds_safe_file_suffix(self) -> None:
        self.assertEqual(file_suffix("BTC-USD", "strict"), "btc_usd_strict")


if __name__ == "__main__":
    unittest.main()
