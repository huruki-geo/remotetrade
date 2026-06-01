from __future__ import annotations

import unittest

from remotetrade.coincheck_poly_maker_analysis import format_maker_summaries, summarize_maker_events


class CoincheckPolyMakerAnalysisTest(unittest.TestCase):
    def test_summarizes_fill_rate_net_pnl_drawdown_and_losing_streak(self) -> None:
        events = [
            _event("entry_quoted", "BUY", "", "", "0"),
            _event("entry_filled", "", "LONG", "", "0"),
            _event("exit_filled", "", "LONG", "-2.0", "0"),
            _event("entry_quoted", "BUY", "", "", "0"),
            _event("entry_filled", "", "LONG", "", "0"),
            _event("exit_filled", "", "LONG", "-3.0", "0"),
            _event("entry_quoted", "BUY", "", "", "0"),
            _event("entry_filled", "", "LONG", "", "0"),
            _event("exit_filled", "", "LONG", "8.0", "0"),
            _event("entry_quoted", "BUY", "", "", "0"),
        ]

        rows = summarize_maker_events(events, hourly=True)
        report = format_maker_summaries(rows)

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].entry_quotes, 4)
        self.assertEqual(rows[0].entry_fills, 3)
        self.assertEqual(rows[0].closed_trades, 3)
        self.assertAlmostEqual(rows[0].average_net_pnl_bps, 1.0)
        self.assertAlmostEqual(rows[0].maximum_drawdown_bps, 5.0)
        self.assertEqual(rows[0].maximum_losing_streak, 2)
        self.assertIn("scalp_fast,00,LONG,4,3,75.0%,3,33.3%,+1.000,+3.000,5.000,2", report)


def _event(event: str, order_side: str, position_side: str, net_pnl_bps: str, hour: str) -> dict[str, str]:
    return {
        "pattern_id": "scalp_fast",
        "event": event,
        "order_side": order_side,
        "position_side": position_side,
        "net_pnl_bps": net_pnl_bps,
        "entry_jst_hour": hour,
    }


if __name__ == "__main__":
    unittest.main()
