from __future__ import annotations

import json
from bisect import bisect_right
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from collections.abc import Iterator
from typing import Any


@dataclass(frozen=True)
class MarketFeature:
    market_slug: str
    time: str
    asset_id: str
    best_bid: float
    best_ask: float
    mid: float
    spread: float
    imbalance: float
    multi_level_imbalance: float
    multi_level_ofi: float
    trade_imbalance: float
    seconds_remaining: float | None
    chainlink_btc_usd: float | None
    binance_btc_usdt: float | None
    binance_chainlink_basis_pct: float | None
    last_trade_price: float | None


@dataclass(frozen=True)
class ReplayCandidate:
    market_slug: str
    time: str
    asset_id: str
    entry_price: float
    exit_price: float
    pnl_per_share: float
    won: bool
    reason: str


@dataclass(frozen=True)
class ReplayReport:
    feature_rows: int
    trades: int
    wins: int
    win_rate: float
    validation_trades: int
    validation_wins: int
    validation_win_rate: float
    validation_pnl_per_share: float
    pnl_per_share: float
    average_pnl_per_share: float
    passed: bool
    required_win_rate: float
    min_trades: int


def build_replay_report(
    path: Path,
    required_win_rate: float = 0.70,
    min_trades: int = 30,
    imbalance_threshold: float = 0.20,
    fee_per_share: float = 0.0,
    crypto_prices_path: Path | None = None,
) -> ReplayReport:
    features = extract_market_features(path, crypto_prices_path=crypto_prices_path)
    candidates = replay_imbalance_strategy(features, imbalance_threshold, fee_per_share)
    validation = chronological_validation(candidates)
    wins = sum(candidate.won for candidate in candidates)
    pnl = sum(candidate.pnl_per_share for candidate in candidates)
    trades = len(candidates)
    win_rate = wins / trades if trades else 0.0
    validation_wins = sum(candidate.won for candidate in validation)
    validation_pnl = sum(candidate.pnl_per_share for candidate in validation)
    validation_trades = len(validation)
    validation_win_rate = validation_wins / validation_trades if validation_trades else 0.0
    return ReplayReport(
        feature_rows=len(features),
        trades=trades,
        wins=wins,
        win_rate=win_rate,
        validation_trades=validation_trades,
        validation_wins=validation_wins,
        validation_win_rate=validation_win_rate,
        validation_pnl_per_share=validation_pnl,
        pnl_per_share=pnl,
        average_pnl_per_share=pnl / trades if trades else 0.0,
        passed=(
            trades >= min_trades
            and validation_trades > 0
            and validation_win_rate >= required_win_rate
            and validation_pnl > 0
        ),
        required_win_rate=required_win_rate,
        min_trades=min_trades,
    )


def format_replay_report(report: ReplayReport) -> str:
    status = "PASS" if report.passed else "REJECT"
    return "\n".join(
        [
            "**Polymarket BTC 5m replay**",
            f"- status: `{status}`",
            f"- feature rows: `{report.feature_rows}`",
            f"- trades: `{report.trades}` / wins: `{report.wins}`",
            f"- win rate: `{report.win_rate:.2%}` / required: `{report.required_win_rate:.2%}`",
            f"- validation trades: `{report.validation_trades}` / wins: `{report.validation_wins}`",
            f"- validation win rate: `{report.validation_win_rate:.2%}` / pnl: `{report.validation_pnl_per_share:+.4f}`",
            f"- pnl per share: `{report.pnl_per_share:+.4f}` / average: `{report.average_pnl_per_share:+.4f}`",
            f"- minimum trades: `{report.min_trades}`",
        ]
    )


