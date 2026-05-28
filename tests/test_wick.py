from __future__ import annotations

import unittest
from datetime import UTC, datetime

from remotetrade.clients import Candle
from remotetrade.wick import detect_wick_signal


class WickTest(unittest.TestCase):
    def test_detects_lower_wick_reversal(self) -> None:
        candle = Candle(
            time=datetime(2026, 1, 1, tzinfo=UTC),
            low=95.0,
            high=101.0,
            open=100.0,
            close=100.5,
            volume=1.0,
        )

        signal = detect_wick_signal(candle, min_wick_ratio=0.55, min_range_pct=0.001)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, "LONG")

    def test_detects_upper_wick_reversal(self) -> None:
        candle = Candle(
            time=datetime(2026, 1, 1, tzinfo=UTC),
            low=99.0,
            high=105.0,
            open=100.0,
            close=99.5,
            volume=1.0,
        )

        signal = detect_wick_signal(candle, min_wick_ratio=0.55, min_range_pct=0.001)

        self.assertIsNotNone(signal)
        self.assertEqual(signal.side, "SHORT")

    def test_ignores_small_range_candle(self) -> None:
        candle = Candle(
            time=datetime(2026, 1, 1, tzinfo=UTC),
            low=99.95,
            high=100.05,
            open=100.0,
            close=100.0,
            volume=1.0,
        )

        signal = detect_wick_signal(candle, min_wick_ratio=0.55, min_range_pct=0.01)

        self.assertIsNone(signal)


if __name__ == "__main__":
    unittest.main()
