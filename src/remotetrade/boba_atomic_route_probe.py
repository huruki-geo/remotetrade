from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from remotetrade.boba_cex_dex_probe import OOLONG_USDT_USDC_POOL, USDC, USDT, _coinbase_ticker, _reserves
from remotetrade.boba_synapse_probe import SYNAPSE_STABLE_POOL
from remotetrade.boba_zencha_probe import ZENCHA_SWAP_FLASH_LOAN, _encode
from remotetrade.dex_route_probe import EthereumRpcClient, _amount_out, _read_pool


CALCULATE_SWAP = "0xa95b089f"
SIZES_USDC = (1.0, 10.0, 50.0, 100.0, 500.0, 1_000.0, 5_000.0)
WETH = "0xdeaddeaddeaddeaddeaddeaddeaddeaddead0000"
WBTC = "0xdc0486f8bf31df57a952bcd3c1d3e166e3d9ec8b"
OOLONG_POOLS = (
    ("oolong_usdc_weth", "0x547b227a77813ea70aacf01212b39db7b560fa1c", USDC, WETH, False),
    ("oolong_usdt_weth", "0x232130d2802c283eb870586cab8ee49f8ea0b181", USDT, WETH, False),
    (*OOLONG_USDT_USDC_POOL, True),
    ("oolong_wbtc_weth", "0xeef227ecccec2213f80bb92cb648b0ddbaab00ab", WBTC, WETH, False),
)


@dataclass(frozen=True)
class AtomicEdge:
    venue: str
    token_in: str
    token_out: str
    quote_kind: str
    pool: str
    token_in_index: int
    token_out_index: int
    fee_bps: float = 0.0


@dataclass(frozen=True)
class AtomicRouteQuote:
    route: str
    start_usdc: float
    gross_final_usdc: float
    gas_cost_usd: float
    final_usdc: float
    profit_usd: float
    net_return_pct: float


@dataclass(frozen=True)
class BobaAtomicRouteProbe:
    observed_at: str
    chain_id: int
    block_number: int
    route_count: int
    route: str
    start_usdc: float
    gross_final_usdc: float
    gas_cost_usd: float
    final_usdc: float
    profit_usd: float
    net_return_pct: float
    profitable_capacity_usdc: float
    quotes: tuple[AtomicRouteQuote, ...]
    opportunity: bool
    caveat: str


def scan_boba_atomic_routes(
    rpc: EthereumRpcClient,
    min_net_return_pct: float = 0.001,
    oolong_stable_fee_bps: float = 1.0,
    oolong_volatile_fee_bps: float = 30.0,
    coinbase_url: str = "https://api.exchange.coinbase.com",
    sizes_usdc: tuple[float, ...] = SIZES_USDC,
) -> BobaAtomicRouteProbe:
    chain_id = rpc.chain_id()
    if chain_id != 288:
        raise RuntimeError(f"Boba atomic route probe requires Boba mainnet, got chain_id={chain_id}.")
    block_number = rpc.block_number()
    oolong_pools = tuple(
        _read_pool(rpc, venue, address, token_a, token_b, block_number)
        for venue, address, token_a, token_b, _ in OOLONG_POOLS
    )
    edges = _build_edges(oolong_stable_fee_bps, oolong_volatile_fee_bps)
    routes = _find_cycles(edges)
    eth_bid, _ = _coinbase_ticker(coinbase_url, "ETH-USD")
    gas_price = rpc.gas_price()
    quote_cache = {}
    all_quotes = tuple(
        _quote_route(rpc, block_number, oolong_pools, route, size_usdc, eth_bid, gas_price, quote_cache)
        for size_usdc in sizes_usdc
        for route in routes
    )
    quotes = tuple(
        max((quote for quote in all_quotes if quote.start_usdc == size_usdc), key=lambda quote: quote.profit_usd)
        for size_usdc in sizes_usdc
    )
    best = max(quotes, key=lambda quote: quote.profit_usd)
    profitable_capacity_usdc = max(
        (quote.start_usdc for quote in quotes if quote.net_return_pct >= min_net_return_pct),
        default=0.0,
    )
    return BobaAtomicRouteProbe(
        observed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        chain_id=chain_id,
        block_number=block_number,
        route_count=len(routes),
        route=best.route,
        start_usdc=best.start_usdc,
        gross_final_usdc=best.gross_final_usdc,
        gas_cost_usd=best.gas_cost_usd,
        final_usdc=best.final_usdc,
        profit_usd=best.profit_usd,
        net_return_pct=best.net_return_pct,
        profitable_capacity_usdc=profitable_capacity_usdc,
        quotes=quotes,
        opportunity=best.net_return_pct >= min_net_return_pct,
        caveat=(
            "paper-only: canonical BOBA USDC/USDT only; atomic execution requires an audited executor contract; "
            "executor overhead, failed transactions, MEV, and pool-state contention are not modeled"
        ),
    )


