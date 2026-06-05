from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from remotetrade.bitbank_poly_maker import PolymarketUpQuote
from remotetrade.coincheck_poly_maker import (
    CoincheckOrderBook,
    CoincheckPolyMakerPaper,
    CoincheckTrade,
    parse_coincheck_websocket_message,
)
from remotetrade.patterns import Pattern


class CoincheckPolyMakerPaperTest(unittest.TestCase):
    def test_quotes_fills_and_closes_long_from_opposing_taker_trades(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = CoincheckPolyMakerPaper(_pattern(hold_seconds=2), root / "state.json", root / "events.csv")
            start = datetime(2026, 6, 1, tzinfo=UTC)

            broker.tick(_quote(start, 0.50), 100, 101, [], now=start)
            quoted = broker.tick(_quote(start + timedelta(seconds=1), 0.56), 100, 101, [], now=start + timedelta(seconds=1))
            filled = broker.tick(
                _quote(start + timedelta(seconds=2), 0.56),
                100,
                101,
                [_trade(start + timedelta(seconds=2), "sell", 100)],
                now=start + timedelta(seconds=2),
            )
            exit_quoted = broker.tick(_quote(start + timedelta(seconds=4), 0.56), 102, 103, [], now=start + timedelta(seconds=4))
            closed = broker.tick(
                _quote(start + timedelta(seconds=5), 0.56),
                103,
                104,
                [_trade(start + timedelta(seconds=5), "buy", 103)],
                now=start + timedelta(seconds=5),
            )

            with (root / "events.csv").open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(quoted.event, "entry_quoted")
        self.assertEqual(quoted.order_side, "BUY")
        self.assertEqual(quoted.entry_jst_hour, 9)
        self.assertEqual(filled.event, "entry_filled")
        self.assertEqual(filled.position_side, "LONG")
        self.assertEqual(exit_quoted.event, "exit_quoted:take_profit")
        self.assertEqual(exit_quoted.order_side, "SELL")
        self.assertEqual(closed.event, "exit_filled")
        self.assertAlmostEqual(closed.net_pnl_bps, 300)
        self.assertEqual(closed.closed_trades, 1)
        self.assertEqual(len(rows), 5)

    def test_quotes_short_only_when_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = CoincheckPolyMakerPaper(
                _pattern(),
                root / "state.json",
                root / "events.csv",
                allowed_sides=("SHORT",),
            )
            start = datetime(2026, 6, 1, tzinfo=UTC)

            broker.tick(_quote(start, 0.50), 100, 101, [], now=start)
            blocked_long = broker.tick(_quote(start + timedelta(seconds=1), 0.56), 100, 101, [], now=start + timedelta(seconds=1))
            broker.tick(_quote(start + timedelta(seconds=2), 0.50), 100, 101, [], now=start + timedelta(seconds=2))
            quoted_short = broker.tick(_quote(start + timedelta(seconds=3), 0.44), 100, 101, [], now=start + timedelta(seconds=3))

        self.assertEqual(blocked_long.event, "observed")
        self.assertEqual(quoted_short.event, "entry_quoted")
        self.assertEqual(quoted_short.order_side, "SELL")

    def test_blocks_entry_outside_jst_hour_allowlist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = CoincheckPolyMakerPaper(
                _pattern(),
                root / "state.json",
                root / "events.csv",
                allowed_jst_hours=(10,),
            )
            start = datetime(2026, 6, 1, tzinfo=UTC)

            broker.tick(_quote(start, 0.50), 100, 101, [], now=start)
            blocked = broker.tick(_quote(start + timedelta(seconds=1), 0.56), 100, 101, [], now=start + timedelta(seconds=1))

        self.assertEqual(blocked.event, "observed")
        self.assertIsNone(broker.state.pending_order)

    def test_does_not_trade_price_jump_between_different_markets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            broker = CoincheckPolyMakerPaper(_pattern(), root / "state.json", root / "events.csv")
            start = datetime(2026, 6, 1, tzinfo=UTC)

            broker.tick(_quote(start, 0.99, "btc-updown-5m-old"), 100, 101, [], now=start)
            switched = broker.tick(
                _quote(start + timedelta(seconds=1), 0.50, "btc-updown-5m-new"),
                100,
                101,
                [],
                now=start + timedelta(seconds=1),
            )

        self.assertEqual(switched.signal, 0.0)
        self.assertEqual(switched.event, "observed")
        self.assertIsNone(broker.state.pending_order)

    def test_parses_and_applies_coincheck_websocket_updates(self) -> None:
        book = CoincheckOrderBook({"bids": [[100, "1"]], "asks": [[102, "1"]]})
        update, trades = parse_coincheck_websocket_message(
            '["btc_jpy",{"bids":[["101","2"],["100","0"]],"asks":[["103","1"]],"last_update_at":"1"}]',
            "btc_jpy",
        )
        self.assertEqual(trades, [])
        self.assertIsNotNone(update)
        book.apply(update or {})
        self.assertEqual(book.best_bid, 101)
        self.assertEqual(book.best_ask, 102)

        update, trades = parse_coincheck_websocket_message(
            '[["1","42","btc_jpy","101","0.01","sell","1","2",null]]',
            "btc_jpy",
        )
        self.assertIsNone(update)
        self.assertEqual(trades[0].side, "sell")
        self.assertEqual(trades[0].price, 101)

    def test_rejects_crossed_local_order_book(self) -> None:
        book = CoincheckOrderBook({"bids": [[102, "1"]], "asks": [[101, "1"]]})

        with self.assertRaisesRegex(RuntimeError, "crossed"):
            book.best_prices()


def _pattern(hold_seconds: int = 60) -> Pattern:
    return Pattern("scalp_fast", "Scalp Fast", 0.05, 0.09, 0.02, -0.02, hold_seconds, 0.1, 30)


def _quote(time: datetime, price: float, market_slug: str = "btc-updown-5m-1") -> PolymarketUpQuote:
    return PolymarketUpQuote(time.isoformat(), market_slug, price)


def _trade(time: datetime, side: str, price: float) -> CoincheckTrade:
    return CoincheckTrade("1", time.isoformat(), side, price, 0.01)


if __name__ == "__main__":
    unittest.main()
