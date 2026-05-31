from __future__ import annotations

import unittest

from remotetrade.route_arbitrage import MarketPair, find_route_arbitrage


class RouteArbitrageTest(unittest.TestCase):
    def test_finds_profitable_triangular_route_after_fees(self) -> None:
        opportunities = find_route_arbitrage(
            [
                MarketPair("BTC-JPY", "BTC", "JPY", bid=10_000_000.0, ask=10_010_000.0),
                MarketPair("XRP-BTC", "XRP", "BTC", bid=0.000_005, ask=0.000_005_01),
                MarketPair("XRP-JPY", "XRP", "JPY", bid=51.0, ask=51.1),
            ],
            start_asset="JPY",
            start_amount=100_000.0,
            fee_bps=10.0,
            min_net_return_pct=0.001,
        )

        self.assertTrue(opportunities)
        best = opportunities[0]
        self.assertEqual(best.assets, ("JPY", "BTC", "XRP", "JPY"))
        self.assertEqual(best.sides, ("BUY", "BUY", "SELL"))
        self.assertGreater(best.net_return_pct, 0.0)

    def test_filters_route_when_fees_consume_profit(self) -> None:
        opportunities = find_route_arbitrage(
            [
                MarketPair("BTC-JPY", "BTC", "JPY", bid=10_000_000.0, ask=10_010_000.0),
                MarketPair("XRP-BTC", "XRP", "BTC", bid=0.000_005, ask=0.000_005_01),
                MarketPair("XRP-JPY", "XRP", "JPY", bid=50.2, ask=50.3),
            ],
            start_asset="JPY",
            start_amount=100_000.0,
            fee_bps=10.0,
            min_net_return_pct=0.001,
        )

        self.assertEqual(opportunities, [])

    def test_supports_four_hop_routes(self) -> None:
        opportunities = find_route_arbitrage(
            [
                MarketPair("BTC-USD", "BTC", "USD", bid=100.0, ask=101.0),
                MarketPair("ETH-BTC", "ETH", "BTC", bid=0.49, ask=0.5),
                MarketPair("SOL-ETH", "SOL", "ETH", bid=0.099, ask=0.1),
                MarketPair("SOL-USD", "SOL", "USD", bid=5.2, ask=5.3),
            ],
            start_asset="USD",
            start_amount=1_000.0,
            fee_bps=0.0,
            min_net_return_pct=0.001,
            max_hops=4,
        )

        self.assertEqual(opportunities[0].assets, ("USD", "BTC", "ETH", "SOL", "USD"))

    def test_filters_route_when_top_of_book_quantity_is_too_small(self) -> None:
        opportunities = find_route_arbitrage(
            [
                MarketPair("BTC-JPY", "BTC", "JPY", bid=10_000_000.0, ask=10_010_000.0, ask_qty=0.001),
                MarketPair("XRP-BTC", "XRP", "BTC", bid=0.000_005, ask=0.000_005_01),
                MarketPair("XRP-JPY", "XRP", "JPY", bid=51.0, ask=51.1),
            ],
            start_asset="JPY",
            start_amount=100_000.0,
            fee_bps=10.0,
            min_net_return_pct=0.001,
        )

        self.assertEqual(opportunities, [])


if __name__ == "__main__":
    unittest.main()
