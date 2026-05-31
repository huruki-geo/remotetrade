from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from remotetrade.boba_cex_dex_probe import _coinbase_ticker
from remotetrade.boba_zencha_probe import CALCULATE_SWAP, GET_TOKEN, GET_TOKEN_BALANCE, USDC, USDT, ZenchaQuote, _decode_address, _encode
from remotetrade.dex_route_probe import EthereumRpcClient


SYNAPSE_STABLE_POOL = "0x75ff037256b36f15919369ac58695550be72fead"
NUSD = "0x6b4712ae9797c199edd44f897ca09bc57628a1cf"
DAI = "0xf74195bb8a5cf652411867c5c2c5b8c2a402be35"
TOKENS = (
    ("nUSD", NUSD, 18),
    ("DAI", DAI, 18),
    ("USDC", USDC, 6),
    ("USDT", USDT, 6),
)
SIZES_USD = (1.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0)
TRADE_PAIRS = ((2, 3), (3, 2))


@dataclass(frozen=True)
class BobaSynapseProbe:
    observed_at: str
    chain_id: int
    block_number: int
    route: str
    start_usd: float
    final_usd: float
    profit_usd: float
    net_return_pct: float
    profitable_capacity_usd: float
    nusd_balance: float
    dai_balance: float
    usdc_balance: float
    usdt_balance: float
    quotes: tuple[ZenchaQuote, ...]
    opportunity: bool
    caveat: str


def scan_boba_synapse(
    rpc: EthereumRpcClient,
    min_net_return_pct: float = 0.001,
    coinbase_url: str = "https://api.exchange.coinbase.com",
    sizes_usd: tuple[float, ...] = SIZES_USD,
) -> BobaSynapseProbe:
    chain_id = rpc.chain_id()
    if chain_id != 288:
        raise RuntimeError(f"Boba Synapse probe requires Boba mainnet, got chain_id={chain_id}.")
    block_number = rpc.block_number()
    _verify_tokens(rpc, block_number)
    balances = tuple(_token_balance(rpc, index, block_number) / 10**decimals for index, (_, _, decimals) in enumerate(TOKENS))
    tickers = {"USDC": (1.0, 1.0), "USDT": _coinbase_ticker(coinbase_url, "USDT-USD")}
    eth_bid, _ = _coinbase_ticker(coinbase_url, "ETH-USD")
    gas_cost_usd = 180_000 * rpc.gas_price() / 10**18 * eth_bid
    quotes = tuple(
        _quote(rpc, block_number, token_in, token_out, size_usd, tickers, gas_cost_usd)
        for size_usd in sizes_usd
        for token_in, token_out in TRADE_PAIRS
    )
    best = max(quotes, key=lambda quote: quote.final_usd - quote.start_usd)
    profitable_capacity_usd = max(
        (quote.start_usd for quote in quotes if quote.net_return_pct >= min_net_return_pct),
        default=0.0,
    )
    return BobaSynapseProbe(
        observed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        chain_id=chain_id,
        block_number=block_number,
        route=best.route,
        start_usd=best.start_usd,
        final_usd=best.final_usd,
        profit_usd=best.final_usd - best.start_usd,
        net_return_pct=best.net_return_pct,
        profitable_capacity_usd=profitable_capacity_usd,
        nusd_balance=balances[0],
        dai_balance=balances[1],
        usdc_balance=balances[2],
        usdt_balance=balances[3],
        quotes=quotes,
        opportunity=best.net_return_pct >= min_net_return_pct,
        caveat="paper-only: nUSD routes are quarantined; bridge fees, CEX inventory, and withdrawal availability are not modeled",
    )


def append_boba_synapse_probe(path: Path, probe: BobaSynapseProbe) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(probe), separators=(",", ":")) + "\n")


def format_boba_synapse_probe(probe: BobaSynapseProbe) -> str:
    label = "candidate" if probe.opportunity else "none"
    return (
        f"[BobaSynapse] {label}: {probe.route} start=${probe.start_usd:.2f} "
        f"profit=${probe.profit_usd:+.4f} net={probe.net_return_pct:+.4%} "
        f"capacity>=${probe.profitable_capacity_usd:.0f} "
        f"pool=nUSD {probe.nusd_balance:.2f}/DAI {probe.dai_balance:.2f}/USDC {probe.usdc_balance:.2f}/USDT {probe.usdt_balance:.2f}"
    )


def _quote(
    rpc: EthereumRpcClient,
    block_number: int,
    token_in: int,
    token_out: int,
    start_usd: float,
    tickers: dict[str, tuple[float, float]],
    gas_cost_usd: float,
) -> ZenchaQuote:
    in_symbol, _, in_decimals = TOKENS[token_in]
    out_symbol, _, out_decimals = TOKENS[token_out]
    _, in_ask = tickers[in_symbol]
    out_bid, _ = tickers[out_symbol]
    amount_in = int(start_usd / in_ask * 10**in_decimals)
    amount_out = _calculate_swap(rpc, token_in, token_out, amount_in, block_number)
    gross_final_usd = amount_out / 10**out_decimals * out_bid
    final_usd = gross_final_usd - gas_cost_usd
    return ZenchaQuote(
        route=f"{in_symbol}(CEX buy) -> {out_symbol}(Synapse swap) -> USD(CEX sell)",
        start_usd=start_usd,
        gross_final_usd=gross_final_usd,
        gas_cost_usd=gas_cost_usd,
        final_usd=final_usd,
        net_return_pct=final_usd / start_usd - 1,
    )


def _verify_tokens(rpc: EthereumRpcClient, block_number: int) -> None:
    for index, (_, expected, _) in enumerate(TOKENS):
        actual = _decode_address(rpc.eth_call_at(SYNAPSE_STABLE_POOL, _encode(GET_TOKEN, index), block_number))
        if actual != expected:
            raise RuntimeError(f"Unexpected Synapse token at index {index}: {actual}")


def _token_balance(rpc: EthereumRpcClient, index: int, block_number: int) -> int:
    return int(rpc.eth_call_at(SYNAPSE_STABLE_POOL, _encode(GET_TOKEN_BALANCE, index), block_number), 16)


def _calculate_swap(rpc: EthereumRpcClient, token_in: int, token_out: int, amount_in: int, block_number: int) -> int:
    return int(rpc.eth_call_at(SYNAPSE_STABLE_POOL, _encode(CALCULATE_SWAP, token_in, token_out, amount_in), block_number), 16)
