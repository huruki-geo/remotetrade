from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from remotetrade.polymarket_trade_analysis import load_closed_trades, summarize_trades


class PolymarketTradeAnalysisTest(unittest.TestCase):
    def test_summarizes_gross_pnl_by_jst_entry_hour_and_side(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "strong_only_trades.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["time", "action", "side", "asset_id", "qty", "price", "pnl", "market_slug", "signal", "reason"],
                )
                writer.writeheader()
                writer.writerow(
                    {"time": "2026-06-01T12:00:00+00:00", "action": "OPEN", "side": "SHORT", "qty": "2", "price": "100"}
                )
                writer.writerow(
                    {"time": "2026-06-01T12:01:00+00:00", "action": "CLOSE", "side": "SHORT", "qty": "2", "price": "99"}
                )
                writer.writerow(
                    {"time": "2026-06-01T13:00:00+00:00", "action": "OPEN", "side": "LONG", "qty": "1", "price": "100"}
                )
                writer.writerow(
                    {"time": "2026-06-01T13:01:00+00:00", "action": "CLOSE", "side": "LONG", "qty": "1", "price": "102"}
                )

            summaries = summarize_trades(load_closed_trades(path), hourly=True)

        self.assertEqual([(row.jst_hour, row.side, row.trades) for row in summaries], [(21, "SHORT", 1), (22, "LONG", 1)])
        self.assertAlmostEqual(summaries[0].average_gross_pnl_bps, 100)
        self.assertAlmostEqual(summaries[1].average_gross_pnl_bps, 200)


if __name__ == "__main__":
    unittest.main()
