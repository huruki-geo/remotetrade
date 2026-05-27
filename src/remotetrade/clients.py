from __future__ import annotations

import json
from csv import DictReader
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from io import StringIO
from typing import Any

import requests


@dataclass(frozen=True)
class PredictionMarket:
    id: str
    slug: str
    question: str
    yes_price: float
    no_price: float
    raw: dict[str, Any]

    @property
    def edge(self) -> float:
        return self.yes_price - 0.5


class PolymarketClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def find_market(self, slug: str | None, query: str) -> PredictionMarket:
        markets = self._fetch_markets(slug=slug, query=query)
        parsed = [market for item in markets if (market := self._parse_market(item))]
        if not slug:
            parsed = [market for market in parsed if _matches_query(market, query)]
        if not parsed:
            label = slug or query
            raise RuntimeError(f"No active Polymarket market with parseable prices found for {label!r}.")

        if slug:
            exact = [market for market in parsed if market.slug == slug]
            if exact:
                return exact[0]

        candidate_slugs = _candidate_slugs(query)
        if candidate_slugs:
            exact_by_slug = {market.slug: market for market in parsed}
            for candidate_slug in candidate_slugs:
                market = exact_by_slug.get(candidate_slug)
                if market and _is_tradeable_price(market):
                    return market
            for candidate_slug in candidate_slugs:
                market = exact_by_slug.get(candidate_slug)
                if market:
                    return market

        return max(parsed, key=lambda market: float(market.raw.get("volumeNum") or market.raw.get("volume") or 0))

    def search_markets(self, query: str, limit: int = 10) -> list[PredictionMarket]:
        markets = self._fetch_markets(slug=None, query=query)
        parsed = [market for item in markets if (market := self._parse_market(item))]
        parsed.sort(key=lambda market: float(market.raw.get("volume24hr") or market.raw.get("volumeNum") or 0), reverse=True)
        return parsed[:limit]

    def _fetch_markets(self, slug: str | None, query: str) -> list[dict[str, Any]]:
        if slug:
            params = {"slug": slug}
            params["slug"] = slug
        else:
            params = {"limit": 100}
            params["active"] = "true"
            params["closed"] = "false"
            if query:
                params["search"] = query

        markets: list[dict[str, Any]] = []
        response = requests.get(f"{self.base_url}/markets", params=params, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            if slug:
                raise
        else:
            payload = response.json()
            markets = _extract_market_list(payload)
        if slug:
            return markets

        params.pop("search", None)
        params["q"] = query
        response = requests.get(f"{self.base_url}/markets", params=params, timeout=self.timeout)
        try:
            response.raise_for_status()
        except requests.HTTPError:
            pass
        else:
            markets.extend(_extract_market_list(response.json()))

        for candidate_slug in _candidate_slugs(query):
            candidate_params = {"active": "true", "closed": "false", "slug": candidate_slug}
            response = requests.get(f"{self.base_url}/markets", params=candidate_params, timeout=self.timeout)
            response.raise_for_status()
            markets.extend(_extract_market_list(response.json()))

        return _dedupe_markets(markets)

    def _parse_market(self, item: dict[str, Any]) -> PredictionMarket | None:
        outcomes = _jsonish_list(item.get("outcomes"))
        prices = _jsonish_list(item.get("outcomePrices"))
        if not outcomes or not prices or len(outcomes) != len(prices):
            return None

        price_by_outcome = {str(outcome).strip().lower(): float(price) for outcome, price in zip(outcomes, prices)}
        yes_price = price_by_outcome.get("yes", price_by_outcome.get("up"))
        no_price = price_by_outcome.get("no", price_by_outcome.get("down"))
        if yes_price is None or no_price is None:
            return None

        return PredictionMarket(
            id=str(item.get("id") or item.get("conditionId") or ""),
            slug=str(item.get("slug") or ""),
            question=str(item.get("question") or ""),
            yes_price=yes_price,
            no_price=no_price,
            raw=item,
        )


def _extract_market_list(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        data = payload.get("data") or payload.get("markets") or []
        if isinstance(data, list):
            return data
        raise RuntimeError("Unexpected Polymarket markets response shape.")
    raise RuntimeError("Unexpected Polymarket markets response shape.")


def _dedupe_markets(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for market in markets:
        key = str(market.get("id") or market.get("slug") or len(unique))
        if key in seen:
            continue
        seen.add(key)
        unique.append(market)
    return unique


class CoinbaseClient:
    def __init__(self, base_url: str, timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_price(self, product_id: str) -> float:
        response = requests.get(f"{self.base_url}/products/{product_id}/ticker", timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        return float(payload["price"])


class StooqClient:
    def __init__(self, base_url: str = "https://stooq.com", timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_price(self, symbol: str) -> float:
        stooq_symbol = symbol.lower()
        if "." not in stooq_symbol:
            stooq_symbol = f"{stooq_symbol}.us"
        response = requests.get(
            f"{self.base_url}/q/l/",
            params={"s": stooq_symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"},
            timeout=self.timeout,
        )
        response.raise_for_status()
        rows = list(DictReader(StringIO(response.text)))
        if not rows:
            raise RuntimeError(f"No Stooq price row for {symbol}.")
        close = rows[0].get("Close")
        if not close or close == "N/D":
            raise RuntimeError(f"No Stooq close price for {symbol}.")
        return float(close)


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


def _matches_query(market: PredictionMarket, query: str) -> bool:
    terms = [
        term
        for term in query.lower().replace("-", " ").split()
        if term not in {"a", "an", "or", "the", "will", "market"}
    ]
    if not terms:
        return True

    haystack = f"{market.slug} {market.question}".lower()
    aliases = {"bitcoin": ["bitcoin", "btc"], "ethereum": ["ethereum", "eth"], "solana": ["solana", "sol"]}
    for term in terms:
        candidates = aliases.get(term, [term])
        if not any(candidate in haystack for candidate in candidates):
            return False
    return True


def _candidate_slugs(query: str) -> list[str]:
    normalized = query.lower()
    if "btc" not in normalized and "bitcoin" not in normalized:
        return []
    if "up" not in normalized or "down" not in normalized:
        return []

    now = datetime.now(UTC)
    candidates: list[str] = []
    if "5m" in normalized or "5-min" in normalized or "5 min" in normalized:
        minute = now.minute - (now.minute % 5)
        floor_5m = now.replace(minute=minute, second=0, microsecond=0)
        for offset in (0, 1, -1, 2):
            start = floor_5m + timedelta(minutes=5 * offset)
            candidates.append(f"btc-updown-5m-{int(start.timestamp())}")

    floor_hour = now.replace(minute=0, second=0, microsecond=0)
    for offset in (0, 1, -1):
        start = floor_hour + timedelta(hours=offset)
        candidates.append(f"bitcoin-up-or-down-{_month_slug(start)}-{start.day}-{start.year}-{_et_hour_slug(start)}-et")

    candidates.append(f"bitcoin-up-or-down-on-{_month_slug(now)}-{now.day}-{now.year}")
    return list(dict.fromkeys(candidates))


def _is_tradeable_price(market: PredictionMarket) -> bool:
    return 0.02 < market.yes_price < 0.98 and 0.02 < market.no_price < 0.98


def _month_slug(value: datetime) -> str:
    return value.strftime("%B").lower()


def _et_hour_slug(value: datetime) -> str:
    et_hour = (value.hour - 4) % 24
    suffix = "am" if et_hour < 12 else "pm"
    hour_12 = et_hour % 12 or 12
    return f"{hour_12}{suffix}"
