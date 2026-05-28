from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from remotetrade.arbitrage import LimitArbitrageOrder, scan_limit_arbitrage
from remotetrade.clients import OrderBook, Quote
from remotetrade.fill_simulator import LimitFillResult, simulate_limit_pair_fill


@dataclass
class PendingLimitPair:
    symbol: str
    buy_venue: str
    sell_venue: str
    buy_limit: float
    sell_limit: float
    net_spread_pct: float
    estimated_profit_usd: float
    notional_usd: float
    qty: float
    placed_at: str

    def to_order(self) -> LimitArbitrageOrder:
        return LimitArbitrageOrder(
            symbol=self.symbol,
            buy_venue=self.buy_venue,
            sell_venue=self.sell_venue,
            buy_limit=self.buy_limit,
            sell_limit=self.sell_limit,
            net_spread_pct=self.net_spread_pct,
            estimated_profit_usd=self.estimated_profit_usd,
            notional_usd=self.notional_usd,
            qty=self.qty,
        )


@dataclass
class LimitPaperState:
    cash: float
    realized_pnl: float = 0.0
    pending: PendingLimitPair | None = None
    both_filled: int = 0
    buy_only: int = 0
    sell_only: int = 0
    expired: int = 0


class LimitPaperBroker:
    def __init__(
        self,
        state_path: Path,
        trades_path: Path,
        ticks_path: Path,
        snapshots_path: Path,
        start_cash: float,
        maker_fee_bps: float,
        taker_fee_bps: float,
        order_ttl_ticks: int,
    ) -> None:
        self.state_path = state_path
        self.trades_path = trades_path
        self.ticks_path = ticks_path
        self.snapshots_path = snapshots_path
        self.maker_fee_bps = maker_fee_bps
        self.taker_fee_bps = taker_fee_bps
        self.order_ttl_ticks = order_ttl_ticks
        self.state = self._load_state(start_cash)

    def evaluate_pending(self, books: list[OrderBook]) -> tuple[str, float, LimitFillResult | None]:
        pending = self.state.pending
        if pending is None:
            return "no_pending", 0.0, None

        by_venue = {book.venue: book for book in books}
        buy_book = by_venue.get(pending.buy_venue)
        sell_book = by_venue.get(pending.sell_venue)
        if buy_book is None or sell_book is None:
            return "missing_book", 0.0, None

        result = simulate_limit_pair_fill(pending.to_order(), buy_book, sell_book)
        if result.outcome == "none":
            if self._pending_age_ticks(pending) >= self.order_ttl_ticks:
                self.state.pending = None
                self.state.expired += 1
                self._append_trade("EXPIRE", pending, 0.0, result.reason)
                self.save()
                return "expired", 0.0, result
            return "pending", 0.0, result

        pnl = self._pnl_for_fill(pending, result)
        self.state.cash += pnl
        self.state.realized_pnl += pnl
        self.state.pending = None
        if result.outcome == "both_filled":
            self.state.both_filled += 1
        elif result.outcome == "buy_only":
            self.state.buy_only += 1
        elif result.outcome == "sell_only":
            self.state.sell_only += 1
        self._append_trade("FILL", pending, pnl, result.outcome)
        self.save()
        return result.outcome, pnl, result

    def place_order(self, order: LimitArbitrageOrder) -> str:
        if self.state.pending is not None:
            return "pending_existing_order"
        self.state.pending = PendingLimitPair(**asdict(order), placed_at=utc_now())
        self._append_trade("PLACE", self.state.pending, 0.0, "new_limit_pair")
        self.save()
        return "placed"

    def append_tick(self, outcome: str, candidate: LimitArbitrageOrder | None, fill_pnl: float) -> None:
        self.ticks_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.ticks_path.exists()
        pending = self.state.pending
        with self.ticks_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "time",
                    "outcome",
                    "realized_pnl",
                    "fill_pnl",
                    "pending_buy_venue",
                    "pending_sell_venue",
                    "pending_buy_limit",
                    "pending_sell_limit",
                    "candidate_buy_venue",
                    "candidate_sell_venue",
                    "candidate_net_spread_pct",
                    "candidate_estimated_profit_usd",
                    "both_filled",
                    "buy_only",
                    "sell_only",
                    "expired",
                ],
            )
            if not exists:
                writer.writeheader()
            writer.writerow(
                {
                    "time": utc_now(),
                    "outcome": outcome,
                    "realized_pnl": f"{self.state.realized_pnl:.6f}",
                    "fill_pnl": f"{fill_pnl:.6f}",
                    "pending_buy_venue": pending.buy_venue if pending else "",
                    "pending_sell_venue": pending.sell_venue if pending else "",
                    "pending_buy_limit": "" if pending is None else f"{pending.buy_limit:.2f}",
                    "pending_sell_limit": "" if pending is None else f"{pending.sell_limit:.2f}",
                    "candidate_buy_venue": candidate.buy_venue if candidate else "",
                    "candidate_sell_venue": candidate.sell_venue if candidate else "",
                    "candidate_net_spread_pct": "" if candidate is None else f"{candidate.net_spread_pct:.6f}",
                    "candidate_estimated_profit_usd": "" if candidate is None else f"{candidate.estimated_profit_usd:.4f}",
                    "both_filled": self.state.both_filled,
                    "buy_only": self.state.buy_only,
                    "sell_only": self.state.sell_only,
                    "expired": self.state.expired,
                }
            )

    def append_snapshots(self, books: list[OrderBook]) -> None:
        self.snapshots_path.parent.mkdir(parents=True, exist_ok=True)
        with self.snapshots_path.open("a", encoding="utf-8") as handle:
            for book in books:
                payload = {
                    "time": utc_now(),
                    "venue": book.venue,
                    "symbol": book.symbol,
                    "observed_at": book.observed_at,
                    "bids": [[level.price, level.qty] for level in book.bids[:20]],
                    "asks": [[level.price, level.qty] for level in book.asks[:20]],
                }
                handle.write(json.dumps(payload, separators=(",", ":")) + "\n")

    def save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(asdict(self.state), indent=2), encoding="utf-8")

    def _load_state(self, start_cash: float) -> LimitPaperState:
        if not self.state_path.exists():
            return LimitPaperState(cash=start_cash)
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        pending_payload = payload.get("pending")
        return LimitPaperState(
            cash=float(payload["cash"]),
            realized_pnl=float(payload.get("realized_pnl", 0.0)),
            pending=PendingLimitPair(**pending_payload) if pending_payload else None,
            both_filled=int(payload.get("both_filled", 0)),
            buy_only=int(payload.get("buy_only", 0)),
            sell_only=int(payload.get("sell_only", 0)),
            expired=int(payload.get("expired", 0)),
        )

    def _append_trade(self, action: str, pending: PendingLimitPair, pnl: float, reason: str) -> None:
        self.trades_path.parent.mkdir(parents=True, exist_ok=True)
        exists = self.trades_path.exists()
        with self.trades_path.open("a", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "time",
                    "action",
                    "buy_venue",
                    "sell_venue",
                    "buy_limit",
                    "sell_limit",
                    "qty",
                    "estimated_profit_usd",
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
                    "buy_venue": pending.buy_venue,
                    "sell_venue": pending.sell_venue,
                    "buy_limit": f"{pending.buy_limit:.2f}",
                    "sell_limit": f"{pending.sell_limit:.2f}",
                    "qty": f"{pending.qty:.10f}",
                    "estimated_profit_usd": f"{pending.estimated_profit_usd:.6f}",
                    "pnl": f"{pnl:.6f}",
                    "reason": reason,
                }
            )

    def _pending_age_ticks(self, pending: PendingLimitPair) -> int:
        if not self.ticks_path.exists():
            return 0
        with self.ticks_path.open(newline="", encoding="utf-8") as handle:
            return sum(1 for row in csv.DictReader(handle) if row.get("pending_buy_venue") == pending.buy_venue)

    def _pnl_for_fill(self, pending: PendingLimitPair, result: LimitFillResult) -> float:
        maker_fee_pct = self.maker_fee_bps / 10_000
        taker_fee_pct = self.taker_fee_bps / 10_000
        buy_notional = pending.buy_limit * pending.qty
        sell_notional = pending.sell_limit * pending.qty
        if result.outcome == "both_filled":
            fees = (buy_notional + sell_notional) * maker_fee_pct
            return sell_notional - buy_notional - fees
        filled_notional = buy_notional if result.buy_filled else sell_notional
        return -result.hedge_cost_usd - filled_notional * (maker_fee_pct + taker_fee_pct)


def quote_from_books(books: list[OrderBook]) -> list[Quote]:
    return [
        Quote(book.venue, book.symbol, book.best_bid, book.best_ask, {})
        for book in books
        if book.bids and book.asks
    ]


def find_limit_candidate(
    books: list[OrderBook],
    notional_usd: float,
    maker_fee_bps: float,
    min_net_spread_pct: float,
    price_improvement_bps: float,
) -> LimitArbitrageOrder | None:
    orders = scan_limit_arbitrage(
        quote_from_books(books),
        notional_usd,
        maker_fee_bps,
        min_net_spread_pct,
        price_improvement_bps,
    )
    return orders[0] if orders else None


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
