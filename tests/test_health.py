from __future__ import annotations

import csv
import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

from remotetrade.health import build_health_report


class HealthTest(unittest.TestCase):
    def test_reports_ok_for_recent_tick(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (root / "limit_paper_ticks.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["time"])
                writer.writeheader()
                writer.writerow({"time": "2026-05-28T00:00:00+00:00"})

            with patch("remotetrade.health.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime(2026, 5, 28, 0, 1, tzinfo=UTC)
                mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
                report = build_health_report(root, max_tick_age_seconds=300, min_free_disk_mb=1)

        self.assertTrue(report.ok)
        self.assertIn("状態: `正常`", report.message)

    def test_ignores_legacy_tick_when_portfolio_ticks_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, timestamp in (
                ("limit_paper_ticks.csv", "2026-05-28T00:00:00+00:00"),
                ("limit_paper_btc_usd_normal_ticks.csv", "2026-05-28T02:00:00+00:00"),
            ):
                with (root / name).open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=["time"])
                    writer.writeheader()
                    writer.writerow({"time": timestamp})

            with patch("remotetrade.health.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime(2026, 5, 28, 2, 1, tzinfo=UTC)
                mock_datetime.fromisoformat.side_effect = datetime.fromisoformat
                report = build_health_report(root, max_tick_age_seconds=300, min_free_disk_mb=1)

        self.assertTrue(report.ok)
        self.assertIn("limit_paper_btc_usd_normal_ticks.csv", report.message)
        self.assertNotIn("limit_paper_ticks.csv", report.message)

    def test_reports_missing_companion_polymarket_stream(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with (root / "limit_paper_btc_ticks.csv").open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["time"])
                writer.writeheader()
                writer.writerow({"time": datetime.now(UTC).isoformat()})
            (root / "polymarket_crypto_prices.jsonl").write_text(
                json.dumps({"received_at": datetime.now(UTC).isoformat()}) + "\n",
                encoding="utf-8",
            )

            report = build_health_report(root, max_tick_age_seconds=300, min_free_disk_mb=1)

        self.assertFalse(report.ok)
        self.assertIn("polymarket_btc_5m_clob.jsonl", report.message)

    def test_reports_missing_ticks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            report = build_health_report(Path(tmp), max_tick_age_seconds=300, min_free_disk_mb=1)

        self.assertFalse(report.ok)
        self.assertIn("tickファイルがありません", report.message)


if __name__ == "__main__":
    unittest.main()
