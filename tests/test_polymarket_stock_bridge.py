from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from remotetrade.polymarket_stock_bridge import collect_stock_bridge_once


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, prices: list[float]) -> None:
        self.prices = prices
        self.headers = {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def get(self, url, params=None, timeout=None):
        price = self.prices.pop(0)
        return FakeResponse(
            {
                "events": [
                    {
                        "markets": [
                            {
                                "id": "m1",
                                "slug": "iran-peace-test",
                                "question": "US x Iran permanent peace deal by 2026?",
                                "active": True,
                                "closed": False,
                                "outcomes": '["Yes","No"]',
                                "outcomePrices": json.dumps([price, 1 - price]),
                                "volume": 1000,
                            }
                        ]
                    }
                ]
            }
        )


class PolymarketStockBridgeTest(unittest.TestCase):
    def test_collects_delta_and_alert_from_public_search(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            patterns = root / "stock_patterns.json"
            state = root / "state.json"
            events = root / "events.jsonl"
            patterns.write_text(
                json.dumps(
                    [
                        {
                            "id": "bridge",
                            "label": "Bridge",
                            "entry_threshold": 0.04,
                            "strong_threshold": 0.08,
                            "take_profit_pct": 0.02,
                            "stop_loss_pct": -0.01,
                            "hold_seconds": 86400,
                            "risk_fraction": 0.1,
                            "max_trade_size_usd": 10,
                            "categories": [
                                {
                                    "id": "iran",
                                    "label": "Iran",
                                    "query": "Iran peace",
                                    "up_long": ["AAL"],
                                    "up_short": ["OXY"],
                                    "down_long": ["OXY"],
                                    "down_short": ["AAL"],
                                }
                            ],
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with patch("remotetrade.polymarket_stock_bridge.requests.Session", return_value=FakeSession([0.20])):
                first = collect_stock_bridge_once(patterns, state, events)
            with patch("remotetrade.polymarket_stock_bridge.requests.Session", return_value=FakeSession([0.25])):
                second = collect_stock_bridge_once(patterns, state, events)

            self.assertEqual(len(first), 1)
            self.assertIsNone(first[0].odds_delta)
            self.assertFalse(first[0].alert)
            self.assertEqual(len(second), 1)
            self.assertAlmostEqual(second[0].odds_delta or 0.0, 0.05)
            self.assertTrue(second[0].alert)
            self.assertEqual(second[0].up_long, ["AAL"])
            self.assertEqual(second[0].down_long, ["OXY"])

            rows = [json.loads(line) for line in events.read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[-1]["market_slug"], "iran-peace-test")


if __name__ == "__main__":
    unittest.main()
