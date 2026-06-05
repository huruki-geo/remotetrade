from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests

from remotetrade.stock_patterns import StockCategory, load_stock_patterns

PUBLIC_SEARCH_URL = "https://gamma-api.polymarket.com/public-search"
MARKETS_URL = "https://gamma-api.polymarket.com/markets"
ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class BridgeCategory:
    id: str
    label: str
    query: str
    market_slugs: list[str]
    up_long: list[str]
    up_short: list[str]
    down_long: list[str]
    down_short: list[str]
    threshold: float


@dataclass(frozen=True)
class BridgeObservation:
    observed_at: str
    category_id: str
    category_label: str
    query: str
    market_slug: str
    market_question: str
    yes_price: float
    previous_yes_price: float | None
    odds_delta: float | None
    alert: bool
    us_market_hours: bool
    us_market_closed: bool
    up_long: list[str]
    up_short: list[str]
    down_long: list[str]
    down_short: list[str]
    raw: dict[str, Any]


def collect_stock_bridge_once(
    patterns_path: Path,
    state_path: Path,
    events_path: Path,
    *,
    max_markets_per_category: int = 8,
    min_liquidity: float = 0.0,
    min_volume: float = 0.0,
    timeout: float = 15.0,
) -> list[BridgeObservation]:
    categories = _bridge_categories(patterns_path)
    state = _load_state(state_path)
    observations: list[BridgeObservation] = []
    observed_at = datetime.now(UTC)

    with requests.Session() as session:
        session.headers.update({"User-Agent": "remotetrade-polymarket-stock-bridge/1.0"})
        for category in categories:
            markets = _fetch_category_markets(session, category, max_markets_per_category, timeout)
            for market in markets:
                yes_price = _yes_price(market)
                if yes_price is None:
                    continue
                if _metric(market, "liquidity", "liquidityNum", "liquidityClob") < min_liquidity:
                    continue
                if _metric(market, "volume", "volumeNum") < min_volume:
                    continue
                state_key = f"{category.id}:{market.get('slug')}"
                previous = state.get(state_key)
                delta = yes_price - previous if isinstance(previous, (int, float)) else None
                alert = delta is not None and abs(delta) >= category.threshold
                observation = BridgeObservation(
                    observed_at=observed_at.isoformat(timespec="seconds"),
                    category_id=category.id,
                    category_label=category.label,
                    query=category.query,
                    market_slug=str(market.get("slug") or ""),
                    market_question=str(market.get("question") or market.get("title") or ""),
                    yes_price=yes_price,
                    previous_yes_price=float(previous) if isinstance(previous, (int, float)) else None,
                    odds_delta=delta,
                    alert=alert,
                    us_market_hours=_is_us_market_hours(observed_at),
                    us_market_closed=not _is_us_market_hours(observed_at),
                    up_long=category.up_long,
                    up_short=category.up_short,
                    down_long=category.down_long,
                    down_short=category.down_short,
                    raw=_compact_market(market),
                )
                observations.append(observation)
                state[state_key] = yes_price

    _append_observations(events_path, observations)
    _save_state(state_path, state)
    return observations


def format_bridge_observations(observations: list[BridgeObservation]) -> str:
    if not observations:
        return "Polymarket stock bridge: no observations"
    alerts = [row for row in observations if row.alert]
    closed = sum(row.us_market_closed for row in observations)
    lines = [
        f"Polymarket stock bridge: observations={len(observations)} alerts={len(alerts)} us_closed={closed}",
    ]
    for row in alerts[:10]:
        delta = row.odds_delta if row.odds_delta is not None else 0.0
        window = "closed" if row.us_market_closed else "open"
        lines.append(
            f"- {row.category_id}/{row.market_slug}: yes={row.yes_price:.3f} "
            f"delta={delta:+.3f} us_market={window} q={row.market_question[:90]}"
        )
    return "\n".join(lines)


def _bridge_categories(path: Path) -> list[BridgeCategory]:
    by_key: dict[tuple[str, str], BridgeCategory] = {}
    for pattern in load_stock_patterns(path):
        for category in pattern.categories:
            key = (category.id, category.query)
            existing = by_key.get(key)
            threshold = pattern.entry_threshold if existing is None else min(existing.threshold, pattern.entry_threshold)
            by_key[key] = _to_bridge_category(category, threshold)
    return list(by_key.values())


def _to_bridge_category(category: StockCategory, threshold: float) -> BridgeCategory:
    return BridgeCategory(
        id=category.id,
        label=category.label,
        query=category.query,
        market_slugs=category.market_slugs,
        up_long=category.up_long,
        up_short=category.up_short,
        down_long=category.down_long,
        down_short=category.down_short,
        threshold=threshold,
    )


