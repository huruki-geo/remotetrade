from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from remotetrade.paper import PaperBroker


class PaperBrokerTest(unittest.TestCase):
    def test_close_position_subtracts_round_trip_cost(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = PaperBroker(
                root / "state.json",
                root / "trades.csv",
                start_cash=300.0,
                round_trip_cost_bps=120.0,
            )

            broker.open_position("LONG", 100.0, 100.0, "market", 0.1, "BTC-USD")
            broker.close_position(101.0, 0.0, "test")

        self.assertAlmostEqual(broker.state.realized_pnl, -0.2)
        self.assertAlmostEqual(broker.state.cash, 299.8)

    def test_append_tick_writes_observation_csv(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = PaperBroker(
                root / "state.json",
                root / "trades.csv",
                start_cash=300.0,
                ticks_path=root / "ticks.csv",
            )

            broker.append_tick(
                pattern_id="scalp_fast",
                market_slug="btc-updown-5m-test",
                asset_id="BTC-USD",
                price=75000.0,
                signal_price=0.53,
                odds_delta=0.02,
                outcome="wait",
                unrealized_pnl=0.0,
                unrealized_pct=0.0,
            )

            with (root / "ticks.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["pattern_id"], "scalp_fast")
            self.assertEqual(rows[0]["odds_delta"], "0.020000")


if __name__ == "__main__":
    unittest.main()
