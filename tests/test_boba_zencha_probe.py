from __future__ import annotations

import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from remotetrade.boba_zencha_probe import (
    CALCULATE_SWAP,
    DAI,
    GET_TOKEN,
    GET_TOKEN_BALANCE,
    TOKENS,
    USDC,
    USDT,
    append_boba_zencha_probe,
    build_boba_zencha_report,
    scan_boba_zencha,
    should_notify_boba_zencha,
)


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
            return hex((60_000 * 10**18, 9_000 * 10**6, 17_000 * 10**6)[args[0]])
        if selector == CALCULATE_SWAP:
            token_in, token_out, amount_in = args
            if (token_in, token_out) == (1, 2):
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


class BobaZenchaProbeTest(unittest.TestCase):
    def test_detects_larger_stableswap_candidate(self) -> None:
        with patch(
            "remotetrade.boba_cex_dex_probe.requests.get",
            side_effect=[
                StubResponse("0.999", "1.001"),
                StubResponse("2000", "2001"),
            ],
        ):
            probe = scan_boba_zencha(StubRpc(), sizes_usd=(10.0, 1_000.0))

        self.assertTrue(probe.opportunity)
        self.assertIn("USDC(CEX buy) -> USDT(Zencha swap)", probe.route)
        self.assertEqual(probe.profitable_capacity_usd, 1_000.0)
        self.assertEqual((probe.dai_balance, probe.usdc_balance, probe.usdt_balance), (60_000.0, 9_000.0, 17_000.0))

    def test_counts_reappearance_as_a_new_episode_without_summing_ticks(self) -> None:
        probe = self._probe()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "probes.jsonl"
            append_boba_zencha_probe(path, replace(probe, observed_at="2026-05-31T10:00:00+00:00", profit_usd=10.0))
            append_boba_zencha_probe(path, replace(probe, observed_at="2026-05-31T10:05:00+00:00", profit_usd=12.0))
            append_boba_zencha_probe(path, replace(probe, observed_at="2026-05-31T10:10:00+00:00", opportunity=False))
            append_boba_zencha_probe(path, replace(probe, observed_at="2026-05-31T10:15:00+00:00", profit_usd=8.0))

            report = build_boba_zencha_report(path)

        self.assertEqual(report.episode_count, 2)
        self.assertEqual(report.theoretical_episode_profit_usd, 20.0)

    def test_notifies_only_when_candidate_appears(self) -> None:
        probe = self._probe()
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "probes.jsonl"
            self.assertTrue(should_notify_boba_zencha(path, probe))
            append_boba_zencha_probe(path, probe)
            self.assertFalse(should_notify_boba_zencha(path, probe))
            append_boba_zencha_probe(path, replace(probe, opportunity=False))
            self.assertTrue(should_notify_boba_zencha(path, probe))

    def _probe(self):
        with patch(
            "remotetrade.boba_cex_dex_probe.requests.get",
            side_effect=[
                StubResponse("0.999", "1.001"),
                StubResponse("2000", "2001"),
            ],
        ):
            return scan_boba_zencha(StubRpc(), sizes_usd=(10.0,))


if __name__ == "__main__":
    unittest.main()
