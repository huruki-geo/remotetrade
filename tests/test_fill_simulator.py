from __future__ import annotations

import unittest

from remotetrade.arbitrage import LimitArbitrageOrder
from remotetrade.clients import OrderBook, OrderBookLevel
from remotetrade.fill_simulator import simulate_limit_pair_fill


class FillSimulatorTest(unittest.TestCase):
    def test_detects_single_leg_fill(self) -> None:
        order = LimitArbitrageOrder(
            symbol="BTC-USD",
            buy_venue="coinbase",
            sell_venue="kraken",
            buy_limit=100.0,
            sell_limit=103.0,
            net_spread_pct=0.01,
            estimated_profit_usd=10.0,
            notional_usd=1000.0,
            qty=10.0,
        )
        buy_after = OrderBook(
            "coinbase",
            "BTC-USD",
            bids=[OrderBookLevel(99.0, 10.0)],
            asks=[OrderBookLevel(99.5, 10.0)],
            raw={},
            observed_at="now",
        )
        sell_after = OrderBook(
            "kraken",
            "XBTUSD",
            bids=[OrderBookLevel(102.0, 10.0)],
            asks=[OrderBookLevel(104.0, 10.0)],
            raw={},
            observed_at="now",
        )

        result = simulate_limit_pair_fill(order, buy_after, sell_after)

        self.assertEqual(result.outcome, "buy_only")
        self.assertTrue(result.buy_filled)
        self.assertFalse(result.sell_filled)


if __name__ == "__main__":
    unittest.main()
