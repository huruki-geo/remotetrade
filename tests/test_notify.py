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

        self.assertIn("**売買あり | Limit Paper Fill**", message)
        self.assertIn("主レーン: `Polymarket公開シグナル活用 Coincheck BTC/JPY post-only 紙トレード (未実装)`", message)
        self.assertIn("並走レーン: `Polymarket公開シグナル活用 bitbank BTC/JPY maker 紙トレード (収集中)`", message)
        self.assertIn("探索レーン: `アビトラ候補検証 (paper-only)`", message)
        self.assertIn("Coincheck BTC/JPY取引所手数料: `maker 0 bps / taker 0 bps`", message)
        self.assertIn("別途評価: `spread / 約定可能性 / 遅延`", message)
        self.assertIn("Polymarket: `公開シグナル参照のみ`", message)
        self.assertIn("**LimitPaper** `両足約定`", message)
        self.assertIn("今回損益: `+1.2300`", message)
        self.assertIn("実現損益: `2.3400`", message)

    def test_translates_common_field_values(self) -> None:
        message = format_discord_tick(
            "指値裁定紙トレード",
            ["[LimitPaper] no_candidate: fill=no_pending pnl=+0.0000 realized_pnl=0.0000 pending=NONE"],
        )

        self.assertIn("**待機 | 指値裁定紙トレード**", message)
        self.assertIn("待機中の指値: `なし`", message)
        self.assertIn("約定判定: `未発注`", message)

    def test_formats_error(self) -> None:
        message = format_discord_error("Paper Tick", "boom")

        self.assertEqual(message, "**エラー Paper Tick**\n- `boom`")


if __name__ == "__main__":
    unittest.main()
