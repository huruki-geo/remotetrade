from __future__ import annotations

import unittest

from remotetrade.bsc_qash_route_probe import BTCB, BUSD, USDT, WBNB, _quote_route
from remotetrade.dex_route_probe import V2Pool


class BscQashRouteProbeTest(unittest.TestCase):
    def test_quotes_qash_example_route(self) -> None:
        pools = [
            V2Pool("pcs", "0x1", USDT, BUSD, 1_000_000 * 10**18, 1_000_000 * 10**18),
            V2Pool("pcs", "0x2", BUSD, BTCB, 100_000 * 10**18, 2 * 10**18),
            V2Pool("pcs", "0x3", USDT, BTCB, 100_000 * 10**18, 18 * 10**17),
        ]

        final_amount, assets = _quote_route(1_000 * 10**18, [USDT, BUSD, BTCB, USDT], pools, 25.0)

        self.assertEqual(assets, [USDT, BUSD, BTCB, USDT])
        self.assertGreater(final_amount, 1_000 * 10**18)


if __name__ == "__main__":
    unittest.main()
