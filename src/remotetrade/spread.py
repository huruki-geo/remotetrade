from __future__ import annotations

import csv
import json
import statistics
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from remotetrade.clients import Quote


@dataclass(frozen=True)
class SpreadSnapshot:
    long_venue: str
    short_venue: str
    long_mid: float
    short_mid: float
    spread_pct: float


@dataclass
class SpreadPosition:
    long_venue: str
    short_venue: str
    long_entry_mid: float
    short_entry_mid: float
    notional_usd: float
    entry_spread_pct: float
    entry_zscore: float
    entry_time: str


@dataclass
class SpreadState:
    cash: float
    realized_pnl: float = 0.0
    position: SpreadPosition | None = None
    observations: list[float] | None = None


@dataclass(frozen=True)
class SpreadDecision:
    action: str
    reason: str


def best_spread_snapshot(quotes: list[Quote]) -> SpreadSnapshot:
    if len(quotes) < 2:
        raise RuntimeError("At least two quotes are required for spread trading.")

    snapshots: list[SpreadSnapshot] = []
    for long_quote in quotes:
        for short_quote in quotes:
            if long_quote.venue == short_quote.venue:
                continue
            if long_quote.mid >= short_quote.mid:
                continue
            avg_mid = (long_quote.mid + short_quote.mid) / 2
            spread_pct = (short_quote.mid - long_quote.mid) / avg_mid
            snapshots.append(
                SpreadSnapshot(
                    long_venue=long_quote.venue,
                    short_venue=short_quote.venue,
                    long_mid=long_quote.mid,
                    short_mid=short_quote.mid,
                    spread_pct=spread_pct,
                )
            )
    if not snapshots:
        raise RuntimeError("No valid spread pair found.")
    return max(snapshots, key=lambda snapshot: snapshot.spread_pct)


def zscore(value: float, observations: list[float]) -> float:
    if len(observations) < 2:
        return 0.0
    mean = statistics.fmean(observations)
    stddev = statistics.pstdev(observations)
    if stddev == 0:
        return 0.0
    return (value - mean) / stddev


