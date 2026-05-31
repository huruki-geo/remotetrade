from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from remotetrade.venue_discovery import (
    append_market_discoveries,
    scan_bitbank_small_maker_markets,
    scan_gmo_small_maker_markets,
    scan_low_cost_markets,
    scan_mexc_research_markets,
)


class StubClient:
    def get_symbols(self):
        return [
            {
                "symbol": "XRP",
                "minOrderSize": "1",
                "makerFee": "-0.0001",
                "takerFee": "0.0005",
            },
            {
                "symbol": "BTC",
                "minOrderSize": "0.001",
                "makerFee": "-0.0001",
                "takerFee": "0.0005",
            },
        ]

    def get_ticker(self, symbol):
        return {
            "bid": "100",
            "ask": "101",
            "volume": "123",
        }

    def get_order_book(self, symbol):
        return {
            "bids": [{"price": "100", "size": "10"}],
            "asks": [{"price": "101", "size": "10"}],
        }


class StubBitbankClient:
    def get_pairs(self):
        return [
            {
                "name": "xrp_jpy",
                "quote_asset": "jpy",
                "maker_fee_rate_quote": "-0.0002",
                "taker_fee_rate_quote": "0.0012",
                "unit_amount": "0.0001",
                "is_enabled": True,
            }
        ]

    def get_tickers(self):
        return [{"pair": "xrp_jpy", "buy": "100", "sell": "101", "vol": "123"}]

    def get_statuses(self):
        return [{"pair": "xrp_jpy", "status": "NORMAL", "min_amount": "1"}]

    def get_order_book(self, pair):
        return {"bids": [["100", "10"]], "asks": [["101", "10"]]}


class StubBitbankNullTickerClient(StubBitbankClient):
    def get_tickers(self):
        return [{"pair": "xrp_jpy", "buy": None, "sell": None, "vol": "0"}]


class StubFailingGmoClient:
    def get_symbols(self):
        raise RuntimeError("temporary outage")


class StubMexcClient:
    def get_symbols(self):
        return [
            {
                "symbol": "BTCUSDT",
                "quoteAsset": "USDT",
                "isSpotTradingAllowed": True,
                "orderTypes": ["LIMIT", "LIMIT_MAKER"],
                "baseSizePrecision": "0.000001",
                "makerCommission": "0",
                "takerCommission": "0.0005",
            }
        ]

    def get_book_tickers(self):
        return [{"symbol": "BTCUSDT", "bidPrice": "100", "askPrice": "101", "bidQty": "10", "askQty": "10"}]


class StubEmptyMexcClient:
    def get_symbols(self):
        return []

    def get_book_tickers(self):
        return []


class VenueDiscoveryTest(unittest.TestCase):
    def test_ranks_small_maker_markets_and_applies_rebate(self) -> None:
        discoveries = scan_gmo_small_maker_markets(StubClient(), max_order_notional_jpy=200, min_depth_jpy=0)

        self.assertEqual(discoveries[0].symbol, "XRP")
        self.assertTrue(discoveries[0].eligible_small_maker)
        self.assertEqual(discoveries[0].maker_fee_bps, -1.0)
        self.assertGreater(discoveries[0].maker_round_trip_edge_bps, discoveries[0].spread_bps)
        self.assertLess(discoveries[0].taker_round_trip_edge_bps, 0.0)

    def test_appends_jsonl_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "discovery.jsonl"
            discoveries = scan_gmo_small_maker_markets(StubClient())
            append_market_discoveries(path, discoveries)

            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["venue"], "gmo_coin")

    def test_scans_bitbank_jpy_pairs_with_current_fee(self) -> None:
        discoveries = scan_bitbank_small_maker_markets(StubBitbankClient())

        self.assertEqual(len(discoveries), 1)
        self.assertEqual(discoveries[0].venue, "bitbank")
        self.assertEqual(discoveries[0].maker_fee_bps, -2.0)

    def test_skips_bitbank_pair_with_null_quote(self) -> None:
        self.assertEqual(scan_bitbank_small_maker_markets(StubBitbankNullTickerClient()), [])

    def test_continues_when_one_venue_is_unavailable(self) -> None:
        discoveries = scan_low_cost_markets(
            gmo_client=StubFailingGmoClient(),
            bitbank_client=StubBitbankClient(),
            mexc_client=StubEmptyMexcClient(),
            min_depth_jpy=0,
        )

        self.assertEqual(len(discoveries), 1)
        self.assertEqual(discoveries[0].venue, "bitbank")

    def test_scans_mexc_as_research_only_with_usdt_budget(self) -> None:
        discoveries = scan_mexc_research_markets(StubMexcClient(), min_depth_usdt=100)

        self.assertEqual(len(discoveries), 1)
        self.assertEqual(discoveries[0].venue, "mexc_research")
        self.assertEqual(discoveries[0].quote_asset, "USDT")
        self.assertEqual(discoveries[0].taker_fee_bps, 5.0)
        self.assertTrue(discoveries[0].eligible_small_maker)


if __name__ == "__main__":
    unittest.main()
