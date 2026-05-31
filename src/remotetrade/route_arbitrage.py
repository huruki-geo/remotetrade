from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketPair:
    symbol: str
    base: str
    quote: str
    bid: float
    ask: float


@dataclass(frozen=True)
class Conversion:
    market: str
    from_asset: str
    to_asset: str
    rate: float
    side: str


@dataclass(frozen=True)
class RouteOpportunity:
    assets: tuple[str, ...]
    markets: tuple[str, ...]
    sides: tuple[str, ...]
    start_amount: float
    final_amount: float
    net_return_pct: float


def find_route_arbitrage(
    pairs: list[MarketPair],
    start_asset: str,
    start_amount: float,
    fee_bps: float,
    min_net_return_pct: float,
    max_hops: int = 3,
) -> list[RouteOpportunity]:
    if start_amount <= 0:
        raise ValueError("start_amount must be positive.")
    if max_hops < 2:
        raise ValueError("max_hops must be at least 2.")

    fee_multiplier = 1 - fee_bps / 10_000
    if fee_multiplier <= 0:
        raise ValueError("fee_bps must be below 10000.")

    graph = _conversion_graph(pairs, fee_multiplier)
    opportunities: list[RouteOpportunity] = []

    def walk(asset: str, amount: float, route: list[Conversion], visited_assets: set[str]) -> None:
        if route and asset == start_asset:
            net_return_pct = amount / start_amount - 1
            if len(route) >= 2 and net_return_pct >= min_net_return_pct:
                opportunities.append(
                    RouteOpportunity(
                        assets=(start_asset, *(conversion.to_asset for conversion in route)),
                        markets=tuple(conversion.market for conversion in route),
                        sides=tuple(conversion.side for conversion in route),
                        start_amount=start_amount,
                        final_amount=amount,
                        net_return_pct=net_return_pct,
                    )
                )
            return

        if len(route) >= max_hops:
            return

        for conversion in graph.get(asset, []):
            if conversion.to_asset in visited_assets and conversion.to_asset != start_asset:
                continue
            walk(
                conversion.to_asset,
                amount * conversion.rate,
                [*route, conversion],
                {*visited_assets, conversion.to_asset},
            )

    walk(start_asset, start_amount, [], {start_asset})
    return sorted(opportunities, key=lambda opportunity: opportunity.net_return_pct, reverse=True)


def _conversion_graph(pairs: list[MarketPair], fee_multiplier: float) -> dict[str, list[Conversion]]:
    graph: dict[str, list[Conversion]] = {}
    for pair in pairs:
        if pair.bid <= 0 or pair.ask <= 0:
            continue
        graph.setdefault(pair.base, []).append(
            Conversion(pair.symbol, pair.base, pair.quote, pair.bid * fee_multiplier, "SELL")
        )
        graph.setdefault(pair.quote, []).append(
            Conversion(pair.symbol, pair.quote, pair.base, fee_multiplier / pair.ask, "BUY")
        )
    return graph
