from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from remotetrade.dex_route_probe import EthereumRpcClient, V2Pool, _amount_out, _read_pool, _to_units


USDT = "0x55d398326f99059ff775485246999027b3197955"
BUSD = "0xe9e7cea3dedca5984780bafc599bd69add087d56"
BTCB = "0x7130d2a12b9bcbfae4f2634d864a1ee1ce3ead9c"
WBNB = "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c"
SYMBOLS = {USDT: "USDT", BUSD: "BUSD", BTCB: "BTCB", WBNB: "WBNB"}
PANCAKESWAP_V2_POOLS = (
    ("pancakeswap_v2", "0x7efaef62fddcca950418312c6c91aef321375a00", USDT, BUSD),
    ("pancakeswap_v2", "0xf45cd219aef8618a92baa7ad848364a158a24f33", BUSD, BTCB),
    ("pancakeswap_v2", "0x3f803ec2b816ea7f06ec76aa2b6f2532f9892d62", USDT, BTCB),
    ("pancakeswap_v2", "0x16b9a82891338f9ba80e2d6970fdda79d1eb0dae", USDT, WBNB),
)


@dataclass(frozen=True)
class BscQashRouteProbe:
    observed_at: str
    chain_id: int
    block_number: int
    assets: tuple[str, ...]
    start_usdt: float
    gross_final_usdt: float
    gas_cost_usdt: float
    final_usdt: float
    net_return_pct: float
    opportunity: bool


def scan_bsc_qash_route(
    rpc: EthereumRpcClient,
    start_usdt: float = 1_000.0,
    min_net_return_pct: float = 0.001,
    fee_bps: float = 25.0,
) -> BscQashRouteProbe:
    chain_id = rpc.chain_id()
    if chain_id != 56:
        raise RuntimeError(f"BSC qash route probe requires BSC mainnet, got chain_id={chain_id}.")
    block_number = rpc.block_number()
    pools = [_read_pool(rpc, *spec, block_number) for spec in PANCAKESWAP_V2_POOLS]
    usdt_busd, busd_btcb, usdt_btcb, usdt_wbnb = pools
    routes = (
        _quote_route(_to_units(start_usdt, 18), [USDT, BUSD, BTCB, USDT], [usdt_busd, busd_btcb, usdt_btcb], fee_bps),
        _quote_route(_to_units(start_usdt, 18), [USDT, BTCB, BUSD, USDT], [usdt_btcb, busd_btcb, usdt_busd], fee_bps),
    )
    gross_final_units, assets = max(routes, key=lambda route: route[0])
    gross_final_usdt = gross_final_units / 10**18
    gas_cost_usdt = _estimate_gas_cost_usdt(rpc.gas_price(), usdt_wbnb)
    final_usdt = gross_final_usdt - gas_cost_usdt
    net_return_pct = final_usdt / start_usdt - 1
    return BscQashRouteProbe(
        observed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        chain_id=chain_id,
        block_number=block_number,
        assets=tuple(SYMBOLS[asset] for asset in assets),
        start_usdt=start_usdt,
        gross_final_usdt=gross_final_usdt,
        gas_cost_usdt=gas_cost_usdt,
        final_usdt=final_usdt,
        net_return_pct=net_return_pct,
        opportunity=net_return_pct >= min_net_return_pct,
    )


def append_bsc_qash_route_probe(path: Path, probe: BscQashRouteProbe) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(probe), separators=(",", ":")) + "\n")


def format_bsc_qash_route_probe(probe: BscQashRouteProbe) -> str:
    label = "opportunity" if probe.opportunity else "none"
    return (
        f"[BscQashRoute] {label}: {' -> '.join(probe.assets)} start={probe.start_usdt:.2f} USDT "
        f"gross={probe.gross_final_usdt:.4f} gas~={probe.gas_cost_usdt:.4f} "
        f"final={probe.final_usdt:.4f} net={probe.net_return_pct:+.4%}"
    )


def _quote_route(amount: int, assets: list[str], pools: list[V2Pool], fee_bps: float) -> tuple[int, list[str]]:
    for from_token, to_token, pool in zip(assets[:-1], assets[1:], pools, strict=True):
        reserve_in, reserve_out = _reserves(pool, from_token, to_token)
        amount = _amount_out(amount, reserve_in, reserve_out, fee_bps)
    return amount, assets


def _reserves(pool: V2Pool, from_token: str, to_token: str) -> tuple[int, int]:
    if (pool.token0, pool.token1) == (from_token, to_token):
        return pool.reserve0, pool.reserve1
    if (pool.token1, pool.token0) == (from_token, to_token):
        return pool.reserve1, pool.reserve0
    raise RuntimeError(f"Pool {pool.address} does not support {from_token}/{to_token}.")


def _estimate_gas_cost_usdt(gas_price: int, usdt_wbnb_pool: V2Pool) -> float:
    reserve_usdt, reserve_wbnb = _reserves(usdt_wbnb_pool, USDT, WBNB)
    wbnb_price_usdt = (reserve_usdt / 10**18) / (reserve_wbnb / 10**18)
    return 360_000 * gas_price / 10**18 * wbnb_price_usdt
