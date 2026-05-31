from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
DAI = "0x6b175474e89094c44da98b954eedeac495271d0f"
USDT = "0xdac17f958d2ee523a2206206994597c13d831ec7"
TOKENS = {
    USDC: ("USDC", 6),
    WETH: ("WETH", 18),
    DAI: ("DAI", 18),
    USDT: ("USDT", 6),
}
ALLOWLIST_POOLS = (
    ("uniswap_v2", "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc", USDC, WETH),
    ("uniswap_v2", "0xae461ca67b15dc8dc81ce7615e0320da1a9ab8d5", USDC, DAI),
    ("uniswap_v2", "0x3041cbd36888becc7bbcbc0045e3b1f144466f5f", USDC, USDT),
    ("uniswap_v2", "0xa478c2975ab1ea89e8196811f51a7b7ade33eb11", WETH, DAI),
    ("uniswap_v2", "0x0d4a11d5eeaac28ec3f61d100daf4d40471f1852", WETH, USDT),
    ("uniswap_v2", "0xb20bd5d04be54f870d5c0d3ca85d82b34b836405", DAI, USDT),
    ("sushiswap_v2", "0x397ff1542f962076d0bfe58ea045ffa2d347aca0", USDC, WETH),
    ("sushiswap_v2", "0xaaf5110db6e744ff70fb339de037b990a20bdace", USDC, DAI),
    ("sushiswap_v2", "0xd86a120a06255df8d4e2248ab04d4267e23adfaa", USDC, USDT),
    ("sushiswap_v2", "0xc3d03e4f041fd4cd388c549ee2a29a9e5075882f", WETH, DAI),
    ("sushiswap_v2", "0x06da0fd433c1a5d7a4faa01111c044910a184553", WETH, USDT),
    ("sushiswap_v2", "0x055cedfe14bce33f985c41d9a1934b7654611aac", DAI, USDT),
)


@dataclass(frozen=True)
class V2Pool:
    venue: str
    address: str
    token0: str
    token1: str
    reserve0: int
    reserve1: int


@dataclass(frozen=True)
class DexRouteProbe:
    observed_at: str
    chain_id: int
    block_number: int
    pool_count: int
    route_count: int
    assets: tuple[str, ...]
    pools: tuple[str, ...]
    start_usdc: float
    gross_final_usdc: float
    gas_cost_usdc: float
    final_usdc: float
    net_return_pct: float
    opportunity: bool


@dataclass(frozen=True)
class _PoolEdge:
    pool: V2Pool
    from_token: str
    to_token: str
    reserve_in: int
    reserve_out: int


class EthereumRpcClient:
    def __init__(self, url: str, timeout: float = 10.0) -> None:
        self.url = url
        self.timeout = timeout
        self.request_id = 0
        self.session = requests.Session()

    def chain_id(self) -> int:
        return int(self.call("eth_chainId", []), 16)

    def block_number(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)

    def gas_price(self) -> int:
        return int(self.call("eth_gasPrice", []), 16)

    def eth_call_at(self, address: str, data: str, block_number: int) -> str:
        return self.call("eth_call", [{"to": address, "data": data}, hex(block_number)])

    def call(self, method: str, params: list[Any]) -> Any:
        self.request_id += 1
        response = self.session.post(
            self.url,
            json={"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(f"Ethereum RPC error: {payload['error']}")
        return payload["result"]


def scan_dex_routes(
    rpc: EthereumRpcClient,
    start_usdc: float = 1_000.0,
    min_net_return_pct: float = 0.001,
    fee_bps: float = 30.0,
    pools: list[V2Pool] | None = None,
) -> DexRouteProbe:
    chain_id = rpc.chain_id()
    if chain_id != 1:
        raise RuntimeError(f"DEX route probe requires Ethereum mainnet, got chain_id={chain_id}.")
    block_number = rpc.block_number()
    pools = pools or [_read_pool(rpc, *spec, block_number) for spec in ALLOWLIST_POOLS]
    routes = _find_routes(pools, _to_units(start_usdc, 6), fee_bps)
    if not routes:
        raise RuntimeError("No allowlisted DEX routes found.")
    gross_final_units, assets, route_pools = max(routes, key=lambda route: route[0])
    gross_final_usdc = gross_final_units / 10**6
    gas_cost_usdc = _estimate_gas_cost_usdc(rpc.gas_price(), len(route_pools), pools)
    final_usdc = gross_final_usdc - gas_cost_usdc
    net_return_pct = final_usdc / start_usdc - 1
    return DexRouteProbe(
        observed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        chain_id=chain_id,
        block_number=block_number,
        pool_count=len(pools),
        route_count=len(routes),
        assets=tuple(_token_symbol(token) for token in assets),
        pools=tuple(f"{pool.venue}:{pool.address[:10]}" for pool in route_pools),
        start_usdc=start_usdc,
        gross_final_usdc=gross_final_usdc,
        gas_cost_usdc=gas_cost_usdc,
        final_usdc=final_usdc,
        net_return_pct=net_return_pct,
        opportunity=net_return_pct >= min_net_return_pct,
    )


def append_dex_route_probe(path: Path, probe: DexRouteProbe) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(probe), separators=(",", ":")) + "\n")


