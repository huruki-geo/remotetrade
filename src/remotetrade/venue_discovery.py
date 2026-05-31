from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


@dataclass(frozen=True)
class MarketDiscovery:
    venue: str
    symbol: str
    quote_asset: str
    observed_at: str
    bid: float
    ask: float
    spread_bps: float
    maker_fee_bps: float
    taker_fee_bps: float
    maker_round_trip_edge_bps: float
    taker_round_trip_edge_bps: float
    min_order_size: float
    min_order_notional_quote: float
    bid_depth_quote: float
    ask_depth_quote: float
    volume_24h: float
    eligible_small_maker: bool


class GmoCoinPublicClient:
    def __init__(self, base_url: str = "https://api.coin.z.com/public", timeout: float = 10.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_symbols(self) -> list[dict[str, Any]]:
        return self._get("/v1/symbols")

    def get_ticker(self, symbol: str) -> dict[str, Any]:
        rows = self._get("/v1/ticker", {"symbol": symbol})
        if not rows:
            raise RuntimeError(f"No GMO ticker for {symbol}.")
        return rows[0]

    def get_order_book(self, symbol: str) -> dict[str, Any]:
        return self._get("/v1/orderbooks", {"symbol": symbol})

    def _get(self, path: str, params: dict[str, str] | None = None) -> Any:
        response = requests.get(f"{self.base_url}{path}", params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get("status") != 0:
            raise RuntimeError(f"GMO API error for {path}: {payload}")
        return payload.get("data")


class BitbankPublicClient:
    def __init__(
        self,
        public_url: str = "https://public.bitbank.cc",
        config_url: str = "https://api.bitbank.cc",
        timeout: float = 10.0,
    ) -> None:
        self.public_url = public_url.rstrip("/")
        self.config_url = config_url.rstrip("/")
        self.timeout = timeout

    def get_pairs(self) -> list[dict[str, Any]]:
        payload = self._get(f"{self.config_url}/v1/spot/pairs")
        return payload["pairs"]

    def get_tickers(self) -> list[dict[str, Any]]:
        return self._get(f"{self.public_url}/tickers")

    def get_statuses(self) -> list[dict[str, Any]]:
        payload = self._get(f"{self.config_url}/v1/spot/status")
        return payload["statuses"]

    def get_order_book(self, pair: str) -> dict[str, Any]:
        return self._get(f"{self.public_url}/{pair}/depth")

    def _get(self, url: str) -> Any:
        response = requests.get(url, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        if payload.get("success") != 1:
            raise RuntimeError(f"bitbank API error for {url}: {payload}")
        return payload.get("data")


class MexcPublicClient:
    def __init__(self, base_url: str = "https://api.mexc.com", timeout: float = 15.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def get_symbols(self) -> list[dict[str, Any]]:
        return self._get("/api/v3/exchangeInfo")["symbols"]

    def get_book_tickers(self) -> list[dict[str, Any]]:
        return self._get("/api/v3/ticker/bookTicker")

    def _get(self, path: str) -> Any:
        response = requests.get(f"{self.base_url}{path}", timeout=self.timeout)
        response.raise_for_status()
        return response.json()


def scan_low_cost_markets(
    max_order_notional_jpy: float = 2_000.0,
    max_order_notional_usdt: float = 20.0,
    min_depth_jpy: float = 10_000.0,
    min_depth_usdt: float = 100.0,
    max_spread_bps: float = 500.0,
    depth_levels: int = 5,
    gmo_client: GmoCoinPublicClient | None = None,
    bitbank_client: BitbankPublicClient | None = None,
    mexc_client: MexcPublicClient | None = None,
) -> list[MarketDiscovery]:
    discoveries: list[MarketDiscovery] = []
    for venue, scan in (
        (
            "gmo_coin",
            lambda: scan_gmo_small_maker_markets(
                gmo_client, max_order_notional_jpy, depth_levels, min_depth_jpy, max_spread_bps
            ),
        ),
        (
            "bitbank",
            lambda: scan_bitbank_small_maker_markets(
                bitbank_client, max_order_notional_jpy, depth_levels, min_depth_jpy, max_spread_bps
            ),
        ),
        (
            "mexc",
            lambda: scan_mexc_research_markets(
                mexc_client, max_order_notional_usdt, min_depth_usdt, max_spread_bps
            ),
        ),
    ):
        try:
            discoveries.extend(scan())
        except (requests.RequestException, RuntimeError) as exc:
            print(f"{venue} discovery skipped after error: {exc}", flush=True)
    return _sort_discoveries(discoveries)


def scan_gmo_small_maker_markets(
    client: GmoCoinPublicClient | None = None,
    max_order_notional_jpy: float = 2_000.0,
    depth_levels: int = 5,
    min_depth_jpy: float = 10_000.0,
    max_spread_bps: float = 500.0,
) -> list[MarketDiscovery]:
    client = client or GmoCoinPublicClient()
    discoveries: list[MarketDiscovery] = []
    for rule in client.get_symbols():
        symbol = str(rule["symbol"])
        if symbol.endswith("_JPY"):
            continue
        try:
            ticker = client.get_ticker(symbol)
            book = client.get_order_book(symbol)
            bid = float(ticker["bid"])
            ask = float(ticker["ask"])
        except (KeyError, TypeError, ValueError):
            continue
        if bid <= 0 or ask <= bid:
            continue
        spread_bps = (ask - bid) / ((ask + bid) / 2) * 10_000
        maker_fee_bps = float(rule["makerFee"]) * 10_000
        taker_fee_bps = float(rule["takerFee"]) * 10_000
        min_order_size = float(rule["minOrderSize"])
        min_order_notional_jpy = min_order_size * ask
        bid_depth = _book_depth(book.get("bids"), depth_levels)
        ask_depth = _book_depth(book.get("asks"), depth_levels)
        discoveries.append(
            MarketDiscovery(
                venue="gmo_coin",
                symbol=symbol,
                quote_asset="JPY",
                observed_at=utc_now(),
                bid=bid,
                ask=ask,
                spread_bps=spread_bps,
                maker_fee_bps=maker_fee_bps,
                taker_fee_bps=taker_fee_bps,
                maker_round_trip_edge_bps=spread_bps - maker_fee_bps * 2,
                taker_round_trip_edge_bps=-spread_bps - taker_fee_bps * 2,
                min_order_size=min_order_size,
                min_order_notional_quote=min_order_notional_jpy,
                bid_depth_quote=bid_depth,
                ask_depth_quote=ask_depth,
                volume_24h=float(ticker["volume"]),
                eligible_small_maker=_is_eligible(
                    min_order_notional_jpy, max_order_notional_jpy, bid_depth, ask_depth, min_depth_jpy, spread_bps, max_spread_bps
                ),
            )
        )
    return _sort_discoveries(discoveries)


def scan_bitbank_small_maker_markets(
    client: BitbankPublicClient | None = None,
    max_order_notional_jpy: float = 2_000.0,
    depth_levels: int = 5,
    min_depth_jpy: float = 10_000.0,
    max_spread_bps: float = 500.0,
) -> list[MarketDiscovery]:
    client = client or BitbankPublicClient()
    tickers = {str(ticker["pair"]): ticker for ticker in client.get_tickers()}
    statuses = {str(status["pair"]): status for status in client.get_statuses()}
    discoveries: list[MarketDiscovery] = []
    for rule in client.get_pairs():
        pair = str(rule["name"])
        if rule.get("is_enabled") is not True or str(rule.get("quote_asset")) != "jpy":
            continue
        ticker = tickers.get(pair)
        status = statuses.get(pair)
        if not ticker or not status or status.get("status") != "NORMAL":
            continue
        try:
            bid = float(ticker["buy"])
            ask = float(ticker["sell"])
        except (KeyError, TypeError, ValueError):
            continue
        if bid <= 0 or ask <= bid:
            continue
        book = client.get_order_book(pair)
        spread_bps = (ask - bid) / ((ask + bid) / 2) * 10_000
        maker_fee_bps = float(rule["maker_fee_rate_quote"]) * 10_000
        taker_fee_bps = float(rule["taker_fee_rate_quote"]) * 10_000
        min_order_size = float(status["min_amount"])
        min_order_notional_jpy = min_order_size * ask
        bid_depth = _bitbank_book_depth(book.get("bids"), depth_levels)
        ask_depth = _bitbank_book_depth(book.get("asks"), depth_levels)
        discoveries.append(
            MarketDiscovery(
                venue="bitbank",
                symbol=pair,
                quote_asset="JPY",
                observed_at=utc_now(),
                bid=bid,
                ask=ask,
                spread_bps=spread_bps,
                maker_fee_bps=maker_fee_bps,
                taker_fee_bps=taker_fee_bps,
                maker_round_trip_edge_bps=spread_bps - maker_fee_bps * 2,
                taker_round_trip_edge_bps=-spread_bps - taker_fee_bps * 2,
                min_order_size=min_order_size,
                min_order_notional_quote=min_order_notional_jpy,
                bid_depth_quote=bid_depth,
                ask_depth_quote=ask_depth,
                volume_24h=float(ticker["vol"]),
                eligible_small_maker=_is_eligible(
                    min_order_notional_jpy, max_order_notional_jpy, bid_depth, ask_depth, min_depth_jpy, spread_bps, max_spread_bps
                ),
            )
        )
    return _sort_discoveries(discoveries)


def scan_mexc_research_markets(
    client: MexcPublicClient | None = None,
    max_order_notional_usdt: float = 20.0,
    min_depth_usdt: float = 100.0,
    max_spread_bps: float = 500.0,
) -> list[MarketDiscovery]:
    client = client or MexcPublicClient()
    tickers = {str(ticker["symbol"]): ticker for ticker in client.get_book_tickers()}
    discoveries: list[MarketDiscovery] = []
    for rule in client.get_symbols():
        symbol = str(rule["symbol"])
        if (
            rule.get("isSpotTradingAllowed") is not True
            or str(rule.get("quoteAsset")) != "USDT"
            or "LIMIT_MAKER" not in (rule.get("orderTypes") or [])
        ):
            continue
        ticker = tickers.get(symbol)
        if not ticker:
            continue
        try:
            bid = float(ticker["bidPrice"])
            ask = float(ticker["askPrice"])
            bid_qty = float(ticker["bidQty"])
            ask_qty = float(ticker["askQty"])
            min_order_size = float(rule["baseSizePrecision"])
            maker_fee_bps = float(rule["makerCommission"]) * 10_000
            taker_fee_bps = float(rule["takerCommission"]) * 10_000
        except (KeyError, TypeError, ValueError):
            continue
        if bid <= 0 or ask <= bid or bid_qty <= 0 or ask_qty <= 0:
            continue
        spread_bps = (ask - bid) / ((ask + bid) / 2) * 10_000
        min_order_notional = min_order_size * ask
        discoveries.append(
            MarketDiscovery(
                venue="mexc_research",
                symbol=symbol,
                quote_asset="USDT",
                observed_at=utc_now(),
                bid=bid,
                ask=ask,
                spread_bps=spread_bps,
                maker_fee_bps=maker_fee_bps,
                taker_fee_bps=taker_fee_bps,
                maker_round_trip_edge_bps=spread_bps - maker_fee_bps * 2,
                taker_round_trip_edge_bps=-spread_bps - taker_fee_bps * 2,
                min_order_size=min_order_size,
                min_order_notional_quote=min_order_notional,
                bid_depth_quote=bid * bid_qty,
                ask_depth_quote=ask * ask_qty,
                volume_24h=0.0,
                eligible_small_maker=_is_eligible(
                    min_order_notional, max_order_notional_usdt, bid * bid_qty, ask * ask_qty, min_depth_usdt, spread_bps, max_spread_bps
                ),
            )
        )
    return _sort_discoveries(discoveries)


def append_market_discoveries(path: Path, discoveries: list[MarketDiscovery]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for discovery in discoveries:
            handle.write(json.dumps(asdict(discovery), separators=(",", ":")) + "\n")


def format_market_discoveries(discoveries: list[MarketDiscovery], limit: int = 10) -> str:
    lines = ["**Small maker market discovery**"]
    for discovery in discoveries[:limit]:
        lines.append(
            f"- `{discovery.venue}:{discovery.symbol}` spread `{discovery.spread_bps:.2f}bps` "
            f"maker `{discovery.maker_fee_bps:+.2f}bps` "
            f"maker-rt `{discovery.maker_round_trip_edge_bps:+.2f}bps` "
            f"min `{discovery.quote_asset} {discovery.min_order_notional_quote:.2f}` "
            f"depth `{discovery.quote_asset} {min(discovery.bid_depth_quote, discovery.ask_depth_quote):.0f}`"
        )
    return "\n".join(lines)


def _book_depth(raw_levels: Any, levels: int) -> float:
    total = 0.0
    for level in (raw_levels or [])[:levels]:
        total += float(level["price"]) * float(level["size"])
    return total


def _bitbank_book_depth(raw_levels: Any, levels: int) -> float:
    return sum(float(price) * float(size) for price, size in (raw_levels or [])[:levels])


def _sort_discoveries(discoveries: list[MarketDiscovery]) -> list[MarketDiscovery]:
    return sorted(
        discoveries,
        key=lambda discovery: (
            discovery.eligible_small_maker,
            discovery.maker_round_trip_edge_bps,
            min(discovery.bid_depth_quote, discovery.ask_depth_quote),
        ),
        reverse=True,
    )


def _is_eligible(
    min_order_notional: float,
    max_order_notional: float,
    bid_depth: float,
    ask_depth: float,
    min_depth: float,
    spread_bps: float,
    max_spread_bps: float,
) -> bool:
    return (
        min_order_notional <= max_order_notional
        and min(bid_depth, ask_depth) >= min_depth
        and spread_bps <= max_spread_bps
    )


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
