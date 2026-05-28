from __future__ import annotations

import unittest

from remotetrade.clients import OrderBook, OrderBookLevel
from remotetrade.profit_guard import effective_buy, evaluate_depth_arbitrage


class ProfitGuardTest(unittest.TestCase):
    def test_effective_buy_walks_depth(self) -> None:
        fill = effective_buy(
            [
                OrderBookLevel(100.0, 1.0),
                OrderBookLevel(110.0, 1.0),
            ],
            notional_usd=155.0,
        )

        self.assertTrue(fill.complete)
        self.assertAlmostEqual(fill.qty, 1.5)
        self.assertAlmostEqual(fill.avg_price, 155.0 / 1.5)

    def test_rejects_when_depth_adjusted_profit_is_too_small(self) -> None:
        buy_book = OrderBook(
            "coinbase",
            "BTC-USD",
            bids=[OrderBookLevel(99.0, 10.0)],
            asks=[OrderBookLevel(100.0, 0.1), OrderBookLevel(103.0, 10.0)],
            raw={},
            observed_at="now",
        )
        sell_book = OrderBook(
            "kraken",
            "XBTUSD",
            bids=[OrderBookLevel(101.0, 10.0)],
            asks=[OrderBookLevel(102.0, 10.0)],
            raw={},
            observed_at="now",
        )

        result = evaluate_depth_arbitrage(
            buy_book,
            sell_book,
            notional_usd=1000.0,
            fee_bps=10.0,
            min_net_spread_pct=0.0,
            safety_bps=0.0,
        )

        self.assertFalse(result.allowed)
        self.assertEqual(result.reason, "net_spread_below_threshold")


if __name__ == "__main__":
    unittest.main()
