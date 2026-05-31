from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import requests

from remotetrade.dex_route_probe import EthereumRpcClient, V2Pool, _amount_out, _read_pool, _to_units


USDT = "0x5de1677344d3cb0d7d465c10b72a8f60699c062d"
USDC = "0x66a2a913e447d6b4bf33efbec43aaef87890fbbc"
OOLONG_USDT_USDC_POOL = ("oolongswap", "0x13a0558337971abfe9370aa200e2e287cc22c432", USDT, USDC)


@dataclass(frozen=True)
class BobaCexDexProbe:
    observed_at: str
    chain_id: int
    block_number: int
    route: str
    start_usd: float
    gross_final_usd: float
    gas_cost_usd: float
    final_usd: float
    net_return_pct: float
    usdt_reserve: float
    usdc_reserve: float
    coinbase_usdt_bid: float
    coinbase_usdt_ask: float
    oolong_fee_bps: float
    opportunity: bool
    caveat: str


def scan_boba_cex_dex(
    rpc: EthereumRpcClient,
    start_usd: float = 10.0,
    min_net_return_pct: float = 0.001,
    oolong_fee_bps: float = 1.0,
    coinbase_url: str = "https://api.exchange.coinbase.com",
) -> BobaCexDexProbe:
    chain_id = rpc.chain_id()
    if chain_id != 288:
        raise RuntimeError(f"Boba CEX-DEX probe requires Boba mainnet, got chain_id={chain_id}.")
    block_number = rpc.block_number()
    pool = _read_pool(rpc, *OOLONG_USDT_USDC_POOL, block_number)
    usdt_reserve, usdc_reserve = _reserves(pool, USDT, USDC)
    usdt_bid, usdt_ask = _coinbase_ticker(coinbase_url, "USDT-USD")
    eth_bid, _ = _coinbase_ticker(coinbase_url, "ETH-USD")

    usdt_bought = _amount_out(_to_units(start_usd, 6), usdc_reserve, usdt_reserve, oolong_fee_bps)
    buy_dex_final_usd = usdt_bought / 10**6 * usdt_bid
    usdt_bought_cex = start_usd / usdt_ask
    sell_dex_final_usd = _amount_out(_to_units(usdt_bought_cex, 6), usdt_reserve, usdc_reserve, oolong_fee_bps) / 10**6
    gross_final_usd, route = max(
        (
            (buy_dex_final_usd, "USDC(BOBA DEX) -> USDT(CEX sell)"),
            (sell_dex_final_usd, "USDT(CEX buy) -> USDC(BOBA DEX)"),
        )
    )
    gas_cost_usd = 150_000 * rpc.gas_price() / 10**18 * eth_bid
    final_usd = gross_final_usd - gas_cost_usd
    net_return_pct = final_usd / start_usd - 1
    return BobaCexDexProbe(
        observed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        chain_id=chain_id,
        block_number=block_number,
        route=route,
        start_usd=start_usd,
        gross_final_usd=gross_final_usd,
        gas_cost_usd=gas_cost_usd,
        final_usd=final_usd,
        net_return_pct=net_return_pct,
        usdt_reserve=usdt_reserve / 10**6,
        usdc_reserve=usdc_reserve / 10**6,
        coinbase_usdt_bid=usdt_bid,
        coinbase_usdt_ask=usdt_ask,
        oolong_fee_bps=oolong_fee_bps,
        opportunity=net_return_pct >= min_net_return_pct,
        caveat="paper-only: bridge latency, bridge fee, CEX inventory, and withdrawal availability are not modeled",
    )


def append_boba_cex_dex_probe(path: Path, probe: BobaCexDexProbe) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(probe), separators=(",", ":")) + "\n")


def format_boba_cex_dex_probe(probe: BobaCexDexProbe) -> str:
    label = "candidate" if probe.opportunity else "none"
    return (
        f"[BobaCexDex] {label}: {probe.route} start=${probe.start_usd:.2f} "
        f"gross=${probe.gross_final_usd:.4f} gas~=${probe.gas_cost_usd:.4f} "
        f"final=${probe.final_usd:.4f} net={probe.net_return_pct:+.4%} "
        f"pool=USDT {probe.usdt_reserve:.2f}/USDC {probe.usdc_reserve:.2f}"
    )


def _reserves(pool: V2Pool, token_in: str, token_out: str) -> tuple[int, int]:
    if (pool.token0, pool.token1) == (token_in, token_out):
        return pool.reserve0, pool.reserve1
    if (pool.token1, pool.token0) == (token_in, token_out):
        return pool.reserve1, pool.reserve0
    raise RuntimeError(f"Unexpected pool token pair: {pool.token0}/{pool.token1}")


def _coinbase_ticker(base_url: str, product: str) -> tuple[float, float]:
    response = requests.get(f"{base_url.rstrip('/')}/products/{product}/ticker", timeout=10)
    response.raise_for_status()
    payload = response.json()
    return float(payload["bid"]), float(payload["ask"])
