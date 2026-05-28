from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from remotetrade.arbitrage import LimitArbitrageOrder
from remotetrade.clients import OrderBook, OrderBookLevel
from remotetrade.limit_paper import LimitPaperBroker, find_limit_candidate


class LimitPaperTest(unittest.TestCase):
    def test_realizes_pnl_when_both_limit_legs_fill(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = LimitPaperBroker(
                root / "state.json",
                root / "trades.csv",
                root / "ticks.csv",
                root / "snapshots.jsonl",
                start_cash=300.0,
                maker_fee_bps=10.0,
                taker_fee_bps=20.0,
                order_ttl_ticks=3,
            )
            order = LimitArbitrageOrder(
                symbol="BTC-USD",
                buy_venue="coinbase",
                sell_venue="kraken",
                buy_limit=100.0,
                sell_limit=103.0,
                net_spread_pct=0.02,
                estimated_profit_usd=20.0,
                notional_usd=1000.0,
                qty=10.0,
            )

            self.assertEqual(broker.place_order(order), "placed")
            outcome, pnl, fill = broker.evaluate_pending(
                [
                    OrderBook(
                        "coinbase",
                        "BTC-USD",
                        bids=[OrderBookLevel(99.0, 10.0)],
                        asks=[OrderBookLevel(99.5, 10.0)],
                        raw={},
                        observed_at="now",
                    ),
                    OrderBook(
                        "kraken",
                        "XBTUSD",
                        bids=[OrderBookLevel(103.5, 10.0)],
                        asks=[OrderBookLevel(104.0, 10.0)],
                        raw={},
                        observed_at="now",
                    ),
                ]
            )

            self.assertEqual(outcome, "both_filled")
            self.assertIsNotNone(fill)
            self.assertGreater(pnl, 0.0)
            self.assertIsNone(broker.state.pending)
            self.assertEqual(broker.state.both_filled, 1)

    def test_find_limit_candidate_from_books(self) -> None:
        candidate = find_limit_candidate(
            [
                OrderBook(
                    "coinbase",
                    "BTC-USD",
                    bids=[OrderBookLevel(100.0, 10.0)],
                    asks=[OrderBookLevel(101.0, 10.0)],
                    raw={},
                    observed_at="now",
                ),
                OrderBook(
                    "kraken",
                    "XBTUSD",
                    bids=[OrderBookLevel(103.0, 10.0)],
                    asks=[OrderBookLevel(104.0, 10.0)],
                    raw={},
                    observed_at="now",
                ),
            ],
            notional_usd=1000.0,
            maker_fee_bps=5.0,
            min_net_spread_pct=0.0,
            price_improvement_bps=1.0,
        )

        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.buy_venue, "coinbase")
        self.assertEqual(candidate.sell_venue, "kraken")


if __name__ == "__main__":
    unittest.main()
