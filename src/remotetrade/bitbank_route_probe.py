from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from remotetrade.route_arbitrage import MarketPair, RouteOpportunity, find_route_arbitrage
from remotetrade.venue_discovery import BitbankPublicClient


@dataclass(frozen=True)
class BitbankRouteProbe:
    observed_at: str
    pair_count: int
    start_asset: str
    start_amount: float
    assets: tuple[str, ...]
    markets: tuple[str, ...]
    sides: tuple[str, ...]
    final_amount: float
    net_return_pct: float
    opportunity: bool


def scan_bitbank_routes(
    client: BitbankPublicClient | None = None,
    start_asset: str = "jpy",
    start_amount: float = 10_000.0,
    min_net_return_pct: float = 0.0005,
) -> BitbankRouteProbe:
    client = client or BitbankPublicClient()
    statuses = {str(row["pair"]): row for row in client.get_statuses()}
    pairs: list[MarketPair] = []
    for rule in client.get_pairs():
        pair = str(rule["name"])
        status = statuses.get(pair)
        if rule.get("is_enabled") is not True or not status or status.get("status") != "NORMAL":
            continue
        try:
            book = client.get_order_book(pair)
            bid, bid_qty = _best_level(book.get("bids"))
            ask, ask_qty = _best_level(book.get("asks"))
            taker_fee_bps = float(rule["taker_fee_rate_quote"]) * 10_000
        except (KeyError, TypeError, ValueError):
            continue
        pairs.append(
            MarketPair(
                pair,
                str(rule["base_asset"]),
                str(rule["quote_asset"]),
                bid,
                ask,
                bid_qty,
                ask_qty,
                taker_fee_bps,
            )
        )
    routes = find_route_arbitrage(pairs, start_asset, start_amount, 0.0, -1.0, max_hops=3)
    triangles = [route for route in routes if len(route.markets) == 3 and len(set(route.markets)) == 3]
    best = triangles[0] if triangles else None
    return _build_probe(pairs, start_asset, start_amount, min_net_return_pct, best)


def append_bitbank_route_probe(path: Path, probe: BitbankRouteProbe) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(probe), separators=(",", ":")) + "\n")


def format_bitbank_route_probe(probe: BitbankRouteProbe) -> str:
    route = " -> ".join(probe.assets) if probe.assets else "none"
    label = "opportunity" if probe.opportunity else "none"
    return (
        f"[BitbankRoute] {label}: route={route} pairs={probe.pair_count} "
        f"start={probe.start_amount:.0f} {probe.start_asset.upper()} "
        f"final={probe.final_amount:.4f} net={probe.net_return_pct:+.4%}"
    )


def _best_level(levels: Any) -> tuple[float, float]:
    if not levels:
        raise ValueError("empty order book")
    price, qty = levels[0]
    return float(price), float(qty)


def _build_probe(
    pairs: list[MarketPair],
    start_asset: str,
    start_amount: float,
    min_net_return_pct: float,
    best: RouteOpportunity | None,
) -> BitbankRouteProbe:
    return BitbankRouteProbe(
        observed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        pair_count=len(pairs),
        start_asset=start_asset,
        start_amount=start_amount,
        assets=best.assets if best else (),
        markets=best.markets if best else (),
        sides=best.sides if best else (),
        final_amount=best.final_amount if best else start_amount,
        net_return_pct=best.net_return_pct if best else 0.0,
        opportunity=best is not None and best.net_return_pct >= min_net_return_pct,
    )
