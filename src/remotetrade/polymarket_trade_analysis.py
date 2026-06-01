from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True)
class ClosedTrade:
    pattern_id: str
    entry_time: datetime
    side: str
    gross_pnl_bps: float


@dataclass(frozen=True)
class TradeSummary:
    pattern_id: str
    jst_hour: int | None
    side: str
    trades: int
    wins: int
    average_gross_pnl_bps: float
    total_gross_pnl_bps: float

    @property
    def win_rate(self) -> float:
        return self.wins / self.trades if self.trades else 0.0


def load_closed_trades(path: Path, pattern_id: str | None = None) -> list[ClosedTrade]:
    pattern = pattern_id or path.name.removesuffix("_trades.csv")
    opened: dict[str, str] | None = None
    trades: list[ClosedTrade] = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            if row["action"] == "OPEN":
                opened = row
            elif row["action"] == "CLOSE" and opened is not None:
                entry_price = float(opened["price"])
                exit_price = float(row["price"])
                qty = float(row["qty"])
                notional = entry_price * qty
                multiplier = 1 if opened["side"] == "LONG" else -1
                gross_pnl = (exit_price - entry_price) * qty * multiplier
                trades.append(
                    ClosedTrade(
                        pattern_id=pattern,
                        entry_time=datetime.fromisoformat(opened["time"]),
                        side=opened["side"],
                        gross_pnl_bps=gross_pnl / notional * 10_000,
                    )
                )
                opened = None
    return trades


def summarize_trades(trades: list[ClosedTrade], *, hourly: bool) -> list[TradeSummary]:
    grouped: dict[tuple[str, int | None, str], list[ClosedTrade]] = {}
    for trade in trades:
        hour = trade.entry_time.astimezone(JST).hour if hourly else None
        grouped.setdefault((trade.pattern_id, hour, trade.side), []).append(trade)
    summaries = []
    for (pattern_id, hour, side), rows in grouped.items():
        pnls = [row.gross_pnl_bps for row in rows]
        summaries.append(
            TradeSummary(
                pattern_id=pattern_id,
                jst_hour=hour,
                side=side,
                trades=len(rows),
                wins=sum(pnl > 0 for pnl in pnls),
                average_gross_pnl_bps=sum(pnls) / len(pnls),
                total_gross_pnl_bps=sum(pnls),
            )
        )
    return sorted(summaries, key=lambda row: (row.pattern_id, row.jst_hour or -1, row.side))


def format_summaries(summaries: list[TradeSummary], *, min_trades: int = 1) -> str:
    lines = ["pattern,jst_hour,side,trades,win_rate,average_gross_bps,total_gross_bps"]
    for row in summaries:
        if row.trades < min_trades:
            continue
        hour = "ALL" if row.jst_hour is None else f"{row.jst_hour:02d}"
        lines.append(
            f"{row.pattern_id},{hour},{row.side},{row.trades},{row.win_rate:.1%},"
            f"{row.average_gross_pnl_bps:+.3f},{row.total_gross_pnl_bps:+.3f}"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze Polymarket-led paper trades by JST entry hour.")
    parser.add_argument("trade_files", nargs="+", type=Path)
    parser.add_argument("--hourly", action="store_true", help="Split summaries by JST entry hour.")
    parser.add_argument("--min-trades", type=int, default=1)
    args = parser.parse_args()
    trades = [trade for path in args.trade_files for trade in load_closed_trades(path)]
    print(format_summaries(summarize_trades(trades, hourly=args.hourly), min_trades=args.min_trades))


if __name__ == "__main__":
    main()
