from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests


USDC = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
WETH = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
DEFAULT_POOLS = (
    ("uniswap_v2", "0xb4e16d0168e52d35cacd2c6185b44281ec28c9dc"),
    ("sushiswap_v2", "0x397ff1542f962076d0bfe58ea045ffa2d347aca0"),
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
    buy_pool: str
    sell_pool: str
    start_usdc: float
    final_usdc: float
    net_return_pct: float
    opportunity: bool


class EthereumRpcClient:
    def __init__(self, url: str, timeout: float = 10.0) -> None:
        self.url = url
        self.timeout = timeout
        self.request_id = 0

    def chain_id(self) -> int:
        return int(self.call("eth_chainId", []), 16)

    def eth_call(self, address: str, data: str) -> str:
        return self.call("eth_call", [{"to": address, "data": data}, "latest"])

    def block_number(self) -> int:
        return int(self.call("eth_blockNumber", []), 16)

    def eth_call_at(self, address: str, data: str, block_number: int) -> str:
        return self.call("eth_call", [{"to": address, "data": data}, hex(block_number)])

    def call(self, method: str, params: list[Any]) -> Any:
        self.request_id += 1
        response = requests.post(
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
) -> DexRouteProbe:
    chain_id = rpc.chain_id()
    if chain_id != 1:
        raise RuntimeError(f"DEX route probe requires Ethereum mainnet, got chain_id={chain_id}.")
    block_number = rpc.block_number()
    pools = [_read_pool(rpc, venue, address, block_number) for venue, address in DEFAULT_POOLS]
    routes = []
    for buy_pool, sell_pool in ((pools[0], pools[1]), (pools[1], pools[0])):
        weth = _amount_out(_to_units(start_usdc, 6), buy_pool.reserve0, buy_pool.reserve1, fee_bps)
        final_usdc = _amount_out(weth, sell_pool.reserve1, sell_pool.reserve0, fee_bps) / 10**6
        routes.append((final_usdc, buy_pool.venue, sell_pool.venue))
    final_usdc, buy_pool, sell_pool = max(routes)
    net_return_pct = final_usdc / start_usdc - 1
    return DexRouteProbe(
        observed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        chain_id=chain_id,
        block_number=block_number,
        buy_pool=buy_pool,
        sell_pool=sell_pool,
        start_usdc=start_usdc,
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
        f"[DexRoute] {label}: {probe.buy_pool} -> {probe.sell_pool} "
        f"start={probe.start_usdc:.2f} USDC final={probe.final_usdc:.4f} USDC "
        f"net={probe.net_return_pct:+.4%}"
    )


def _read_pool(rpc: EthereumRpcClient, venue: str, address: str, block_number: int) -> V2Pool:
    token0 = _decode_address(rpc.eth_call_at(address, "0x0dfe1681", block_number))
    token1 = _decode_address(rpc.eth_call_at(address, "0xd21220a7", block_number))
    if (token0, token1) != (USDC, WETH):
        raise RuntimeError(f"Unexpected token contract pair for {venue}: {token0}/{token1}")
    raw = rpc.eth_call_at(address, "0x0902f1ac", block_number)
    reserve0, reserve1 = _decode_uint_words(raw, 2)
    return V2Pool(venue, address, token0, token1, reserve0, reserve1)


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
