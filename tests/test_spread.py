from __future__ import annotations

import unittest

from remotetrade.clients import Quote
from remotetrade.spread import best_spread_snapshot, decide_spread, zscore


class SpreadTest(unittest.TestCase):
    def test_selects_largest_absolute_mid_spread(self) -> None:
        quotes = [
            Quote("coinbase", "BTC-USD", bid=99.0, ask=101.0, raw={}),
            Quote("kraken", "XBTUSD", bid=109.0, ask=111.0, raw={}),
            Quote("bitstamp", "BTCUSD", bid=101.0, ask=103.0, raw={}),
        ]

        snapshot = best_spread_snapshot(quotes)

        self.assertEqual(snapshot.long_venue, "coinbase")
        self.assertEqual(snapshot.short_venue, "kraken")
        self.assertGreater(snapshot.spread_pct, 0.0)

    def test_zscore_uses_observation_distribution(self) -> None:
        self.assertAlmostEqual(zscore(3.0, [1.0, 2.0, 3.0]), 1.224744871, places=6)

    def test_opens_when_zscore_exceeds_entry_threshold(self) -> None:
        decision = decide_spread(
            position=None,
            current_zscore=2.1,
            entry_zscore=2.0,
            exit_zscore=0.5,
            stop_zscore=4.0,
            pnl_pct=0.0,
            stop_loss_pct=-0.002,
        )

        self.assertEqual(decision.action, "OPEN")


if __name__ == "__main__":
    unittest.main()