def _fetch_category_markets(
    session: requests.Session,
    category: BridgeCategory,
    limit: int,
    timeout: float,
) -> list[dict[str, Any]]:
    markets: list[dict[str, Any]] = []
    for slug in category.market_slugs:
        markets.extend(_fetch_slug_markets(session, slug, timeout))
    if not category.market_slugs:
        markets.extend(_public_search_markets(session, category.query, limit, timeout))
        if not any(_is_open_market(market) for market in markets):
            for term in _query_terms(category.query):
                markets.extend(_public_search_markets(session, term, limit, timeout))
    filtered = [market for market in markets if _is_open_market(market) and _matches_category(category, market)]
    filtered.sort(key=lambda item: (_metric(item, "volume24hr"), _metric(item, "volume", "volumeNum")), reverse=True)
    return _dedupe_by_slug(filtered)[:limit]


def _fetch_slug_markets(session: requests.Session, slug: str, timeout: float) -> list[dict[str, Any]]:
    response = session.get(MARKETS_URL, params={"slug": slug}, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        markets = payload.get("data") or payload.get("markets") or []
        return markets if isinstance(markets, list) else []
    return []


def _public_search_markets(session: requests.Session, query: str, limit: int, timeout: float) -> list[dict[str, Any]]:
    response = session.get(PUBLIC_SEARCH_URL, params={"q": query, "limit": limit}, timeout=timeout)
    response.raise_for_status()
    payload = response.json()
    events = payload.get("events") if isinstance(payload, dict) else []
    markets: list[dict[str, Any]] = []
    if isinstance(events, list):
        for event in events:
            if not isinstance(event, dict):
                continue
            for market in event.get("markets") or []:
                if isinstance(market, dict):
                    markets.append(market)
    return markets


def _is_open_market(market: dict[str, Any]) -> bool:
    return bool(market.get("active", True)) and not bool(market.get("closed", False)) and not bool(market.get("archived", False))


def _matches_category(category: BridgeCategory, market: dict[str, Any]) -> bool:
    if category.market_slugs:
        return True
    terms = _query_terms(category.query)
    if not terms:
        return True
    haystack = " ".join(
        str(market.get(key) or "")
        for key in ("slug", "question", "title", "description")
    ).lower()
    return any(term in haystack for term in terms)


def _query_terms(query: str) -> list[str]:
    stop = {"a", "an", "or", "the", "will", "by", "in", "on", "of", "and", "2026", "above"}
    return [term for term in query.lower().replace("/", " ").replace("-", " ").split() if term and term not in stop]


def _yes_price(market: dict[str, Any]) -> float | None:
    outcomes = _jsonish_list(market.get("outcomes"))
    prices = _jsonish_list(market.get("outcomePrices"))
    if outcomes and prices and len(outcomes) == len(prices):
        for outcome, price in zip(outcomes, prices):
            if str(outcome).strip().lower() in {"yes", "up"}:
                try:
                    return float(price)
                except (TypeError, ValueError):
                    return None
    for key in ("lastTradePrice", "bestAsk", "bestBid"):
        try:
            value = market.get(key)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _jsonish_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _metric(market: dict[str, Any], *keys: str) -> float:
    for key in keys:
        try:
            value = market.get(key)
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _dedupe_by_slug(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for market in markets:
        slug = str(market.get("slug") or "")
        if not slug or slug in seen:
            continue
        seen.add(slug)
        unique.append(market)
    return unique


def _compact_market(market: dict[str, Any]) -> dict[str, Any]:
    return {
        key: market.get(key)
        for key in (
            "id",
            "conditionId",
            "slug",
            "question",
            "endDate",
            "volume",
            "volume24hr",
            "liquidity",
            "liquidityNum",
            "liquidityClob",
            "lastTradePrice",
            "bestBid",
            "bestAsk",
        )
        if key in market
    }


def _is_us_market_hours(moment: datetime) -> bool:
    local = moment.astimezone(ET)
    if local.weekday() >= 5:
        return False
    start = local.replace(hour=9, minute=30, second=0, microsecond=0)
    end = local.replace(hour=16, minute=0, second=0, microsecond=0)
    return start <= local < end


def _load_state(path: Path) -> dict[str, float]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    prices = payload.get("prices") if isinstance(payload, dict) else payload
    if not isinstance(prices, dict):
        return {}
    state: dict[str, float] = {}
    for key, value in prices.items():
        try:
            state[str(key)] = float(value)
        except (TypeError, ValueError):
            continue
    return state


def _save_state(path: Path, state: dict[str, float]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"updated_at": datetime.now(UTC).isoformat(timespec="seconds"), "prices": state}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _append_observations(path: Path, observations: list[BridgeObservation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for observation in observations:
            handle.write(json.dumps(asdict(observation), ensure_ascii=False, separators=(",", ":")) + "\n")