def extract_market_features(
    path: Path,
    levels: int = 5,
    crypto_prices_path: Path | None = None,
) -> list[MarketFeature]:
    books: dict[tuple[str, str], dict[str, Any]] = {}
    crypto_prices = _crypto_price_index(crypto_prices_path)
    features: list[MarketFeature] = []
    for row in _jsonl_rows(path):
        market_slug = str(row.get("market_slug") or "")
        received_at = str(row.get("received_at") or "")
        event = row.get("event")
        if not market_slug or not isinstance(event, dict):
            continue
        event_type = event.get("event_type")
        if event_type == "price_change":
            for change in event.get("price_changes") or []:
                if not isinstance(change, dict):
                    continue
                asset_id = str(change.get("asset_id") or "")
                if not asset_id:
                    continue
                book = books.setdefault((market_slug, asset_id), _new_book())
                side = str(change.get("side") or "").upper()
                levels_key = "bids" if side == "BUY" else "asks" if side == "SELL" else ""
                if levels_key:
                    _apply_level(book[levels_key], change.get("price"), change.get("size"))
                feature = _feature_from_book(market_slug, received_at, asset_id, book, levels, crypto_prices)
                if feature:
                    features.append(feature)
            continue
        asset_id = str(event.get("asset_id") or "")
        if not asset_id:
            continue
        key = (market_slug, asset_id)
        book = books.setdefault(key, _new_book())
        if event_type == "book":
            book["bids"] = _levels_by_price(event.get("bids"))
            book["asks"] = _levels_by_price(event.get("asks"))
            book["last_trade_price"] = _float_or_none(event.get("last_trade_price"))
        elif event_type == "last_trade_price":
            book["last_trade_price"] = _float_or_none(event.get("price"))
            size = _float_or_none(event.get("size")) or 0.0
            side = str(event.get("side") or "").upper()
            if side == "BUY":
                book["buy_trade_qty"] += size
            elif side == "SELL":
                book["sell_trade_qty"] += size
        else:
            continue
        feature = _feature_from_book(market_slug, received_at, asset_id, book, levels, crypto_prices)
        if feature:
            features.append(feature)
    return features


def replay_imbalance_strategy(
    features: list[MarketFeature],
    imbalance_threshold: float,
    fee_per_share: float = 0.0,
) -> list[ReplayCandidate]:
    by_market: dict[str, list[MarketFeature]] = {}
    for feature in features:
        by_market.setdefault(feature.market_slug, []).append(feature)

    candidates: list[ReplayCandidate] = []
    for market_slug, rows in by_market.items():
        if len(rows) < 2:
            continue
        entry = next((row for row in rows if row.multi_level_imbalance >= imbalance_threshold), None)
        if entry is None:
            continue
        same_asset_rows = [row for row in rows if row.asset_id == entry.asset_id]
        exit_row = same_asset_rows[-1]
        if exit_row.time == entry.time:
            continue
        entry_price = entry.best_ask
        exit_price = exit_row.mid
        raw_pnl = exit_price - entry_price
        pnl = raw_pnl - fee_per_share
        candidates.append(
            ReplayCandidate(
                market_slug=market_slug,
                time=entry.time,
                asset_id=entry.asset_id,
                entry_price=entry_price,
                exit_price=exit_price,
                pnl_per_share=pnl,
                won=pnl > 0,
                reason="multi_level_imbalance",
            )
        )
    return candidates


def chronological_validation(candidates: list[ReplayCandidate], development_fraction: float = 0.70) -> list[ReplayCandidate]:
    if not candidates:
        return []
    ordered = sorted(candidates, key=lambda candidate: candidate.time)
    split = min(len(ordered) - 1, max(1, int(len(ordered) * development_fraction)))
    return ordered[split:]


def write_replay_report(path: Path, report: ReplayReport) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")


