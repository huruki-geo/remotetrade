from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from remotetrade.clients import Candle
from remotetrade.paper import Position


@dataclass(frozen=True)
class WickSignal:
    side: str
    strength: float
    reason: str


@dataclass(frozen=True)
class WickDecision:
    action: str
    side: str | None = None
    reason: str = ""


def detect_wick_signal(candle: Candle, min_wick_ratio: float, min_range_pct: float) -> WickSignal | None:
    if candle.range <= 0 or candle.close <= 0:
        return None

    range_pct = candle.range / candle.close
    if range_pct < min_range_pct:
        return None

    upper_wick = candle.high - max(candle.open, candle.close)
    lower_wick = min(candle.open, candle.close) - candle.low
    upper_ratio = upper_wick / candle.range
    lower_ratio = lower_wick / candle.range

    if lower_ratio >= min_wick_ratio and lower_ratio > upper_ratio:
        return WickSignal("LONG", lower_ratio, "lower_wick_reversal")
    if upper_ratio >= min_wick_ratio and upper_ratio > lower_ratio:
        return WickSignal("SHORT", upper_ratio, "upper_wick_reversal")
    return None


class WickReversalStrategy:
    def __init__(
        self,
        take_profit_pct: float,
        stop_loss_pct: float,
        hold_seconds: int,
    ) -> None:
        self.take_profit_pct = take_profit_pct
        self.stop_loss_pct = stop_loss_pct
        self.hold_seconds = hold_seconds

    def decide(self, signal: WickSignal | None, position: Position | None, pnl_pct: float) -> WickDecision:
        if position is None:
            if signal is None:
                return WickDecision("WAIT", reason="no_wick_signal")
            return WickDecision("OPEN", signal.side, signal.reason)

        if pnl_pct >= self.take_profit_pct:
            return WickDecision("CLOSE", reason="take_profit")
        if pnl_pct <= self.stop_loss_pct:
            return WickDecision("CLOSE", reason="stop_loss")
        if self._position_age_seconds(position) >= self.hold_seconds:
            return WickDecision("CLOSE", reason="hold_window_elapsed")
        if signal and signal.side != position.side:
            return WickDecision("CLOSE", reason="opposite_wick_signal")

        return WickDecision("HOLD", position.side, "position_active")

    @staticmethod
    def _position_age_seconds(position: Position) -> float:
        entry_time = datetime.fromisoformat(position.entry_time)
        if entry_time.tzinfo is None:
            entry_time = entry_time.replace(tzinfo=UTC)
        return (datetime.now(UTC) - entry_time).total_seconds()
