from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from remotetrade.report import build_daily_report


class ReportTest(unittest.TestCase):
    def test_builds_daily_report_from_data_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (root / "limit_paper_ticks.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "time",
                        "realized_pnl",
                        "both_filled",
                        "buy_only",
                        "sell_only",
                        "expired",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "time": "2026-05-28T00:00:00+00:00",
                        "realized_pnl": "1.230000",
                        "both_filled": "2",
                        "buy_only": "1",
                        "sell_only": "0",
                        "expired": "3",
                    }
                )
            with (root / "limit_paper_trades.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["time", "action"])
                writer.writeheader()
                writer.writerow({"time": "2026-05-28T00:01:00+00:00", "action": "FILL"})
            (root / "orderbook_snapshots.jsonl").write_text("{}\n{}\n", encoding="utf-8")
            (root / "limit_paper_state.json").write_text(
                json.dumps({"realized_pnl": 1.23}),
                encoding="utf-8",
            )

            report = build_daily_report(root, now=datetime(2026, 5, 28, 1, tzinfo=UTC))

        self.assertIn("**RemoteTrade 日次レポート**", report)
        self.assertIn("Polymarket実弾判定レビュー: `2026-06-15 JST`", report)
        self.assertIn("指値裁定: tick `1` / 約定 `1` / 実現損益 `1.230000`", report)
        self.assertIn("約定内訳: 両足 `2` / 片足 `1` / 期限切れ `3`", report)
        self.assertIn("板スナップショット: `2` 行", report)


if __name__ == "__main__":
    unittest.main()