def _feature_from_book(
    market_slug: str,
    time: str,
    asset_id: str,
    book: dict[str, Any],
    levels: int,
    crypto_prices: dict[str, list[tuple[datetime, float]]],
) -> MarketFeature | None:
    bids = sorted(book["bids"].items(), reverse=True)
    asks = sorted(book["asks"].items())
    if not bids or not asks:
        return None
    best_bid, best_bid_qty = bids[0]
    best_ask, best_ask_qty = asks[0]
    if best_bid <= 0 or best_ask <= best_bid:
        return None
    bid_qty = sum(qty for _, qty in bids[:levels])
    ask_qty = sum(qty for _, qty in asks[:levels])
    previous_bid_qty = book["previous_bid_qty"]
    previous_ask_qty = book["previous_ask_qty"]
    ofi = 0.0
    if previous_bid_qty is not None and previous_ask_qty is not None:
        depth_change = (bid_qty - previous_bid_qty) - (ask_qty - previous_ask_qty)
        ofi = depth_change / (bid_qty + ask_qty) if bid_qty + ask_qty else 0.0
    book["previous_bid_qty"] = bid_qty
    book["previous_ask_qty"] = ask_qty
    event_time = _datetime_or_none(time)
    chainlink = _latest_price(crypto_prices.get("chainlink:btc/usd", []), event_time)
    binance = _latest_price(crypto_prices.get("binance:btcusdt", []), event_time)
    return MarketFeature(
        market_slug=market_slug,
        time=time,
        asset_id=asset_id,
        best_bid=best_bid,
        best_ask=best_ask,
        mid=(best_bid + best_ask) / 2,
        spread=best_ask - best_bid,
        imbalance=_ratio(best_bid_qty, best_ask_qty),
        multi_level_imbalance=_ratio(bid_qty, ask_qty),
        multi_level_ofi=ofi,
        trade_imbalance=_ratio(book["buy_trade_qty"], book["sell_trade_qty"]),
        seconds_remaining=_seconds_remaining(market_slug, event_time),
        chainlink_btc_usd=chainlink,
        binance_btc_usdt=binance,
        binance_chainlink_basis_pct=(binance / chainlink - 1) if binance is not None and chainlink else None,
        last_trade_price=book["last_trade_price"],
    )


def _jsonl_rows(path: Path) -> Iterator[dict[str, Any]]:
    if not path.exists():
        return
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                yield payload


def _levels_by_price(raw_levels: Any) -> dict[float, float]:
    levels: dict[float, float] = {}
    for level in raw_levels or []:
        if isinstance(level, dict):
            _apply_level(levels, level.get("price"), level.get("size"))
    return levels


def _apply_level(levels: dict[float, float], raw_price: Any, raw_size: Any) -> None:
    price = _float_or_none(raw_price)
    size = _float_or_none(raw_size)
    if price is None or size is None:
        return
    if size <= 0:
        levels.pop(price, None)
    else:
        levels[price] = size


def _ratio(bid_qty: float, ask_qty: float) -> float:
    total = bid_qty + ask_qty
    return (bid_qty - ask_qty) / total if total else 0.0


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _new_book() -> dict[str, Any]:
    return {
        "bids": {},
        "asks": {},
        "last_trade_price": None,
        "previous_bid_qty": None,
        "previous_ask_qty": None,
        "buy_trade_qty": 0.0,
        "sell_trade_qty": 0.0,
    }


def _crypto_price_index(path: Path | None) -> dict[str, list[tuple[datetime, float]]]:
    index: dict[str, list[tuple[datetime, float]]] = {}
    if path is None:
        return index
    for row in _jsonl_rows(path):
        event_time = _datetime_or_none(str(row.get("received_at") or ""))
        price = _float_or_none(row.get("price"))
        source = str(row.get("source") or "")
        symbol = str(row.get("symbol") or "").lower()
        if event_time is None or price is None or not source or not symbol:
            continue
        index.setdefault(f"{source}:{symbol}", []).append((event_time, price))
    for prices in index.values():
        prices.sort()
    return index


def _latest_price(prices: list[tuple[datetime, float]], event_time: datetime | None) -> float | None:
    if not prices or event_time is None:
        return None
    index = bisect_right(prices, (event_time, float("inf"))) - 1
    return prices[index][1] if index >= 0 else None


def _seconds_remaining(market_slug: str, event_time: datetime | None) -> float | None:
    if event_time is None:
        return None
    try:
        start_timestamp = int(market_slug.rsplit("-", 1)[1])
    except (IndexError, ValueError):
        return None
    end = datetime.fromtimestamp(start_timestamp + 300, UTC)
    return max(0.0, (end - event_time).total_seconds())


def _datetime_or_none(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
