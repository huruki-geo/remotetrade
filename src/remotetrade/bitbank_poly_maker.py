from __future__ import annotations

import csv
import json
import time
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from remotetrade.clients import PolymarketClient
from remotetrade.polymarket_clob import market_asset_ids
from remotetrade.venue_discovery import BitbankPublicClient


_UP_ASSET_IDS: dict[str, str] = {}
_UNAVAILABLE_MARKET_SLUGS: set[str] = set()


@dataclass(frozen=True)
class PolymarketUpQuote:
    time: str
    market_slug: str
    price: float


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
class BitbankPolyMakerState:
    observations: list[tuple[str, float]] = field(default_factory=list)
    pending_order: MakerOrder | None = None
    position: MakerPosition | None = None
    realized_pnl_bps: float = 0.0
    closed_trades: int = 0
    previous_signal: float = 0.0


@dataclass(frozen=True)
class MakerPaperEvent:
    time: str
    event: str
    market_slug: str
    polymarket_up_price: float
    signal: float
    bid: float
    ask: float
    order_side: str
    order_price: float | None
    position_side: str
    gross_pnl_bps: float
    maker_fee_bps: float
    net_pnl_bps: float
    realized_pnl_bps: float


class BitbankPolyMakerPaper:
    def __init__(
        self,
        state_path: Path,
        events_path: Path,
        signal_window_seconds: float = 10.0,
        signal_threshold: float = 0.05,
        entry_ttl_seconds: float = 3.0,
        exit_ttl_seconds: float = 3.0,
        hold_seconds: float = 60.0,
    ) -> None:
        self.state_path = state_path
        self.events_path = events_path
        self.signal_window_seconds = signal_window_seconds
        self.signal_threshold = signal_threshold
        self.entry_ttl_seconds = entry_ttl_seconds
        self.exit_ttl_seconds = exit_ttl_seconds
        self.hold_seconds = hold_seconds
        self.state = self._load_state()

    def tick(
        self,
        quote: PolymarketUpQuote,
        bid: float,
        ask: float,
        maker_fee_bps: float,
        now: datetime | None = None,
    ) -> MakerPaperEvent:
        now = now or datetime.now(UTC)
        signal = self._record_observation(quote, now)
        order = self.state.pending_order
        event = "observed"
        gross_pnl_bps = 0.0
        net_pnl_bps = 0.0

        if order and self._is_filled(order, bid, ask):
            if order.purpose == "entry":
                side = "LONG" if order.side == "BUY" else "SHORT"
                self.state.position = MakerPosition(side, order.price, now.isoformat(), order.signal)
                event = "entry_filled"
            else:
                gross_pnl_bps = self._gross_pnl_bps(self.state.position, order.price)
                net_pnl_bps = gross_pnl_bps - maker_fee_bps * 2
                self.state.realized_pnl_bps += net_pnl_bps
                self.state.closed_trades += 1
                self.state.position = None
                event = "exit_filled"
            self.state.pending_order = None
        elif order and self._age_seconds(order.placed_at, now) >= self._ttl_seconds(order):
            self.state.pending_order = None
            event = f"{order.purpose}_cancelled"

        if self.state.pending_order is None:
            if self.state.position and self._age_seconds(self.state.position.entry_time, now) >= self.hold_seconds:
                self.state.pending_order = self._exit_order(self.state.position, bid, ask, now)
                event = "exit_quoted"
            elif (
                self.state.position is None
                and abs(signal) >= self.signal_threshold
                and abs(self.state.previous_signal) < self.signal_threshold
            ):
                self.state.pending_order = self._entry_order(signal, bid, ask, now)
                event = "entry_quoted"

        self.state.previous_signal = signal
        self._save_state()
        paper_event = MakerPaperEvent(
            time=now.isoformat(),
            event=event,
            market_slug=quote.market_slug,
            polymarket_up_price=quote.price,
            signal=signal,
            bid=bid,
            ask=ask,
            order_side=self.state.pending_order.side if self.state.pending_order else "",
            order_price=self.state.pending_order.price if self.state.pending_order else None,
            position_side=self.state.position.side if self.state.position else "",
            gross_pnl_bps=gross_pnl_bps,
            maker_fee_bps=maker_fee_bps,
            net_pnl_bps=net_pnl_bps,
            realized_pnl_bps=self.state.realized_pnl_bps,
        )
        append_maker_paper_event(self.events_path, paper_event)
        return paper_event

    def _record_observation(self, quote: PolymarketUpQuote, now: datetime) -> float:
        cutoff = now.timestamp() - self.signal_window_seconds
        observations = [
            (raw_time, price)
            for raw_time, price in self.state.observations
            if _datetime(raw_time).timestamp() >= cutoff
        ]
        observations.append((quote.time, quote.price))
        observations.sort()
        self.state.observations = observations
        return quote.price - observations[0][1]

    @staticmethod
    def _entry_order(signal: float, bid: float, ask: float, now: datetime) -> MakerOrder:
        return MakerOrder("entry", "BUY" if signal > 0 else "SELL", bid if signal > 0 else ask, now.isoformat(), signal)

    @staticmethod
    def _exit_order(position: MakerPosition, bid: float, ask: float, now: datetime) -> MakerOrder:
        side = "SELL" if position.side == "LONG" else "BUY"
        return MakerOrder("exit", side, ask if side == "SELL" else bid, now.isoformat(), position.signal)

    @staticmethod
    def _is_filled(order: MakerOrder, bid: float, ask: float) -> bool:
        return ask <= order.price if order.side == "BUY" else bid >= order.price

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

    def _load_state(self) -> BitbankPolyMakerState:
        if not self.state_path.exists():
            return BitbankPolyMakerState()
        payload = json.loads(self.state_path.read_text(encoding="utf-8"))
        order = payload.get("pending_order")
        position = payload.get("position")
        return BitbankPolyMakerState(
            observations=[tuple(row) for row in payload.get("observations") or []],
            pending_order=MakerOrder(**order) if order else None,
            position=MakerPosition(**position) if position else None,
            realized_pnl_bps=float(payload.get("realized_pnl_bps") or 0.0),
            closed_trades=int(payload.get("closed_trades") or 0),
            previous_signal=float(payload.get("previous_signal") or 0.0),
        )

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(asdict(self.state), indent=2), encoding="utf-8")


