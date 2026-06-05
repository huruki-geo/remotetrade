from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests
import websocket

from remotetrade.archive import MAX_EVENT_FILE_BYTES, rotate_file
from remotetrade.bitbank_poly_maker import PolymarketUpQuote, latest_polymarket_up_quote
from remotetrade.patterns import Pattern, load_patterns


JST = ZoneInfo("Asia/Tokyo")


@dataclass(frozen=True)
class CoincheckTrade:
    trade_id: str
    time: str
    side: str
    price: float
    amount: float


@dataclass
class MakerOrder:
    purpose: str
    side: str
    price: float
    placed_at: str
    signal: float


@dataclass
class MakerPosition:
    side: str
    entry_price: float
    entry_time: str
    signal: float


@dataclass
class CoincheckPolyMakerState:
    observations: list[tuple[str, float]] = field(default_factory=list)
    market_slug: str = ""
    pending_order: MakerOrder | None = None
    position: MakerPosition | None = None
    realized_pnl_bps: float = 0.0
    closed_trades: int = 0
    previous_signal: float = 0.0
    last_quote_time: str = ""


@dataclass(frozen=True)
class MakerPaperEvent:
    time: str
    pattern_id: str
    event: str
    market_slug: str
    polymarket_up_price: float
    signal: float
    bid: float
    ask: float
    order_side: str
    order_price: float | None
    position_side: str
    entry_jst_hour: int | None
    gross_pnl_bps: float
    maker_fee_bps: float
    net_pnl_bps: float
    realized_pnl_bps: float
    closed_trades: int


