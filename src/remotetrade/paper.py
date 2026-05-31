from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path


@dataclass
class Position:
    side: str
    asset_id: str
    qty: float
    notional_usd: float
    entry_price: float
    entry_time: str
    market_slug: str
    entry_signal: float


@dataclass
class PaperState:
    cash: float
    realized_pnl: float = 0.0
    position: Position | None = None
    last_market_slug: str | None = None
    last_market_price: float | None = None
    last_observed_at: str | None = None
    observations: dict[str, float] | None = None


class PaperBroker:
    def __init__(
        self,
        state_path: Path,
        trades_path: Path,
        start_cash: float,
        ticks_path: Path | None = None,
        round_trip_cost_bps: float = 0.0,
    ) -> None:
        self.state_path = state_path
        self.trades_path = trades_path
        self.ticks_path = ticks_path
        self.round_trip_cost_bps = round_trip_cost_bps
        self.state = self._load_state(start_cash)

    def open_position(
        self,
        side: str,
        notional_usd: float,
        price: float,
        market_slug: str,
        signal: float,
        asset_id: str,
    ) -> str:
        if self.state.position is not None:
            return "hold_existing_position"
        qty = notional_usd / price
        self.state.position = Position(
            side=side,
            asset_id=asset_id,
            qty=qty,
            notional_usd=notional_usd,
            entry_price=price,
            entry_time=utc_now(),
            market_slug=market_slug,
            entry_signal=signal,
        )
        self._append_trade("OPEN", side, qty, price, 0.0, market_slug, signal, asset_id=asset_id)
        self.save()
        return "opened"

    def close_position(self, price: float, signal: float, reason: str) -> str:
        position = self.state.position
        if position is None:
            return "no_position"
        multiplier = 1.0 if position.side == "LONG" else -1.0
        gross_pnl = (price - position.entry_price) * position.qty * multiplier
        round_trip_cost = position.notional_usd * self.round_trip_cost_bps / 10_000
        pnl = gross_pnl - round_trip_cost
        self.state.cash += pnl
        self.state.realized_pnl += pnl
        self.state.position = None
        self._append_trade(
            "CLOSE",
            position.side,
            position.qty,
            price,
            pnl,
            position.market_slug,
            signal,
            reason,
            asset_id=position.asset_id,
        )
        self.save()
        return "closed"

    def record_observation(self, market_slug: str, market_price: float, observation_key: str | None = None) -> float | None:
        key = observation_key or market_slug
        observations = self.state.observations or {}
        if key in observations:
            delta = market_price - observations[key]
        elif self.state.last_market_slug != market_slug:
            delta = None
        elif self.state.last_market_price is None:
            delta = None
        else:
            delta = market_price - self.state.last_market_price

        observations[key] = market_price
        self.state.observations = observations
        self.state.last_market_slug = market_slug
        self.state.last_market_price = market_price
        self.state.last_observed_at = utc_now()
        return delta

    def mark_to_market_pnl(self, price: float) -> float:
        position = self.state.position
        if position is None:
            return 0.0
        multiplier = 1.0 if position.side == "LONG" else -1.0
        return (price - position.entry_price) * position.qty * multiplier

    def mark_to_market_pct(self, price: float) -> float:
        position = self.state.position
        if position is None or position.notional_usd == 0:
            return 0.0
        return self.mark_to_market_pnl(price) / position.notional_usd

    def size_for_trade(self, risk_fraction: float, max_trade_size_usd: float, min_trade_size_usd: float) -> float:
        equity = max(self.state.cash, 0.0)
        notional = min(max_trade_size_usd, equity * risk_fraction)
        return notional if notional >= min_trade_size_usd else 0.0

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = asdict(self.state)
        self.state_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def append_tick(
        self,
        pattern_id: str,
        market_slug: str,
        asset_id: str,
        price: float,
        signal_price: float,
        odds_delta: float | None,
        outcome: str,
        unrealized_pnl: float,
        unrealized_pct: float,
    ) -> None:
        if self.ticks_path is None:
            return

        self.ticks_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.ticks_path.exists()
        position = self.state.position
        with self.ticks_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "time",
                    "pattern_id",
                    "market_slug",
                    "asset_id",
                    "price",
                    "signal_price",
                    "odds_delta",
                    "outcome",
                    "position_side",
                    "position_asset_id",
                    "realized_pnl",
                    "unrealized_pnl",
                    "unrealized_pct",
                ],
            )
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "time": utc_now(),
                    "pattern_id": pattern_id,
                    "market_slug": market_slug,
                    "asset_id": asset_id,
                    "price": f"{price:.6f}",
                    "signal_price": f"{signal_price:.6f}",
                    "odds_delta": "" if odds_delta is None else f"{odds_delta:.6f}",
                    "outcome": outcome,
                    "position_side": position.side if position else "",
                    "position_asset_id": position.asset_id if position else "",
                    "realized_pnl": f"{self.state.realized_pnl:.6f}",
                    "unrealized_pnl": f"{unrealized_pnl:.6f}",
                    "unrealized_pct": f"{unrealized_pct:.6f}",
                }
            )

    def _load_state(self, start_cash: float) -> PaperState:
        if not self.state_path.exists():
            return PaperState(cash=start_cash)
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        position_payload = payload.get("position")
        if position_payload and "asset_id" not in position_payload:
            position_payload["asset_id"] = position_payload.get("market_slug", "UNKNOWN")
        position = Position(**position_payload) if position_payload else None
        return PaperState(
            cash=float(payload["cash"]),
            realized_pnl=float(payload.get("realized_pnl", 0.0)),
            position=position,
            last_market_slug=payload.get("last_market_slug"),
            last_market_price=payload.get("last_market_price"),
            last_observed_at=payload.get("last_observed_at"),
            observations=payload.get("observations"),
        )

    def _append_trade(
        self,
        action: str,
        side: str,
        qty: float,
        price: float,
        pnl: float,
        market_slug: str,
        signal: float,
        reason: str = "",
        asset_id: str = "",
    ) -> None:
        self.trades_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.trades_path.exists()
        with self.trades_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "time",
                    "action",
                    "side",
                    "asset_id",
                    "qty",
                    "price",
                    "pnl",
                    "market_slug",
                    "signal",
                    "reason",
                ],
            )
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "time": utc_now(),
                    "action": action,
                    "side": side,
                    "asset_id": asset_id,
                    "qty": f"{qty:.10f}",
                    "price": f"{price:.2f}",
                    "pnl": f"{pnl:.2f}",
                    "market_slug": market_slug,
                    "signal": f"{signal:.4f}",
                    "reason": reason,
                }
            )


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
