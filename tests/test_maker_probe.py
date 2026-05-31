from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from remotetrade.maker_probe import (
    MakerProbeObservation,
    MakerProbeTarget,
    append_maker_probe_observations,
    build_maker_probe_reports,
    fetch_maker_probe_observations,
)


class StubBitbankClient:
    def get_pairs(self):
        return [
            {
                "name": "mana_jpy",
                "maker_fee_rate_quote": "-0.0002",
                "taker_fee_rate_quote": "0.0012",
            }
        ]

    def get_order_book(self, pair):
        return {"bids": [["10", "100"], ["9", "100"]], "asks": [["11", "100"], ["12", "100"]]}


class StubGmoClient:
    def get_symbols(self):
        return [{"symbol": "WILD", "makerFee": "-0.0003", "takerFee": "0.0009"}]

    def get_order_book(self, symbol):
        return {
            "bids": [{"price": "3.5", "size": "100"}],
            "asks": [{"price": "3.6", "size": "100"}],
        }


class MakerProbeTest(unittest.TestCase):
    def test_fetches_target_books_with_current_fees(self) -> None:
        observations = fetch_maker_probe_observations(
            targets=(MakerProbeTarget("bitbank", "mana_jpy"), MakerProbeTarget("gmo_coin", "WILD")),
            bitbank_client=StubBitbankClient(),
            gmo_client=StubGmoClient(),
        )

        self.assertEqual([observation.symbol for observation in observations], ["mana_jpy", "WILD"])
        self.assertEqual(observations[0].maker_fee_bps, -2.0)
        self.assertEqual(observations[0].bid_depth_quote, 1900.0)
        self.assertAlmostEqual(observations[1].maker_fee_bps, -3.0)

    def test_appends_probe_csv(self) -> None:
        observations = fetch_maker_probe_observations(
            targets=(MakerProbeTarget("bitbank", "mana_jpy"),),
            bitbank_client=StubBitbankClient(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "maker_probe_ticks.csv"
            append_maker_probe_observations(path, observations)

            with path.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["symbol"], "mana_jpy")
        self.assertEqual(rows[0]["maker_fee_bps"], "-2.0")

    def test_replays_conservative_cross_and_markout(self) -> None:
        observations = [
            _observation("t0", bid=100, ask=110),
            _observation("t1", bid=97, ask=99),
            _observation("t2", bid=98, ask=101),
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "maker_probe_ticks.csv"
            append_maker_probe_observations(path, observations)

            report = build_maker_probe_reports(path)[0]

        self.assertEqual(report.quotes, 2)
        self.assertEqual(report.buy_only, 1)
        self.assertEqual(report.unfilled, 1)
        self.assertLess(report.average_hedged_pnl_bps, 0)
        self.assertLess(report.average_markout_bps, 0)


def _observation(time: str, bid: float, ask: float) -> MakerProbeObservation:
    spread_bps = (ask - bid) / ((ask + bid) / 2) * 10_000
    return MakerProbeObservation(time, "bitbank", "mana_jpy", bid, ask, spread_bps, -2, 12, spread_bps + 4, 1000, 1000)


if __name__ == "__main__":
    unittest.main()
