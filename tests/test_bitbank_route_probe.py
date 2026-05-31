from __future__ import annotations

import unittest

from remotetrade.bitbank_route_probe import scan_bitbank_routes


class StubClient:
    def get_statuses(self):
        return [{"pair": pair, "status": "NORMAL"} for pair in ("btc_jpy", "xrp_btc", "xrp_jpy")]

    def get_pairs(self):
        return [
            self._pair("btc_jpy", "btc", "jpy"),
            self._pair("xrp_btc", "xrp", "btc"),
            self._pair("xrp_jpy", "xrp", "jpy"),
        ]

    def get_order_book(self, pair):
        return {
            "btc_jpy": {"bids": [["10000000", "1"]], "asks": [["10010000", "1"]]},
            "xrp_btc": {"bids": [["0.000005", "100000"]], "asks": [["0.00000501", "100000"]]},
            "xrp_jpy": {"bids": [["51", "100000"]], "asks": [["51.1", "100000"]]},
        }[pair]

    @staticmethod
    def _pair(name, base, quote):
        return {
            "name": name,
            "base_asset": base,
            "quote_asset": quote,
            "is_enabled": True,
            "taker_fee_rate_quote": "0.001",
        }


class BitbankRouteProbeTest(unittest.TestCase):
    def test_records_best_profitable_triangle(self) -> None:
        probe = scan_bitbank_routes(StubClient(), start_amount=100_000.0, min_net_return_pct=0.001)

        self.assertTrue(probe.opportunity)
        self.assertEqual(probe.assets, ("jpy", "btc", "xrp", "jpy"))
        self.assertGreater(probe.net_return_pct, 0.0)


if __name__ == "__main__":
    unittest.main()