class SpreadPaperBroker:
    def __init__(self, state_path: Path, trades_path: Path, start_cash: float, window: int) -> None:
        self.state_path = state_path
        self.trades_path = trades_path
        self.window = window
        self.state = self._load_state(start_cash)

    def record_observation(self, spread_pct: float) -> list[float]:
        observations = self.state.observations or []
        observations.append(spread_pct)
        self.state.observations = observations[-self.window :]
        return self.state.observations

    def open_position(self, snapshot: SpreadSnapshot, notional_usd: float, entry_zscore: float) -> str:
        if self.state.position is not None:
            return "hold_existing_position"
        self.state.position = SpreadPosition(
            long_venue=snapshot.long_venue,
            short_venue=snapshot.short_venue,
            long_entry_mid=snapshot.long_mid,
            short_entry_mid=snapshot.short_mid,
            notional_usd=notional_usd,
            entry_spread_pct=snapshot.spread_pct,
            entry_zscore=entry_zscore,
            entry_time=utc_now(),
        )
        self._append_trade("OPEN", snapshot, 0.0, "spread_zscore")
        self.save()
        return "opened"

    def close_position(self, snapshot: SpreadSnapshot, reason: str) -> str:
        pnl = self.mark_to_market_pnl(snapshot)
        self.state.cash += pnl
        self.state.realized_pnl += pnl
        self.state.position = None
        self._append_trade("CLOSE", snapshot, pnl, reason)
        self.save()
        return "closed"

    def mark_to_market_pnl(self, snapshot: SpreadSnapshot) -> float:
        position = self.state.position
        if position is None:
            return 0.0
        long_return = (snapshot.long_mid - position.long_entry_mid) / position.long_entry_mid
        short_return = (position.short_entry_mid - snapshot.short_mid) / position.short_entry_mid
        return position.notional_usd * 0.5 * (long_return + short_return)

    def mark_to_market_pct(self, snapshot: SpreadSnapshot) -> float:
        position = self.state.position
        if position is None or position.notional_usd == 0:
            return 0.0
        return self.mark_to_market_pnl(snapshot) / position.notional_usd

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(asdict(self.state), indent=2), encoding="utf-8")

    def append_tick(self, path: Path, snapshot: SpreadSnapshot, spread_zscore: float, outcome: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        exists = path.exists()
        position = self.state.position
        with path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "time",
                    "long_venue",
                    "short_venue",
                    "long_mid",
                    "short_mid",
                    "spread_pct",
                    "zscore",
                    "outcome",
                    "position_long_venue",
                    "position_short_venue",
                    "realized_pnl",
                    "unrealized_pnl",
                    "unrealized_pct",
                ],
            )
            if not exists:
                writer.writeheader()
            unrealized = self.mark_to_market_pnl(snapshot)
            writer.writerow(
                {
                    "time": utc_now(),
                    "long_venue": snapshot.long_venue,
                    "short_venue": snapshot.short_venue,
                    "long_mid": f"{snapshot.long_mid:.2f}",
                    "short_mid": f"{snapshot.short_mid:.2f}",
                    "spread_pct": f"{snapshot.spread_pct:.6f}",
                    "zscore": f"{spread_zscore:.3f}",
                    "outcome": outcome,
                    "position_long_venue": position.long_venue if position else "",
                    "position_short_venue": position.short_venue if position else "",
                    "realized_pnl": f"{self.state.realized_pnl:.6f}",
                    "unrealized_pnl": f"{unrealized:.6f}",
                    "unrealized_pct": f"{self.mark_to_market_pct(snapshot):.6f}",
                }
            )

    def _load_state(self, start_cash: float) -> SpreadState:
        if not self.state_path.exists():
            return SpreadState(cash=start_cash)
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        position_payload = payload.get("position")
        return SpreadState(
            cash=float(payload["cash"]),
            realized_pnl=float(payload.get("realized_pnl", 0.0)),
            position=SpreadPosition(**position_payload) if position_payload else None,
            observations=[float(value) for value in payload.get("observations") or []],
        )

    def _append_trade(self, action: str, snapshot: SpreadSnapshot, pnl: float, reason: str) -> None:
        self.trades_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.trades_path.exists()
        with self.trades_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "time",
                    "action",
                    "long_venue",
                    "short_venue",
                    "long_mid",
                    "short_mid",
                    "spread_pct",
                    "pnl",
                    "reason",
                ],
            )
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "time": utc_now(),
                    "action": action,
                    "long_venue": snapshot.long_venue,
                    "short_venue": snapshot.short_venue,
                    "long_mid": f"{snapshot.long_mid:.2f}",
                    "short_mid": f"{snapshot.short_mid:.2f}",
                    "spread_pct": f"{snapshot.spread_pct:.6f}",
                    "pnl": f"{pnl:.6f}",
                    "reason": reason,
                }
            )


def decide_spread(
    position: SpreadPosition | None,
    current_zscore: float,
    entry_zscore: float,
    exit_zscore: float,
    stop_zscore: float,
    pnl_pct: float,
    stop_loss_pct: float,
) -> SpreadDecision:
    if position is None:
        if abs(current_zscore) >= entry_zscore:
            return SpreadDecision("OPEN", "spread_zscore")
        return SpreadDecision("WAIT", "zscore_inside_entry_threshold")

    if pnl_pct <= stop_loss_pct:
        return SpreadDecision("CLOSE", "stop_loss")
    if abs(current_zscore) <= exit_zscore:
        return SpreadDecision("CLOSE", "spread_converged")
    if abs(current_zscore) >= stop_zscore and abs(current_zscore) > abs(position.entry_zscore):
        return SpreadDecision("CLOSE", "spread_diverged")
    return SpreadDecision("HOLD", "position_active")


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