def append_boba_atomic_route_probe(path: Path, probe: BobaAtomicRouteProbe) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(probe), separators=(",", ":")) + "\n")


def format_boba_atomic_route_probe(probe: BobaAtomicRouteProbe) -> str:
    label = "candidate" if probe.opportunity else "none"
    return (
        f"[BobaAtomicRoute] {label}: {probe.route} routes={probe.route_count} "
        f"start={probe.start_usdc:.2f} USDC gross={probe.gross_final_usdc:.4f} "
        f"gas~=${probe.gas_cost_usd:.4f} profit=${probe.profit_usd:+.4f} "
        f"net={probe.net_return_pct:+.4%} capacity>={probe.profitable_capacity_usdc:.0f} USDC"
    )


def _build_edges(oolong_stable_fee_bps: float, oolong_volatile_fee_bps: float) -> tuple[AtomicEdge, ...]:
    edges = [
        AtomicEdge("zencha", USDC, USDT, "saddle", ZENCHA_SWAP_FLASH_LOAN, 1, 2),
        AtomicEdge("zencha", USDT, USDC, "saddle", ZENCHA_SWAP_FLASH_LOAN, 2, 1),
        AtomicEdge("synapse", USDC, USDT, "saddle", SYNAPSE_STABLE_POOL, 2, 3),
        AtomicEdge("synapse", USDT, USDC, "saddle", SYNAPSE_STABLE_POOL, 3, 2),
    ]
    for venue, address, token_a, token_b, stable in OOLONG_POOLS:
        fee_bps = oolong_stable_fee_bps if stable else oolong_volatile_fee_bps
        edges.append(AtomicEdge(venue, token_a, token_b, "v2", address, 0, 0, fee_bps))
        edges.append(AtomicEdge(venue, token_b, token_a, "v2", address, 0, 0, fee_bps))
    return tuple(edges)


def _find_cycles(edges: tuple[AtomicEdge, ...]) -> tuple[tuple[AtomicEdge, ...], ...]:
    routes = []
    def walk(token, route, assets):
        if token == USDC and route:
            if len(route) >= 2:
                routes.append(tuple(route))
            return
        if len(route) >= 4:
            return
        for edge in edges:
            if edge.token_in != token or edge.pool in {item.pool for item in route}:
                continue
            if edge.token_out in assets and edge.token_out != USDC:
                continue
            walk(edge.token_out, [*route, edge], [*assets, edge.token_out])

    walk(USDC, [], [USDC])
    return tuple(routes)


def _quote_route(rpc, block_number, oolong_pools, route, start_usdc, eth_bid, gas_price, quote_cache) -> AtomicRouteQuote:
    amount = int(start_usdc * 10**6)
    for edge in route:
        key = (edge, amount)
        if key not in quote_cache:
            quote_cache[key] = _quote_edge(rpc, block_number, oolong_pools, edge, amount)
        amount = quote_cache[key]
    gross_final_usdc = amount / 10**6
    gas_cost_usd = 140_000 * len(route) * gas_price / 10**18 * eth_bid
    final_usdc = gross_final_usdc - gas_cost_usd
    return AtomicRouteQuote(
        route="USDC -> " + " -> ".join(f"{edge.token_out_symbol}({edge.venue})" for edge in _route_labels(route)),
        start_usdc=start_usdc,
        gross_final_usdc=gross_final_usdc,
        gas_cost_usd=gas_cost_usd,
        final_usdc=final_usdc,
        profit_usd=final_usdc - start_usdc,
        net_return_pct=final_usdc / start_usdc - 1,
    )


def _quote_edge(rpc, block_number, oolong_pools, edge, amount_in):
    if edge.quote_kind == "saddle":
        data = _encode(CALCULATE_SWAP, edge.token_in_index, edge.token_out_index, amount_in)
        return int(rpc.eth_call_at(edge.pool, data, block_number), 16)
    oolong = next(pool for pool in oolong_pools if pool.address == edge.pool)
    reserve_in, reserve_out = _reserves(oolong, edge.token_in, edge.token_out)
    return _amount_out(amount_in, reserve_in, reserve_out, edge.fee_bps)


@dataclass(frozen=True)
class _RouteLabel:
    token_out_symbol: str
    venue: str


def _route_labels(route):
    symbols = {USDC: "USDC", USDT: "USDT", WETH: "WETH", WBTC: "WBTC"}
    return tuple(_RouteLabel(symbols[edge.token_out], edge.venue) for edge in route)
