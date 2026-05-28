from __future__ import annotations

import unittest

from remotetrade.notify import format_discord_error, format_discord_tick


class NotifyTest(unittest.TestCase):
    def test_formats_trade_tick_as_markdown_summary(self) -> None:
        message = format_discord_tick(
            "Limit Paper Fill",
            [
                "[LimitPaper] both_filled: fill=both_filled pnl=+1.2300 realized_pnl=2.3400 "
                "pending=NONE both=1 one_leg=0 expired=0"
            ],
        )

        self.assertIn("**TRADE Limit Paper Fill**", message)
        self.assertIn("**LimitPaper** `both_filled`", message)
        self.assertIn("pnl: `+1.2300`", message)
        self.assertIn("realized: `2.3400`", message)

    def test_formats_error(self) -> None:
        message = format_discord_error("Paper Tick", "boom")

        self.assertEqual(message, "**ERROR Paper Tick**\n- `boom`")


if __name__ == "__main__":
    unittest.main()