class CoincheckPublicClient:
    def __init__(
        self,
        base_url: str = "https://coincheck.com",
        websocket_url: str = "wss://ws-api.coincheck.com/",
        timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.websocket_url = websocket_url
        self.timeout = timeout

    def get_order_book(self, pair: str) -> dict[str, Any]:
        response = requests.get(f"{self.base_url}/api/order_books", params={"pair": pair}, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def connect(self, pair: str) -> websocket.WebSocket:
        connection = websocket.create_connection(self.websocket_url, timeout=self.timeout)
        connection.send(json.dumps({"type": "subscribe", "channel": f"{pair}-orderbook"}))
        connection.send(json.dumps({"type": "subscribe", "channel": f"{pair}-trades"}))
        return connection


class CoincheckOrderBook:
    def __init__(self, snapshot: dict[str, Any]) -> None:
        self.bids = _levels(snapshot.get("bids"))
        self.asks = _levels(snapshot.get("asks"))

    @property
    def best_bid(self) -> float:
        return max(self.bids)

    @property
    def best_ask(self) -> float:
        return min(self.asks)

    def apply(self, payload: dict[str, Any]) -> None:
        _apply_levels(self.bids, payload.get("bids"))
        _apply_levels(self.asks, payload.get("asks"))

    def best_prices(self) -> tuple[float, float]:
        bid = self.best_bid
        ask = self.best_ask
        if ask <= bid:
            raise RuntimeError(f"Coincheck local order book is crossed: bid={bid:g} ask={ask:g}")
        return bid, ask


class CoincheckPolyMakerPaper:
    def __init__(
        self,
        pattern: Pattern,
        state_path: Path,
        events_path: Path,
        signal_window_seconds: float = 15.0,
        entry_ttl_seconds: float = 3.0,
        exit_ttl_seconds: float = 3.0,
        maker_fee_bps: float = 0.0,
        allowed_sides: tuple[str, ...] = ("LONG", "SHORT"),
        allowed_jst_hours: tuple[int, ...] = (),
    ) -> None:
        self.pattern = pattern
        self.state_path = state_path
        self.events_path = events_path
        self.signal_window_seconds = signal_window_seconds
        self.entry_ttl_seconds = entry_ttl_seconds
        self.exit_ttl_seconds = exit_ttl_seconds
        self.maker_fee_bps = maker_fee_bps
        self.allowed_sides = allowed_sides
        self.allowed_jst_hours = allowed_jst_hours
        self.state = self._load_state()

    def tick(
        self,
        quote: PolymarketUpQuote,
        bid: float,
        ask: float,
        trades: list[CoincheckTrade],
        now: datetime | None = None,
    ) -> MakerPaperEvent:
        now = now or datetime.now(UTC)
        signal = self._record_observation(quote, now)
        order = self.state.pending_order
        event = "observed"
        gross_pnl_bps = 0.0
        net_pnl_bps = 0.0
        event_position_side = ""
        event_entry_jst_hour: int | None = None

        if order and self._is_filled(order, trades):
            if order.purpose == "entry":
                side = "LONG" if order.side == "BUY" else "SHORT"
                self.state.position = MakerPosition(side, order.price, now.isoformat(), order.signal)
                event = "entry_filled"
            else:
                gross_pnl_bps = self._gross_pnl_bps(self.state.position, order.price)
                net_pnl_bps = gross_pnl_bps - self.maker_fee_bps * 2
                if self.state.position:
                    event_position_side = self.state.position.side
                    event_entry_jst_hour = _datetime(self.state.position.entry_time).astimezone(JST).hour
                self.state.realized_pnl_bps += net_pnl_bps
                self.state.closed_trades += 1
                self.state.position = None
                event = "exit_filled"
            self.state.pending_order = None
        elif order and self._age_seconds(order.placed_at, now) >= self._ttl_seconds(order):
            self.state.pending_order = None
            event = f"{order.purpose}_cancelled"

        if self.state.pending_order is None:
            if self.state.position:
                reason = self._exit_reason(self.state.position, signal, bid, ask, now)
                if reason:
                    self.state.pending_order = self._exit_order(self.state.position, bid, ask, now)
                    event = f"exit_quoted:{reason}"
            else:
                side = self._entry_side(signal)
                if side and self._entry_allowed(side, now):
                    self.state.pending_order = self._entry_order(side, signal, bid, ask, now)
                    event = "entry_quoted"

        self.state.previous_signal = signal
        self._save_state()
        position = self.state.position
        if position:
            event_position_side = position.side
            event_entry_jst_hour = _datetime(position.entry_time).astimezone(JST).hour
        elif self.state.pending_order and self.state.pending_order.purpose == "entry":
            event_entry_jst_hour = _datetime(self.state.pending_order.placed_at).astimezone(JST).hour
        paper_event = MakerPaperEvent(
            time=now.isoformat(),
            pattern_id=self.pattern.id,
            event=event,
            market_slug=quote.market_slug,
            polymarket_up_price=quote.price,
            signal=signal,
            bid=bid,
            ask=ask,
            order_side=self.state.pending_order.side if self.state.pending_order else "",
            order_price=self.state.pending_order.price if self.state.pending_order else None,
            position_side=event_position_side,
            entry_jst_hour=event_entry_jst_hour,
            gross_pnl_bps=gross_pnl_bps,
            maker_fee_bps=self.maker_fee_bps,
            net_pnl_bps=net_pnl_bps,
            realized_pnl_bps=self.state.realized_pnl_bps,
            closed_trades=self.state.closed_trades,
        )
        append_maker_paper_event(self.events_path, paper_event)
        return paper_event

    def _record_observation(self, quote: PolymarketUpQuote, now: datetime) -> float:
        if quote.market_slug != self.state.market_slug:
            self.state.market_slug = quote.market_slug
            self.state.observations = []
            self.state.previous_signal = 0.0
            self.state.last_quote_time = ""
            if self.state.pending_order and self.state.pending_order.purpose == "entry":
                self.state.pending_order = None
        cutoff = now.timestamp() - self.signal_window_seconds
        observations = [
            (raw_time, price)
            for raw_time, price in self.state.observations
            if _datetime(raw_time).timestamp() >= cutoff
        ]
        if quote.time != self.state.last_quote_time:
            observations.append((quote.time, quote.price))
            observations.sort()
            self.state.last_quote_time = quote.time
        self.state.observations = observations
        return quote.price - observations[0][1] if observations else 0.0

    def _exit_reason(self, position: MakerPosition, signal: float, bid: float, ask: float, now: datetime) -> str:
        mark_price = bid if position.side == "LONG" else ask
        pnl_pct = self._gross_pnl_bps(position, mark_price) / 10_000
        if pnl_pct >= self.pattern.take_profit_pct:
            return "take_profit"
        if pnl_pct <= self.pattern.stop_loss_pct:
            return "stop_loss"
        if self._age_seconds(position.entry_time, now) >= self.pattern.hold_seconds:
            return "hold_window_elapsed"
        if position.side == "LONG" and signal <= -self.pattern.strong_threshold:
            return "strong_reverse_signal"
        if position.side == "SHORT" and signal >= self.pattern.strong_threshold:
            return "strong_reverse_signal"
        return ""

    def _entry_side(self, signal: float) -> str:
        crossed_up = signal >= self.pattern.entry_threshold and self.state.previous_signal < self.pattern.entry_threshold
        crossed_down = signal <= -self.pattern.entry_threshold and self.state.previous_signal > -self.pattern.entry_threshold
        if crossed_up:
            return "LONG"
        if crossed_down:
            return "SHORT"
        return ""

    def _entry_allowed(self, side: str, now: datetime) -> bool:
        return side in self.allowed_sides and (not self.allowed_jst_hours or now.astimezone(JST).hour in self.allowed_jst_hours)

    @staticmethod
    def _entry_order(side: str, signal: float, bid: float, ask: float, now: datetime) -> MakerOrder:
        return MakerOrder("entry", "BUY" if side == "LONG" else "SELL", bid if side == "LONG" else ask, now.isoformat(), signal)

    @staticmethod
    def _exit_order(position: MakerPosition, bid: float, ask: float, now: datetime) -> MakerOrder:
        side = "SELL" if position.side == "LONG" else "BUY"
        return MakerOrder("exit", side, ask if side == "SELL" else bid, now.isoformat(), position.signal)

    @staticmethod
    def _is_filled(order: MakerOrder, trades: list[CoincheckTrade]) -> bool:
        if order.side == "BUY":
            return any(trade.side == "sell" and trade.price <= order.price for trade in trades)
        return any(trade.side == "buy" and trade.price >= order.price for trade in trades)

    def _ttl_seconds(self, order: MakerOrder) -> float:
        return self.entry_ttl_seconds if order.purpose == "entry" else self.exit_ttl_seconds

    @staticmethod
    def _gross_pnl_bps(position: MakerPosition | None, exit_price: float) -> float:
        if position is None:
            return 0.0
        multiplier = 1.0 if position.side == "LONG" else -1.0
        return (exit_price / position.entry_price - 1) * 10_000 * multiplier

    @staticmethod
    def _age_seconds(raw_time: str, now: datetime) -> float:
        return (now - _datetime(raw_time)).total_seconds()

    def _load_state(self) -> CoincheckPolyMakerState:
        if not self.state_path.exists():
            return CoincheckPolyMakerState()
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        order = payload.get("pending_order")
        position = payload.get("position")
        return CoincheckPolyMakerState(
            observations=[tuple(row) for row in payload.get("observations") or []],
            market_slug=str(payload.get("market_slug") or ""),
            pending_order=MakerOrder(**order) if order else None,
            position=MakerPosition(**position) if position else None,
            realized_pnl_bps=float(payload.get("realized_pnl_bps") or 0.0),
            closed_trades=int(payload.get("closed_trades") or 0),
            previous_signal=float(payload.get("previous_signal") or 0.0),
            last_quote_time=str(payload.get("last_quote_time") or ""),
        )

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(asdict(self.state), indent=2), encoding="utf-8")


def run_coincheck_poly_maker_paper(
    data_dir: Path,
    gamma_url: str,
    patterns_path: Path,
    pair: str = "btc_jpy",
    poll_seconds: float = 1.0,
    signal_window_seconds: float = 15.0,
    entry_ttl_seconds: float = 3.0,
    exit_ttl_seconds: float = 3.0,
    maker_fee_bps: float = 0.0,
    max_stale_seconds: float = 10.0,
    allowed_sides: tuple[str, ...] = ("LONG", "SHORT"),
    allowed_jst_hours: tuple[int, ...] = (),
    client: CoincheckPublicClient | None = None,
) -> None:
    client = client or CoincheckPublicClient()
    patterns = load_patterns(patterns_path)
    brokers = [
        CoincheckPolyMakerPaper(
            pattern,
            data_dir / f"coincheck_poly_maker_{pattern.id}_state.json",
            data_dir / "coincheck_poly_maker_events.csv",
            signal_window_seconds,
            entry_ttl_seconds,
            exit_ttl_seconds,
            maker_fee_bps,
            allowed_sides,
            allowed_jst_hours,
        )
        for pattern in patterns
    ]
    while True:
        connection: websocket.WebSocket | None = None
        try:
            book = CoincheckOrderBook(client.get_order_book(pair))
            connection = client.connect(pair)
            connection.settimeout(min(poll_seconds, 1.0))
            trades: list[CoincheckTrade] = []
            last_market_event_at = time.monotonic()
            next_tick_at = 0.0
            while True:
                try:
                    raw_message = connection.recv()
                    if raw_message:
                        book_update, new_trades = parse_coincheck_websocket_message(raw_message, pair)
                        if book_update:
                            book.apply(book_update)
                        trades.extend(new_trades)
                        last_market_event_at = time.monotonic()
                except websocket.WebSocketTimeoutException:
                    pass

                now = time.monotonic()
                if now < next_tick_at:
                    continue
                next_tick_at = now + poll_seconds
                if now - last_market_event_at > max_stale_seconds:
                    raise RuntimeError("Coincheck public WebSocket market data is stale.")
                quote = latest_polymarket_up_quote(data_dir / "polymarket_btc_5m_clob.jsonl", gamma_url)
                if quote is None or _age_seconds(quote.time) > max_stale_seconds:
                    raise RuntimeError("Polymarket CLOB quote is stale or unavailable.")
                bid, ask = book.best_prices()
                for broker in brokers:
                    event = broker.tick(quote, bid, ask, trades)
                    print(format_maker_paper_event(event), flush=True)
                trades = []
        except Exception as exc:
            print(f"coincheck poly maker reconnecting after error: {exc}", flush=True)
            time.sleep(3)
        finally:
            if connection is not None:
                connection.close()


def parse_coincheck_websocket_message(raw_message: str, pair: str) -> tuple[dict[str, Any] | None, list[CoincheckTrade]]:
    payload = json.loads(raw_message)
    if isinstance(payload, list) and len(payload) == 2 and payload[0] == pair and isinstance(payload[1], dict):
        return payload[1], []
    trades: list[CoincheckTrade] = []
    if isinstance(payload, list):
        for row in payload:
            if not isinstance(row, list) or len(row) < 6 or row[2] != pair:
                continue
            trades.append(CoincheckTrade(str(row[1]), str(row[0]), str(row[5]), float(row[3]), float(row[4])))
    return None, trades


def append_maker_paper_event(path: Path, event: MakerPaperEvent) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rotate_file(path, MAX_EVENT_FILE_BYTES)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MakerPaperEvent.__dataclass_fields__))
        if not exists:
            writer.writeheader()
        writer.writerow(asdict(event))


def format_maker_paper_event(event: MakerPaperEvent) -> str:
    return (
        f"[CoincheckPolyMaker {event.pattern_id}] {event.event}: up={event.polymarket_up_price:.3f} "
        f"signal={event.signal:+.3f} bid={event.bid:g} ask={event.ask:g} "
        f"order={event.order_side}@{event.order_price} position={event.position_side or 'NONE'} "
        f"net={event.net_pnl_bps:+.2f}bps realized={event.realized_pnl_bps:+.2f}bps "
        f"closed={event.closed_trades}"
    )


def _levels(raw_levels: Any) -> dict[float, float]:
    return {float(price): float(amount) for price, amount in (raw_levels or []) if float(amount) > 0}


def _apply_levels(levels: dict[float, float], raw_levels: Any) -> None:
    for raw_price, raw_amount in raw_levels or []:
        price = float(raw_price)
        amount = float(raw_amount)
        if amount > 0:
            levels[price] = amount
        else:
            levels.pop(price, None)


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _age_seconds(value: str) -> float:
    return (datetime.now(UTC) - _datetime(value)).total_seconds()