def format_dex_route_probe(probe: DexRouteProbe) -> str:
    label = "opportunity" if probe.opportunity else "none"
    return (
        f"[DexRoute] {label}: {' -> '.join(probe.assets)} via {' -> '.join(probe.pools)} "
        f"pools={probe.pool_count} routes={probe.route_count} start={probe.start_usdc:.2f} USDC "
        f"gross={probe.gross_final_usdc:.4f} gas~={probe.gas_cost_usdc:.4f} "
        f"final={probe.final_usdc:.4f} net={probe.net_return_pct:+.4%}"
    )


def _find_routes(
    pools: list[V2Pool],
    start_amount: int,
    fee_bps: float,
    max_hops: int = 4,
) -> list[tuple[int, list[str], list[V2Pool]]]:
    graph = _pool_graph(pools)
    routes: list[tuple[int, list[str], list[V2Pool]]] = []

    def walk(token: str, amount: int, assets: list[str], route: list[V2Pool]) -> None:
        if route and token == USDC:
            if len(route) >= 2:
                routes.append((amount, assets, route))
            return
        if len(route) >= max_hops:
            return
        for edge in graph.get(token, []):
            if edge.pool in route or (edge.to_token in assets and edge.to_token != USDC):
                continue
            output = _amount_out(amount, edge.reserve_in, edge.reserve_out, fee_bps)
            if output > 0:
                walk(edge.to_token, output, [*assets, edge.to_token], [*route, edge.pool])

    walk(USDC, start_amount, [USDC], [])
    return routes


def _pool_graph(pools: list[V2Pool]) -> dict[str, list[_PoolEdge]]:
    graph: dict[str, list[_PoolEdge]] = {}
    for pool in pools:
        graph.setdefault(pool.token0, []).append(_PoolEdge(pool, pool.token0, pool.token1, pool.reserve0, pool.reserve1))
        graph.setdefault(pool.token1, []).append(_PoolEdge(pool, pool.token1, pool.token0, pool.reserve1, pool.reserve0))
    return graph


def _read_pool(
    rpc: EthereumRpcClient,
    venue: str,
    address: str,
    expected_token_a: str,
    expected_token_b: str,
    block_number: int,
) -> V2Pool:
    token0 = _decode_address(rpc.eth_call_at(address, "0x0dfe1681", block_number))
    token1 = _decode_address(rpc.eth_call_at(address, "0xd21220a7", block_number))
    if {token0, token1} != {expected_token_a, expected_token_b}:
        raise RuntimeError(f"Unexpected token contract pair for {venue}:{address}: {token0}/{token1}")
    reserve0, reserve1 = _decode_uint_words(rpc.eth_call_at(address, "0x0902f1ac", block_number), 2)
    return V2Pool(venue, address, token0, token1, reserve0, reserve1)


def _estimate_gas_cost_usdc(gas_price: int, hops: int, pools: list[V2Pool]) -> float:
    weth_usdc_pool = next(pool for pool in pools if {pool.token0, pool.token1} == {USDC, WETH})
    reserve_usdc = weth_usdc_pool.reserve0 if weth_usdc_pool.token0 == USDC else weth_usdc_pool.reserve1
    reserve_weth = weth_usdc_pool.reserve1 if weth_usdc_pool.token1 == WETH else weth_usdc_pool.reserve0
    weth_price_usdc = (reserve_usdc / 10**6) / (reserve_weth / 10**18)
    estimated_gas_units = 120_000 + 80_000 * hops
    return estimated_gas_units * gas_price / 10**18 * weth_price_usdc


def _amount_out(amount_in: int, reserve_in: int, reserve_out: int, fee_bps: float) -> int:
    amount_in_with_fee = amount_in * int(10_000 - fee_bps)
    return amount_in_with_fee * reserve_out // (reserve_in * 10_000 + amount_in_with_fee)


def _decode_address(raw: str) -> str:
    return "0x" + raw.removeprefix("0x")[-40:].lower()


def _decode_uint_words(raw: str, count: int) -> tuple[int, ...]:
    value = raw.removeprefix("0x")
    return tuple(int(value[index * 64 : (index + 1) * 64], 16) for index in range(count))


def _to_units(amount: float, decimals: int) -> int:
    return int(amount * 10**decimals)


def _token_symbol(token: str) -> str:
    return TOKENS[token][0]
