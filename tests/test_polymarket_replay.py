from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remotetrade.polymarket_replay import build_replay_report, extract_market_features, format_replay_report


class PolymarketReplayTest(unittest.TestCase):
    def test_can_limit_jsonl_reads_to_recent_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            old = _book("old", "up", "2026-05-31T00:00:00+00:00", 0.50, 0.51, 100, 100)
            recent = _book("recent", "up", "2026-05-31T00:01:00+00:00", 0.50, 0.51, 100, 100)
            encoded_recent = json.dumps(recent) + "\n"
            path.write_text(json.dumps(old) + "\n" + encoded_recent, encoding="utf-8")

            features = extract_market_features(path, max_event_bytes=len(encoded_recent.encode("utf-8")) + 1)

        self.assertEqual([feature.market_slug for feature in features], ["recent"])

    def test_extracts_multi_level_imbalance_and_passes_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            rows = []
            for index in range(3):
                rows.extend(
                    [
                        _book(f"m{index}", "up", "2026-05-31T00:00:00+00:00", 0.50, 0.51, 300, 50),
                        _book(f"m{index}", "up", "2026-05-31T00:04:00+00:00", 0.69, 0.71, 200, 100),
                    ]
                )
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            features = extract_market_features(path)
            report = build_replay_report(path, required_win_rate=0.70, min_trades=3)

        self.assertGreater(features[0].multi_level_imbalance, 0.20)
        self.assertEqual(report.trades, 3)
        self.assertEqual(report.win_rate, 1.0)
        self.assertTrue(report.passed)

    def test_rejects_when_trade_count_is_too_low(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        _book("m1", "up", "2026-05-31T00:00:00+00:00", 0.50, 0.51, 300, 50),
                        _book("m1", "up", "2026-05-31T00:04:00+00:00", 0.69, 0.71, 200, 100),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_replay_report(path, required_win_rate=0.70, min_trades=30)

        self.assertFalse(report.passed)
        self.assertIn("status: `COLLECTING`", format_replay_report(report))

    def test_accepts_positive_validation_expectancy_with_low_win_rate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        _book("m1", "up", "2026-05-31T00:00:00+00:00", 0.50, 0.51, 300, 50),
                        _book("m1", "up", "2026-05-31T00:01:00+00:00", 0.39, 0.41, 100, 100),
                        _book("m2", "up", "2026-05-31T00:02:00+00:00", 0.50, 0.51, 300, 50),
                        _book("m2", "up", "2026-05-31T00:03:00+00:00", 0.39, 0.41, 100, 100),
                        _book("m3", "up", "2026-05-31T00:04:00+00:00", 0.50, 0.51, 300, 50),
                        _book("m3", "up", "2026-05-31T00:05:00+00:00", 0.89, 0.91, 100, 100),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_replay_report(path, required_win_rate=0.70, min_trades=3)

        self.assertEqual(report.win_rate, 1 / 3)
        self.assertGreater(report.validation_pnl_per_share, 0)
        self.assertTrue(report.passed)

    def test_applies_price_change_to_existing_book(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        _book("m1", "up", "2026-05-31T00:00:00+00:00", 0.50, 0.51, 100, 100),
                        {
                            "market_slug": "m1",
                            "received_at": "2026-05-31T00:00:01+00:00",
                            "event": {
                                "event_type": "price_change",
                                "price_changes": [
                                    {"asset_id": "up", "side": "BUY", "price": "0.50", "size": "300"}
                                ],
                            },
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            features = extract_market_features(path)

        self.assertEqual(len(features), 2)
        self.assertGreater(features[-1].multi_level_imbalance, features[0].multi_level_imbalance)
        self.assertGreater(features[-1].multi_level_ofi, 0.0)

    def test_tracks_trade_aggressor_imbalance(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        _book("m1", "up", "2026-05-31T00:00:00+00:00", 0.50, 0.51, 100, 100),
                        {
                            "market_slug": "m1",
                            "received_at": "2026-05-31T00:00:01+00:00",
                            "event": {
                                "event_type": "last_trade_price",
                                "asset_id": "up",
                                "side": "BUY",
                                "price": "0.51",
                                "size": "12",
                            },
                        },
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            features = extract_market_features(path)

        self.assertEqual(features[-1].trade_imbalance, 1.0)
        self.assertEqual(features[-1].polymarket_buy_trade_qty, 12.0)
        self.assertEqual(features[-1].polymarket_sell_trade_qty, 0.0)
        self.assertEqual(features[-1].polymarket_trade_qty, 12.0)

    def test_tracks_polymarket_trade_volume_in_rolling_window(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps(row)
                    for row in [
                        _book("m1", "up", "2026-05-31T00:00:00+00:00", 0.50, 0.51, 100, 100),
                        _trade("m1", "up", "2026-05-31T00:00:01+00:00", "BUY", 12),
                        _trade("m1", "up", "2026-05-31T00:00:30+00:00", "SELL", 4),
                        _trade("m1", "up", "2026-05-31T00:01:02+00:00", "BUY", 3),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            features = extract_market_features(path, trade_volume_window_seconds=60)

        self.assertEqual(features[2].polymarket_trade_qty, 16.0)
        self.assertEqual(features[-1].polymarket_buy_trade_qty, 3.0)
        self.assertEqual(features[-1].polymarket_sell_trade_qty, 4.0)
        self.assertEqual(features[-1].polymarket_trade_qty, 7.0)
        self.assertAlmostEqual(features[-1].trade_imbalance, -1 / 7)

    def test_joins_crypto_prices_and_time_remaining(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events_path = root / "events.jsonl"
            prices_path = root / "prices.jsonl"
            events_path.write_text(
                json.dumps(_book("btc-updown-5m-1780186500", "up", "2026-05-31T00:15:10+00:00", 0.50, 0.51, 100, 100))
                + "\n",
                encoding="utf-8",
            )
            prices_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "source": "chainlink",
                                "symbol": "btc/usd",
                                "price": 73800,
                                "received_at": "2026-05-31T00:15:09+00:00",
                            }
                        ),
                        json.dumps(
                            {
                                "source": "binance",
                                "symbol": "btcusdt",
                                "price": 73873.8,
                                "received_at": "2026-05-31T00:15:09+00:00",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            feature = extract_market_features(events_path, crypto_prices_path=prices_path)[0]

        self.assertEqual(feature.chainlink_btc_usd, 73800)
        self.assertEqual(feature.binance_btc_usdt, 73873.8)
        self.assertAlmostEqual(feature.binance_chainlink_basis_pct or 0.0, 0.001)
        self.assertIsNotNone(feature.seconds_remaining)


def _book(slug: str, asset_id: str, time: str, bid: float, ask: float, bid_qty: float, ask_qty: float) -> dict:
    return {
        "market_slug": slug,
        "received_at": time,
        "event": {
            "event_type": "book",
            "asset_id": asset_id,
            "bids": [{"price": str(bid), "size": str(bid_qty)}],
            "asks": [{"price": str(ask), "size": str(ask_qty)}],
        },
    }


def _trade(slug: str, asset_id: str, time: str, side: str, size: float) -> dict:
    return {
        "market_slug": slug,
        "received_at": time,
        "event": {
            "event_type": "last_trade_price",
            "asset_id": asset_id,
            "side": side,
            "price": "0.51",
            "size": str(size),
        },
    }


if __name__ == "__main__":
    unittest.main()