def latest_polymarket_up_quote(path: Path, gamma_url: str, max_bytes: int = 512_000) -> PolymarketUpQuote | None:
    rows = _tail_jsonl(path, max_bytes)
    if not rows:
        return None
    client = PolymarketClient(gamma_url)
    for row in reversed(rows):
        slug = str(row.get("market_slug") or "")
        event = row.get("event")
        if not slug or not isinstance(event, dict):
            continue
        up_asset_id = _UP_ASSET_IDS.get(slug)
        if up_asset_id is None:
            if slug in _UNAVAILABLE_MARKET_SLUGS:
                continue
            try:
                market = client.find_market(slug, "")
            except RuntimeError:
                _UNAVAILABLE_MARKET_SLUGS.add(slug)
                continue
            asset_ids = market_asset_ids(market)
            if not asset_ids:
                continue
            up_asset_id = asset_ids[0]
            _UP_ASSET_IDS[slug] = up_asset_id
        if not up_asset_id:
            continue
        price = _up_price(event, up_asset_id)
        if price is not None:
            return PolymarketUpQuote(str(row.get("received_at") or ""), slug, price)
    return None


def run_bitbank_poly_maker_paper(
    data_dir: Path,
    gamma_url: str,
    pair: str = "btc_jpy",
    poll_seconds: float = 1.0,
    signal_window_seconds: float = 10.0,
    signal_threshold: float = 0.05,
    entry_ttl_seconds: float = 3.0,
    exit_ttl_seconds: float = 3.0,
    hold_seconds: float = 60.0,
) -> None:
    client = BitbankPublicClient()
    rule = next(rule for rule in client.get_pairs() if str(rule["name"]) == pair)
    maker_fee_bps = float(rule["maker_fee_rate_quote"]) * 10_000
    broker = BitbankPolyMakerPaper(
        data_dir / "bitbank_poly_maker_state.json",
        data_dir / "bitbank_poly_maker_events.csv",
        signal_window_seconds,
        signal_threshold,
        entry_ttl_seconds,
        exit_ttl_seconds,
        hold_seconds,
    )
    last_quote_time = ""
    next_poll_at = 0.0
    while True:
        try:
            now = time.monotonic()
            if now < next_poll_at:
                time.sleep(next_poll_at - now)
            next_poll_at = time.monotonic() + poll_seconds
            quote = latest_polymarket_up_quote(data_dir / "polymarket_btc_5m_clob.jsonl", gamma_url)
            if quote is None or quote.time == last_quote_time:
                continue
            book = client.get_order_book(pair)
            bid = float(book["bids"][0][0])
            ask = float(book["asks"][0][0])
            event = broker.tick(quote, bid, ask, maker_fee_bps)
            last_quote_time = quote.time
            print(format_maker_paper_event(event), flush=True)
        except Exception as exc:
            print(f"bitbank poly maker reconnecting after error: {exc}", flush=True)


def append_maker_paper_event(path: Path, event: MakerPaperEvent) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MakerPaperEvent.__dataclass_fields__))
        if not exists:
            writer.writeheader()
        writer.writerow(asdict(event))


def format_maker_paper_event(event: MakerPaperEvent) -> str:
    return (
        f"[BitbankPolyMaker] {event.event}: up={event.polymarket_up_price:.3f} signal={event.signal:+.3f} "
        f"bid={event.bid:g} ask={event.ask:g} order={event.order_side}@{event.order_price} "
        f"position={event.position_side or 'NONE'} net={event.net_pnl_bps:+.2f}bps "
        f"realized={event.realized_pnl_bps:+.2f}bps"
    )


def _up_price(event: dict[str, Any], up_asset_id: str) -> float | None:
    event_type = str(event.get("event_type") or "")
    if event_type == "price_change":
        for change in event.get("price_changes") or []:
            if str(change.get("asset_id") or "") != up_asset_id:
                continue
            bid = _float_or_none(change.get("best_bid"))
            ask = _float_or_none(change.get("best_ask"))
            if bid is not None and ask is not None:
                return (bid + ask) / 2
    if str(event.get("asset_id") or "") != up_asset_id:
        return None
    if event_type == "book":
        bids = [_float_or_none(row.get("price")) for row in event.get("bids") or []]
        asks = [_float_or_none(row.get("price")) for row in event.get("asks") or []]
        bids = [price for price in bids if price is not None]
        asks = [price for price in asks if price is not None]
        return (max(bids) + min(asks)) / 2 if bids and asks else None
    if event_type == "last_trade_price":
        return _float_or_none(event.get("price"))
    return None


def _tail_jsonl(path: Path, max_bytes: int) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("rb") as handle:
        size = path.stat().st_size
        if size > max_bytes:
            handle.seek(size - max_bytes)
            handle.readline()
        rows: list[dict[str, Any]] = []
        for line in handle:
            try:
                payload = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                rows.append(payload)
        return rows


def _datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
