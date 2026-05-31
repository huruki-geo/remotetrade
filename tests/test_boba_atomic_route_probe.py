from __future__ import annotations

import unittest
from unittest.mock import patch

from remotetrade.boba_atomic_route_probe import OOLONG_POOLS, scan_boba_atomic_routes
from remotetrade.boba_cex_dex_probe import OOLONG_USDT_USDC_POOL, USDC, USDT
from remotetrade.boba_synapse_probe import SYNAPSE_STABLE_POOL
from remotetrade.boba_zencha_probe import CALCULATE_SWAP, ZENCHA_SWAP_FLASH_LOAN


class StubRpc:
    def chain_id(self):
        return 288

    def block_number(self):
        return 123

    def gas_price(self):
        return 1_000_000

    def eth_call_at(self, address, data, block_number):
        if address in {pool[1] for pool in OOLONG_POOLS}:
            spec = next(pool for pool in OOLONG_POOLS if pool[1] == address)
            if data == "0x0dfe1681":
                return "0x" + "0" * 24 + spec[2].removeprefix("0x")
            if data == "0xd21220a7":
                return "0x" + "0" * 24 + spec[3].removeprefix("0x")
            if data == "0x0902f1ac":
                return "0x" + "".join(f"{value:064x}" for value in (1_000 * 10**6, 1_000 * 10**6, 0))
        if data.startswith(CALCULATE_SWAP):
            amount_in = int(data[-64:], 16)
            if address == SYNAPSE_STABLE_POOL:
                return hex(amount_in * 102 // 100)
            if address == ZENCHA_SWAP_FLASH_LOAN:
                return hex(amount_in)
        raise AssertionError((address, data))


class StubResponse:
    def raise_for_status(self):
        return None

    def json(self):
        return {"bid": "2000", "ask": "2001"}


class BobaAtomicRouteProbeTest(unittest.TestCase):
    def test_detects_cross_pool_cycle(self) -> None:
        with patch("remotetrade.boba_cex_dex_probe.requests.get", return_value=StubResponse()):
            probe = scan_boba_atomic_routes(StubRpc(), sizes_usdc=(10.0, 100.0))

        self.assertTrue(probe.opportunity)
        self.assertIn("synapse", probe.route)
        self.assertIn("zencha", probe.route)
        self.assertGreater(probe.route_count, 6)
        self.assertGreater(probe.profit_usd, 0)


if __name__ == "__main__":
    unittest.main()
