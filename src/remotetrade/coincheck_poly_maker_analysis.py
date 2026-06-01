from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MakerSummary:
    pattern_id: str
    jst_hour: int | None
    side: str
    entry_quotes: int
    entry_fills: int
    closed_trades: int
    wins: int
    average_net_pnl_bps: float
    total_net_pnl_bps: float
    maximum_drawdown_bps: float
    maximum_losing_streak: int

    @property
    def fill_rate(self) -> float:
        return self.entry_fills / self.entry_quotes if self.entry_quotes else 0.0

    @property
    def win_rate(self) -> float:
        return self.wins / self.closed_trades if self.closed_trades else 0.0


def load_maker_events(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def summarize_maker_events(events: list[dict[str, str]], *, hourly: bool) -> list[MakerSummary]:
    grouped: dict[tuple[str, int | None, str], dict[str, object]] = {}
    positions: dict[str, tuple[str, int | None]] = {}
    for event in events:
        pattern_id = event["pattern_id"]
        event_name = event["event"]
        side = _event_side(event)
        hour = _hour(event) if hourly else None
        if event_name == "entry_quoted" and side:
            _group(grouped, pattern_id, hour, side)["entry_quotes"] += 1
        elif event_name == "entry_filled" and side:
            _group(grouped, pattern_id, hour, side)["entry_fills"] += 1
            positions[pattern_id] = (side, hour)
        elif event_name == "exit_filled":
            side, hour = positions.pop(pattern_id, (side, hour))
            if side:
                _group(grouped, pattern_id, hour, side)["pnls"].append(float(event["net_pnl_bps"]))

    summaries = []
    for (pattern_id, hour, side), values in grouped.items():
        pnls = values["pnls"]
        summaries.append(
            MakerSummary(
                pattern_id,
                hour,
                side,
                values["entry_quotes"],
                values["entry_fills"],
                len(pnls),
                sum(pnl > 0 for pnl in pnls),
                sum(pnls) / len(pnls) if pnls else 0.0,
                sum(pnls),
                _maximum_drawdown(pnls),
                _maximum_losing_streak(pnls),
            )
        )
    return sorted(summaries, key=lambda row: (row.pattern_id, row.jst_hour if row.jst_hour is not None else -1, row.side))


def format_maker_summaries(summaries: list[MakerSummary], *, min_closed_trades: int = 0) -> str:
    lines = [
        "pattern,jst_hour,side,entry_quotes,entry_fills,fill_rate,closed_trades,win_rate,"
        "average_net_bps,total_net_bps,max_drawdown_bps,max_losing_streak"
    ]
    for row in summaries:
        if row.closed_trades < min_closed_trades:
            continue
        hour = "ALL" if row.jst_hour is None else f"{row.jst_hour:02d}"
        lines.append(
            f"{row.pattern_id},{hour},{row.side},{row.entry_quotes},{row.entry_fills},{row.fill_rate:.1%},"
            f"{row.closed_trades},{row.win_rate:.1%},{row.average_net_pnl_bps:+.3f},{row.total_net_pnl_bps:+.3f},"
            f"{row.maximum_drawdown_bps:.3f},{row.maximum_losing_streak}"
        )
    return "\n".join(lines)


def _group(
    grouped: dict[tuple[str, int | None, str], dict[str, object]],
    pattern_id: str,
    hour: int | None,
    side: str,
) -> dict[str, object]:
    return grouped.setdefault((pattern_id, hour, side), {"entry_quotes": 0, "entry_fills": 0, "pnls": []})


def _event_side(event: dict[str, str]) -> str:
    if event.get("position_side"):
        return event["position_side"]
    if event.get("order_side") == "BUY":
        return "LONG"
    if event.get("order_side") == "SELL":
        return "SHORT"
    return ""


def _hour(event: dict[str, str]) -> int | None:
    raw = event.get("entry_jst_hour") or ""
    return int(raw) if raw else None


def _maximum_drawdown(pnls: list[float]) -> float:
    equity = 0.0
    peak = 0.0
    drawdown = 0.0
    for pnl in pnls:
        equity += pnl
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
    return drawdown


def _maximum_losing_streak(pnls: list[float]) -> int:
    maximum = 0
    current = 0
    for pnl in pnls:
        current = current + 1 if pnl < 0 else 0
        maximum = max(maximum, current)
    return maximum
