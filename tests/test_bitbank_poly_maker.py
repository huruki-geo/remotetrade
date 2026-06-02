from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from unittest.mock import patch

from remotetrade.bitbank_poly_maker import (
    BitbankPolyMakerPaper,
    PolymarketUpQuote,
    _UNAVAILABLE_MARKET_SLUGS,
    _up_price,
    latest_polymarket_up_quote,
)


class BitbankPolyMakerPaperTest(unittest.TestCase):
    def test_quotes_fills_and_closes_long_with_maker_rebate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = BitbankPolyMakerPaper(
                root / "state.json",
                root / "events.csv",
                signal_window_seconds=10,
                signal_threshold=0.05,
                hold_seconds=2,
            )
            start = datetime(2026, 6, 1, tzinfo=UTC)

            broker.tick(_quote(start, 0.50), 100, 101, maker_fee_bps=-2, now=start)
            quoted = broker.tick(_quote(start + timedelta(seconds=1), 0.56), 100, 101, maker_fee_bps=-2, now=start + timedelta(seconds=1))
            filled = broker.tick(_quote(start + timedelta(seconds=2), 0.56), 99, 100, maker_fee_bps=-2, now=start + timedelta(seconds=2))
            exit_quoted = broker.tick(
                _quote(start + timedelta(seconds=4), 0.56), 101, 102, maker_fee_bps=-2, now=start + timedelta(seconds=4)
            )
            closed = broker.tick(
                _quote(start + timedelta(seconds=5), 0.56), 102, 103, maker_fee_bps=-2, now=start + timedelta(seconds=5)
            )

            with (root / "events.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(quoted.event, "entry_quoted")
        self.assertEqual(quoted.order_side, "BUY")
        self.assertEqual(quoted.order_price, 100)
        self.assertEqual(filled.event, "entry_filled")
        self.assertEqual(filled.position_side, "LONG")
        self.assertEqual(exit_quoted.event, "exit_quoted")
        self.assertEqual(exit_quoted.order_side, "SELL")
        self.assertEqual(closed.event, "exit_filled")
        self.assertAlmostEqual(closed.gross_pnl_bps, 200)
        self.assertAlmostEqual(closed.net_pnl_bps, 204)
        self.assertEqual(len(rows), 5)

    def test_cancels_unfilled_entry_after_ttl(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = BitbankPolyMakerPaper(root / "state.json", root / "events.csv", entry_ttl_seconds=3)
            start = datetime(2026, 6, 1, tzinfo=UTC)

            broker.tick(_quote(start, 0.50), 100, 101, maker_fee_bps=-2, now=start)
            broker.tick(_quote(start + timedelta(seconds=1), 0.56), 100, 101, maker_fee_bps=-2, now=start + timedelta(seconds=1))
            cancelled = broker.tick(
                _quote(start + timedelta(seconds=4), 0.56), 100, 101, maker_fee_bps=-2, now=start + timedelta(seconds=4)
            )

        self.assertEqual(cancelled.event, "entry_cancelled")
        self.assertIsNone(broker.state.pending_order)
        self.assertIsNone(broker.state.position)

    def test_does_not_trade_price_jump_between_different_markets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = BitbankPolyMakerPaper(root / "state.json", root / "events.csv")
            start = datetime(2026, 6, 1, tzinfo=UTC)

            broker.tick(_quote(start, 0.99, "btc-updown-5m-old"), 100, 101, maker_fee_bps=-2, now=start)
            switched = broker.tick(
                _quote(start + timedelta(seconds=1), 0.50, "btc-updown-5m-new"),
                100,
                101,
                maker_fee_bps=-2,
                now=start + timedelta(seconds=1),
            )

        self.assertEqual(switched.signal, 0.0)
        self.assertEqual(switched.event, "observed")
        self.assertIsNone(broker.state.pending_order)

    def test_extracts_up_mid_from_price_change(self) -> None:
        event = {
            "event_type": "price_change",
            "price_changes": [
                {"asset_id": "down", "best_bid": "0.39", "best_ask": "0.40"},
                {"asset_id": "up", "best_bid": "0.60", "best_ask": "0.61"},
            ],
        }

        self.assertAlmostEqual(_up_price(event, "up") or 0.0, 0.605)

    def test_caches_unavailable_polymarket_slug(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            slug = "btc-updown-5m-closed"
            path.write_text(
                json.dumps(
                    {
                        "market_slug": slug,
                        "received_at": "2026-06-01T00:00:00+00:00",
                        "event": {"event_type": "last_trade_price", "asset_id": "up", "price": "0.50"},
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            _UNAVAILABLE_MARKET_SLUGS.discard(slug)

            with patch("remotetrade.bitbank_poly_maker.PolymarketClient.find_market", side_effect=RuntimeError) as find_market:
                self.assertIsNone(latest_polymarket_up_quote(path, "https://example.test"))
                self.assertIsNone(latest_polymarket_up_quote(path, "https://example.test"))

        self.assertEqual(find_market.call_count, 1)


def _quote(time: datetime, price: float, market_slug: str = "btc-updown-5m-1") -> PolymarketUpQuote:
    return PolymarketUpQuote(time.isoformat(), market_slug, price)


if __name__ == "__main__":
    unittest.main()
