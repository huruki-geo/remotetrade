from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from remotetrade.clients import BitstampClient, CoinbaseClient, KrakenClient, Quote


class QuoteClient(Protocol):
    def get_quote(self, symbol: str) -> Quote: ...


@dataclass(frozen=True)
class VenueSpec:
    venue: str
    symbol: str
    client: QuoteClient


@dataclass(frozen=True)
class ArbitrageOpportunity:
    symbol: str
    buy_venue: str
    sell_venue: str
    buy_ask: float
    sell_bid: float
    gross_spread_pct: float
    net_spread_pct: float
    estimated_profit_usd: float
    notional_usd: float


@dataclass(frozen=True)
class LimitArbitrageOrder:
    symbol: str
    buy_venue: str
    sell_venue: str
    buy_limit: float
    sell_limit: float
    net_spread_pct: float
    estimated_profit_usd: float
    notional_usd: float
    qty: float


def scan_arbitrage(
    quotes: list[Quote],
    notional_usd: float,
    fee_bps: float,
    min_net_spread_pct: float,
) -> list[ArbitrageOpportunity]:
    opportunities: list[ArbitrageOpportunity] = []
    fee_pct = fee_bps / 10_000
    total_fee_pct = fee_pct * 2

    for buy in quotes:
        for sell in quotes:
            if buy.venue == sell.venue:
                continue
            gross_spread_pct = (sell.bid - buy.ask) / buy.ask
            net_spread_pct = gross_spread_pct - total_fee_pct
            if net_spread_pct < min_net_spread_pct:
                continue
            opportunities.append(
                ArbitrageOpportunity(
                    symbol=buy.symbol,
                    buy_venue=buy.venue,
                    sell_venue=sell.venue,
                    buy_ask=buy.ask,
                    sell_bid=sell.bid,
                    gross_spread_pct=gross_spread_pct,
                    net_spread_pct=net_spread_pct,
                    estimated_profit_usd=notional_usd * net_spread_pct,
                    notional_usd=notional_usd,
                )
            )

    return sorted(opportunities, key=lambda opportunity: opportunity.net_spread_pct, reverse=True)


def scan_limit_arbitrage(
    quotes: list[Quote],
    notional_usd: float,
    maker_fee_bps: float,
    min_net_spread_pct: float,
    price_improvement_bps: float,
) -> list[LimitArbitrageOrder]:
    orders: list[LimitArbitrageOrder] = []
    fee_pct = maker_fee_bps / 10_000
    improvement_pct = price_improvement_bps / 10_000
    total_fee_pct = fee_pct * 2

    for buy in quotes:
        for sell in quotes:
            if buy.venue == sell.venue:
                continue
            buy_limit = buy.bid * (1 + improvement_pct)
            sell_limit = sell.ask * (1 - improvement_pct)
            if buy_limit >= buy.ask or sell_limit <= sell.bid:
                continue
            gross_spread_pct = (sell_limit - buy_limit) / buy_limit
            net_spread_pct = gross_spread_pct - total_fee_pct
            if net_spread_pct < min_net_spread_pct:
                continue
            orders.append(
                LimitArbitrageOrder(
                    symbol=buy.symbol,
                    buy_venue=buy.venue,
                    sell_venue=sell.venue,
                    buy_limit=buy_limit,
                    sell_limit=sell_limit,
                    net_spread_pct=net_spread_pct,
                    estimated_profit_usd=notional_usd * net_spread_pct,
                    notional_usd=notional_usd,
                    qty=notional_usd / buy_limit,
                )
            )

    return sorted(orders, key=lambda order: order.net_spread_pct, reverse=True)


def default_venues(product_id: str) -> list[VenueSpec]:
    base, quote = product_id.split("-", 1)
    kraken_base = "XBT" if base.upper() == "BTC" else base.upper()
    return [
        VenueSpec("coinbase", product_id.upper(), CoinbaseClient()),
        VenueSpec("kraken", f"{kraken_base}{quote.upper()}", KrakenClient()),
        VenueSpec("bitstamp", f"{base.upper()}{quote.upper()}", BitstampClient()),
    ]


def fetch_quotes(venues: list[VenueSpec]) -> list[Quote]:
    quotes: list[Quote] = []
    for venue in venues:
        quote = venue.client.get_quote(venue.symbol)
        quotes.append(
            Quote(
                venue=venue.venue,
                symbol=quote.symbol,
                bid=quote.bid,
                ask=quote.ask,
                raw=quote.raw,
            )
        )
    return quotes


def append_arbitrage_tick(path: Path, quotes: list[Quote], opportunities: list[ArbitrageOpportunity]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    best = opportunities[0] if opportunities else None
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "time",
                "venue",
                "symbol",
                "bid",
                "ask",
                "best_buy_venue",
                "best_sell_venue",
                "best_net_spread_pct",
                "best_estimated_profit_usd",
            ],
        )
        if not exists:
            writer.writeheader()
        for quote in quotes:
            writer.writerow(
                {
                    "time": utc_now(),
                    "venue": quote.venue,
                    "symbol": quote.symbol,
                    "bid": f"{quote.bid:.2f}",
                    "ask": f"{quote.ask:.2f}",
                    "best_buy_venue": best.buy_venue if best else "",
                    "best_sell_venue": best.sell_venue if best else "",
                    "best_net_spread_pct": "" if best is None else f"{best.net_spread_pct:.6f}",
                    "best_estimated_profit_usd": "" if best is None else f"{best.estimated_profit_usd:.4f}",
                }
            )


def append_limit_arbitrage_tick(path: Path, quotes: list[Quote], orders: list[LimitArbitrageOrder]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    best = orders[0] if orders else None
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "time",
                "venue",
                "symbol",
                "bid",
                "ask",
                "best_buy_venue",
                "best_sell_venue",
                "best_buy_limit",
                "best_sell_limit",
                "best_qty",
                "best_net_spread_pct",
                "best_estimated_profit_usd",
            ],
        )
        if not exists:
            writer.writeheader()
        for quote in quotes:
            writer.writerow(
                {
                    "time": utc_now(),
                    "venue": quote.venue,
                    "symbol": quote.symbol,
                    "bid": f"{quote.bid:.2f}",
                    "ask": f"{quote.ask:.2f}",
                    "best_buy_venue": best.buy_venue if best else "",
                    "best_sell_venue": best.sell_venue if best else "",
                    "best_buy_limit": "" if best is None else f"{best.buy_limit:.2f}",
                    "best_sell_limit": "" if best is None else f"{best.sell_limit:.2f}",
                    "best_qty": "" if best is None else f"{best.qty:.10f}",
                    "best_net_spread_pct": "" if best is None else f"{best.net_spread_pct:.6f}",
                    "best_estimated_profit_usd": "" if best is None else f"{best.estimated_profit_usd:.4f}",
                }
            )


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")
