from __future__ import annotations

import unittest

from remotetrade.dex_route_probe import USDC, WETH, _amount_out, scan_dex_routes


class StubRpc:
    def chain_id(self):
        return 1

    def block_number(self):
        return 123

    def eth_call_at(self, address, data, block_number):
        assert block_number == 123
        if data == "0x0dfe1681":
            return "0x" + "0" * 24 + USDC.removeprefix("0x")
        if data == "0xd21220a7":
            return "0x" + "0" * 24 + WETH.removeprefix("0x")
        if data == "0x0902f1ac":
            reserves = (2_000_000 * 10**6, 1_000 * 10**18) if address.endswith("c9dc") else (2_100_000 * 10**6, 1_000 * 10**18)
            return "0x" + "".join(f"{value:064x}" for value in (*reserves, 0))
        raise AssertionError(data)


class DexRouteProbeTest(unittest.TestCase):
    def test_records_best_allowlisted_pool_route(self) -> None:
        probe = scan_dex_routes(StubRpc(), start_usdc=1_000.0, min_net_return_pct=0.001)

        self.assertTrue(probe.opportunity)
        self.assertEqual(probe.buy_pool, "uniswap_v2")
        self.assertEqual(probe.sell_pool, "sushiswap_v2")
        self.assertGreater(probe.final_usdc, probe.start_usdc)

    def test_constant_product_quote_applies_fee_and_price_impact(self) -> None:
        amount_out = _amount_out(1_000, 100_000, 100_000, 30.0)

        self.assertLess(amount_out, 997)


if __name__ == "__main__":
    unittest.main()
