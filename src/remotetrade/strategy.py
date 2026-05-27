from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from remotetrade.clients import PredictionMarket
from remotetrade.paper import Position


@dataclass(frozen=True)
class Decision:
    action: str
    side: str | None = None
    reason: str = ""


class PolymarketLeadStrategy:
    def __init__(
        self,
        entry_threshold: float,
        strong_threshold: float,
        take_profit_pct: float,
        stop_loss_pct: float,
        hold_seconds: int,
    ) -> None:
        self.entry_threshold = entry_threshold
        self.strong_threshold = strong_threshold
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.hold_seconds = hold_seconds

    def decide(self, market: PredictionMarket, odds_delta: float | None, position: Position | None, pnl_pct: float) -> Decision:
        if odds_delta is None:
            return Decision("HOLD" if position else "WAIT", position.side if position else None, "warming_up_market")

        if position is None:
            if odds_delta >= self.entry_threshold:
                return Decision("OPEN", "LONG", "polymarket_up_odds_spike")
            if odds_delta <= -self.entry_threshold:
                return Decision("OPEN", "SHORT", "polymarket_up_odds_drop")
            return Decision("WAIT", reason="odds_delta_inside_entry_threshold")

        age_seconds = self._position_age_seconds(position)
        if pnl_pct >= self.take_profit_pct:
            return Decision("CLOSE", reason="take_profit")
        if pnl_pct <= self.stop_loss_pct:
            return Decision("CLOSE", reason="stop_loss")
        if age_seconds >= self.hold_seconds:
            return Decision("CLOSE", reason="hold_window_elapsed")

        if position.side == "LONG" and odds_delta <= -self.strong_threshold:
            return Decision("CLOSE", reason="strong_reverse_signal")
        if position.side == "SHORT" and odds_delta >= self.strong_threshold:
            return Decision("CLOSE", reason="strong_reverse_signal")

        return Decision("HOLD", position.side, "position_active")

    @staticmethod
    def _position_age_seconds(position: Position) -> float:
        entry_time = datetime.fromisoformat(position.entry_time)
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=UTC)
        return (datetime.now(UTC) - entry_time).total_seconds()
