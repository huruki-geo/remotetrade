from __future__ import annotations

import unittest
from unittest.mock import patch

from remotetrade.boba_cex_dex_probe import USDC, USDT, scan_boba_cex_dex


class StubRpc:
    def chain_id(self):
        return 288

    def block_number(self):
        return 123

    def gas_price(self):
        return 1_000_000

    def eth_call_at(self, address, data, block_number):
        if data == "0x0dfe1681":
            return "0x" + "0" * 24 + USDT.removeprefix("0x")
        if data == "0xd21220a7":
            return "0x" + "0" * 24 + USDC.removeprefix("0x")
        if data == "0x0902f1ac":
            return "0x" + "".join(f"{value:064x}" for value in (1_100 * 10**6, 1_000 * 10**6, 0))
        raise AssertionError(data)


class StubResponse:
    def __init__(self, bid, ask):
        self.payload = {"bid": bid, "ask": ask}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class BobaCexDexProbeTest(unittest.TestCase):
    def test_detects_small_size_cex_dex_candidate(self) -> None:
        with patch(
            "remotetrade.boba_cex_dex_probe.requests.get",
            side_effect=[StubResponse("0.999", "1.001"), StubResponse("2000", "2001")],
        ):
            probe = scan_boba_cex_dex(StubRpc(), start_usd=10.0)

        self.assertTrue(probe.opportunity)
        self.assertEqual(probe.route, "USDC(BOBA DEX) -> USDT(CEX sell)")
        self.assertGreater(probe.final_usd, probe.start_usd)


if __name__ == "__main__":
    unittest.main()
