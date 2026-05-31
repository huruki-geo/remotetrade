from __future__ import annotations

import unittest
from unittest.mock import patch

from remotetrade.boba_synapse_probe import DAI, NUSD, TOKENS, scan_boba_synapse
from remotetrade.boba_zencha_probe import CALCULATE_SWAP, GET_TOKEN, GET_TOKEN_BALANCE


class StubRpc:
    def chain_id(self):
        return 288

    def block_number(self):
        return 123

    def gas_price(self):
        return 1_000_000

    def eth_call_at(self, address, data, block_number):
        selector = data[:10]
        args = [int(data[index : index + 64], 16) for index in range(10, len(data), 64)]
        if selector == GET_TOKEN:
            return "0x" + "0" * 24 + TOKENS[args[0]][1].removeprefix("0x")
        if selector == GET_TOKEN_BALANCE:
            return hex((1 * 10**18, 700 * 10**18, 580 * 10**6, 640 * 10**6)[args[0]])
        if selector == CALCULATE_SWAP:
            token_in, token_out, amount_in = args
            if (token_in, token_out) == (2, 3):
                return hex(amount_in * 102 // 100)
            return hex(amount_in)
        raise AssertionError(data)


class StubResponse:
    def __init__(self, bid, ask):
        self.payload = {"bid": bid, "ask": ask}

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class BobaSynapseProbeTest(unittest.TestCase):
    def test_uses_only_canonical_usdc_usdt_route(self) -> None:
        with patch(
            "remotetrade.boba_cex_dex_probe.requests.get",
            side_effect=[StubResponse("0.999", "1.001"), StubResponse("2000", "2001")],
        ):
            probe = scan_boba_synapse(StubRpc(), sizes_usd=(10.0, 20.0))

        self.assertTrue(probe.opportunity)
        self.assertIn("USDC(CEX buy) -> USDT(Synapse swap)", probe.route)
        self.assertNotIn("nUSD", probe.route)
        self.assertEqual((probe.nusd_balance, probe.dai_balance), (1.0, 700.0))


if __name__ == "__main__":
    unittest.main()
