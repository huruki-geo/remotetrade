from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remotetrade.polymarket_rtds import (
    CryptoPriceEvent,
    append_crypto_price_event,
    build_crypto_price_subscription,
    parse_crypto_price_message,
)


class PolymarketRtdsTest(unittest.TestCase):
    def test_builds_binance_and_chainlink_subscription(self) -> None:
        subscription = build_crypto_price_subscription()

        topics = [item["topic"] for item in subscription["subscriptions"]]
        self.assertEqual(topics, ["crypto_prices", "crypto_prices_chainlink"])
        self.assertEqual(subscription["subscriptions"][1]["type"], "*")
        self.assertEqual(subscription["subscriptions"][1]["filters"], "")

    def test_parses_chainlink_update(self) -> None:
        event = parse_crypto_price_message(
            json.dumps(
                {
                    "topic": "crypto_prices_chainlink",
                    "type": "update",
                    "timestamp": 1753314088421,
                    "payload": {
                        "symbol": "btc/usd",
                        "timestamp": 1753314088395,
                        "value": 67234.5,
                    },
                }
            ),
            received_at="2026-05-31T00:00:00.000+00:00",
        )

        self.assertEqual(
            event,
            CryptoPriceEvent(
                source="chainlink",
                symbol="btc/usd",
                price=67234.5,
                source_timestamp_ms=1753314088395,
                received_at="2026-05-31T00:00:00.000+00:00",
                message_timestamp_ms=1753314088421,
            ),
        )

    def test_ignores_non_price_messages(self) -> None:
        self.assertIsNone(parse_crypto_price_message('{"topic":"comments","type":"update","payload":{}}'))
        self.assertIsNone(parse_crypto_price_message("PING"))

    def test_appends_jsonl_event(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            append_crypto_price_event(
                path,
                CryptoPriceEvent("binance", "btcusdt", 70000.0, 123, "now", 124),
            )

            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["source"], "binance")
        self.assertEqual(payload["price"], 70000.0)


if __name__ == "__main__":
    unittest.main()
