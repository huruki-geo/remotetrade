from __future__ import annotations

import unittest

from remotetrade.arbitrage import scan_arbitrage, scan_limit_arbitrage
from remotetrade.clients import Quote


class ArbitrageTest(unittest.TestCase):
    def test_detects_net_profitable_cross_exchange_spread(self) -> None:
        quotes = [
            Quote("coinbase", "BTC-USD", bid=100.0, ask=101.0, raw={}),
            Quote("kraken", "XBTUSD", bid=103.0, ask=104.0, raw={}),
        ]

        opportunities = scan_arbitrage(
            quotes,
            notional_usd=1000.0,
            fee_bps=10.0,
            min_net_spread_pct=0.0,
        )

        self.assertEqual(len(opportunities), 1)
        self.assertEqual(opportunities[0].buy_venue, "coinbase")
        self.assertEqual(opportunities[0].sell_venue, "kraken")
        self.assertAlmostEqual(opportunities[0].gross_spread_pct, (103.0 - 101.0) / 101.0)
        self.assertGreater(opportunities[0].estimated_profit_usd, 0.0)

    def test_filters_after_fees_and_threshold(self) -> None:
        quotes = [
            Quote("coinbase", "BTC-USD", bid=100.0, ask=101.0, raw={}),
            Quote("kraken", "XBTUSD", bid=101.1, ask=102.0, raw={}),
        ]

        opportunities = scan_arbitrage(
            quotes,
            notional_usd=1000.0,
            fee_bps=20.0,
            min_net_spread_pct=0.001,
        )

        self.assertEqual(opportunities, [])

    def test_limit_arbitrage_quotes_maker_prices_inside_book(self) -> None:
        quotes = [
            Quote("coinbase", "BTC-USD", bid=100.0, ask=101.0, raw={}),
            Quote("kraken", "XBTUSD", bid=103.0, ask=104.0, raw={}),
        ]

        orders = scan_limit_arbitrage(
            quotes,
            notional_usd=1000.0,
            maker_fee_bps=5.0,
            min_net_spread_pct=0.0,
            price_improvement_bps=1.0,
        )

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].buy_venue, "coinbase")
        self.assertEqual(orders[0].sell_venue, "kraken")
        self.assertGreater(orders[0].buy_limit, 100.0)
        self.assertLess(orders[0].buy_limit, 101.0)
        self.assertGreater(orders[0].sell_limit, 103.0)
        self.assertLess(orders[0].sell_limit, 104.0)


if __name__ == "__main__":
    unittest.main()
