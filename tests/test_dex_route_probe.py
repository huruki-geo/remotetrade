from __future__ import annotations

import unittest

from remotetrade.dex_route_probe import DAI, USDC, WETH, V2Pool, _amount_out, scan_dex_routes


class StubRpc:
    def chain_id(self):
        return 1

    def block_number(self):
        return 123

    def gas_price(self):
        return 1_000_000_000


class DexRouteProbeTest(unittest.TestCase):
    def test_records_best_allowlisted_three_leg_route_after_gas(self) -> None:
        pools = [
            V2Pool("uni", "0x1", USDC, WETH, 2_000_000 * 10**6, 1_000 * 10**18),
            V2Pool("uni", "0x2", WETH, DAI, 1_000 * 10**18, 2_100_000 * 10**18),
            V2Pool("sushi", "0x3", USDC, DAI, 2_000_000 * 10**6, 2_000_000 * 10**18),
        ]

        probe = scan_dex_routes(StubRpc(), start_usdc=1_000.0, min_net_return_pct=0.001, pools=pools)

        self.assertTrue(probe.opportunity)
        self.assertEqual(probe.assets, ("USDC", "WETH", "DAI", "USDC"))
        self.assertEqual(len(probe.pools), 3)
        self.assertGreater(probe.final_usdc, probe.start_usdc)

    def test_constant_product_quote_applies_fee_and_price_impact(self) -> None:
        amount_out = _amount_out(1_000, 100_000, 100_000, 30.0)

        self.assertLess(amount_out, 997)


if __name__ == "__main__":
    unittest.main()
