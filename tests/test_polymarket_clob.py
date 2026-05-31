from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remotetrade.clients import PredictionMarket
from remotetrade.polymarket_clob import (
    ClobMarketEvent,
    append_market_event,
    build_market_subscription,
    market_asset_ids,
    parse_market_messages,
)


class PolymarketClobTest(unittest.TestCase):
    def test_extracts_json_encoded_asset_ids(self) -> None:
        market = PredictionMarket("1", "btc-updown-5m-1", "BTC Up or Down", 0.5, 0.5, {"clobTokenIds": '["up","down"]'})

        self.assertEqual(market_asset_ids(market), ["up", "down"])

    def test_builds_public_market_subscription(self) -> None:
        self.assertEqual(
            build_market_subscription(["up", "down"]),
            {"assets_ids": ["up", "down"], "type": "market", "custom_feature_enabled": True},
        )

    def test_parses_snapshot_list_and_single_update(self) -> None:
        snapshots = parse_market_messages(json.dumps([{"event_type": "book"}, {"ignored": True}]))
        update = parse_market_messages(json.dumps({"event_type": "last_trade_price", "price": "0.5"}))

        self.assertEqual(snapshots, [{"event_type": "book"}])
        self.assertEqual(update[0]["event_type"], "last_trade_price")

    def test_rotates_event_file_at_size_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text("old\n", encoding="utf-8")

            append_market_event(path, ClobMarketEvent("m1", "now", {"event_type": "book"}), max_file_bytes=4)

            self.assertEqual(path.with_suffix(".jsonl.previous").read_text(encoding="utf-8"), "old\n")
            self.assertIn('"market_slug":"m1"', path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
