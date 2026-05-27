from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from remotetrade.clients import PredictionMarket
from remotetrade.paper import Position
from remotetrade.strategy import PolymarketLeadStrategy


class PolymarketLeadStrategyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = PolymarketLeadStrategy(
            entry_threshold=0.06,
            strong_threshold=0.10,
            take_profit_pct=0.004,
            stop_loss_pct=-0.0025,
            hold_seconds=300,
        )
        self.market = PredictionMarket("1", "btc-updown-5m-test", "BTC Up or Down 5m", 0.56, 0.44, {})

    def test_opens_long_on_positive_odds_spike(self) -> None:
        decision = self.strategy.decide(self.market, odds_delta=0.06, position=None, pnl_pct=0.0)

        self.assertEqual(decision.action, "OPEN")
        self.assertEqual(decision.side, "LONG")

    def test_opens_short_on_negative_odds_spike(self) -> None:
        decision = self.strategy.decide(self.market, odds_delta=-0.06, position=None, pnl_pct=0.0)

        self.assertEqual(decision.action, "OPEN")
        self.assertEqual(decision.side, "SHORT")

    def test_closes_on_stop_loss_before_hold_expiry(self) -> None:
        position = Position(
            side="LONG",
            asset_id="BTC-USD",
            qty=1.0,
            notional_usd=100.0,
            entry_price=100.0,
            entry_time=(datetime.now(UTC) - timedelta(seconds=30)).isoformat(timespec="seconds"),
            market_slug="btc-updown-5m-test",
            entry_signal=0.06,
        )

        decision = self.strategy.decide(self.market, odds_delta=0.0, position=position, pnl_pct=-0.003)

        self.assertEqual(decision.action, "CLOSE")
        self.assertEqual(decision.reason, "stop_loss")


if __name__ == "__main__":
    unittest.main()
