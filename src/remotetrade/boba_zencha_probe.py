from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from remotetrade.boba_cex_dex_probe import _coinbase_ticker
from remotetrade.dex_route_probe import EthereumRpcClient


ZENCHA_SWAP_FLASH_LOAN = "0x2d027b49b8960810f84d5fe172d07fff62311852"
DAI = "0xf74195bb8a5cf652411867c5c2c5b8c2a402be35"
USDC = "0x66a2a913e447d6b4bf33efbec43aaef87890fbbc"
USDT = "0x5de1677344d3cb0d7d465c10b72a8f60699c062d"
TOKENS = (
    ("DAI", DAI, 18),
    ("USDC", USDC, 6),
    ("USDT", USDT, 6),
)
SIZES_USD = (1.0, 5.0, 10.0, 20.0, 50.0, 100.0, 200.0, 500.0, 1_000.0, 2_000.0, 5_000.0)
TRADE_PAIRS = ((1, 2), (2, 1))

# Saddle SwapFlashLoan selectors.
GET_TOKEN = "0x82b86600"
GET_TOKEN_BALANCE = "0x91ceb3eb"
CALCULATE_SWAP = "0xa95b089f"


@dataclass(frozen=True)
class ZenchaQuote:
    route: str
    start_usd: float
    gross_final_usd: float
    gas_cost_usd: float
    final_usd: float
    net_return_pct: float


@dataclass(frozen=True)
class BobaZenchaProbe:
    observed_at: str
    chain_id: int
    block_number: int
    route: str
    start_usd: float
    gross_final_usd: float
    gas_cost_usd: float
    final_usd: float
    profit_usd: float
    net_return_pct: float
    profitable_capacity_usd: float
    dai_balance: float
    usdc_balance: float
    usdt_balance: float
    quotes: tuple[ZenchaQuote, ...]
    opportunity: bool
    caveat: str


@dataclass(frozen=True)
class BobaZenchaReport:
    observation_count: int
    opportunity_observations: int
    episode_count: int
    active: bool
    first_observed_at: str | None
    last_observed_at: str | None
    max_profit_usd: float
    max_profitable_capacity_usd: float
    theoretical_episode_profit_usd: float


def scan_boba_zencha(
    rpc: EthereumRpcClient,
    min_net_return_pct: float = 0.001,
    coinbase_url: str = "https://api.exchange.coinbase.com",
    sizes_usd: tuple[float, ...] = SIZES_USD,
) -> BobaZenchaProbe:
    chain_id = rpc.chain_id()
    if chain_id != 288:
        raise RuntimeError(f"Boba Zencha probe requires Boba mainnet, got chain_id={chain_id}.")
    block_number = rpc.block_number()
    _verify_tokens(rpc, block_number)
    balances = tuple(_token_balance(rpc, index, block_number) / 10**decimals for index, (_, _, decimals) in enumerate(TOKENS))
    tickers = {
        "USDC": (1.0, 1.0),
        "USDT": _coinbase_ticker(coinbase_url, "USDT-USD"),
    }
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
    return BobaZenchaProbe(
        observed_at=datetime.now(UTC).isoformat(timespec="seconds"),
        chain_id=chain_id,
        block_number=block_number,
        route=best.route,
        start_usd=best.start_usd,
        gross_final_usd=best.gross_final_usd,
        gas_cost_usd=best.gas_cost_usd,
        final_usd=best.final_usd,
        profit_usd=best.final_usd - best.start_usd,
        net_return_pct=best.net_return_pct,
        profitable_capacity_usd=profitable_capacity_usd,
        dai_balance=balances[0],
        usdc_balance=balances[1],
        usdt_balance=balances[2],
        quotes=quotes,
        opportunity=best.net_return_pct >= min_net_return_pct,
        caveat=(
            "paper-only: Zencha frontend availability, token redemption, bridge latency, bridge fee, "
            "CEX inventory, and withdrawal availability are not modeled"
        ),
    )


def append_boba_zencha_probe(path: Path, probe: BobaZenchaProbe) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(asdict(probe), separators=(",", ":")) + "\n")


def should_notify_boba_zencha(path: Path, probe: BobaZenchaProbe) -> bool:
    previous = _load_latest_boba_zencha_probe(path)
    return probe.opportunity and (previous is None or not previous.opportunity)


def build_boba_zencha_report(path: Path, max_gap_seconds: int = 600) -> BobaZenchaReport:
    probes = _load_boba_zencha_probes(path)
    episodes: list[list[BobaZenchaProbe]] = []
    active_episode = False
    for probe in probes:
        if not probe.opportunity:
            active_episode = False
            continue
        if not active_episode or _seconds_between(episodes[-1][-1], probe) > max_gap_seconds:
            episodes.append([])
        episodes[-1].append(probe)
        active_episode = True
    return BobaZenchaReport(
        observation_count=len(probes),
        opportunity_observations=sum(probe.opportunity for probe in probes),
        episode_count=len(episodes),
        active=bool(probes and probes[-1].opportunity),
        first_observed_at=probes[0].observed_at if probes else None,
        last_observed_at=probes[-1].observed_at if probes else None,
        max_profit_usd=max((probe.profit_usd for probe in probes), default=0.0),
        max_profitable_capacity_usd=max((probe.profitable_capacity_usd for probe in probes), default=0.0),
        theoretical_episode_profit_usd=sum(max(probe.profit_usd for probe in episode) for episode in episodes),
    )


def format_boba_zencha_report(report: BobaZenchaReport) -> str:
    state = "active" if report.active else "inactive"
    return (
        "[BobaZenchaReport] "
        f"observations={report.observation_count} candidates={report.opportunity_observations} "
        f"independent_episodes={report.episode_count} state={state} "
        f"max_profit=${report.max_profit_usd:.4f} capacity>=${report.max_profitable_capacity_usd:.0f} "
        f"theoretical_episode_profit=${report.theoretical_episode_profit_usd:.4f} "
        f"range={report.first_observed_at or 'none'}..{report.last_observed_at or 'none'}"
    )


def format_boba_zencha_probe(probe: BobaZenchaProbe) -> str:
    label = "candidate" if probe.opportunity else "none"
    return (
        f"[BobaZencha] {label}: {probe.route} start=${probe.start_usd:.2f} "
        f"gross=${probe.gross_final_usd:.4f} gas~=${probe.gas_cost_usd:.4f} "
        f"profit=${probe.profit_usd:+.4f} net={probe.net_return_pct:+.4%} "
        f"capacity>=${probe.profitable_capacity_usd:.0f} "
        f"pool=DAI {probe.dai_balance:.2f}/USDC {probe.usdc_balance:.2f}/USDT {probe.usdt_balance:.2f}"
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
        route=f"{in_symbol}(CEX buy) -> {out_symbol}(Zencha swap) -> USD(CEX sell)",
        start_usd=start_usd,
        gross_final_usd=gross_final_usd,
        gas_cost_usd=gas_cost_usd,
        final_usd=final_usd,
        net_return_pct=final_usd / start_usd - 1,
    )


def _verify_tokens(rpc: EthereumRpcClient, block_number: int) -> None:
    for index, (_, expected, _) in enumerate(TOKENS):
        actual = _decode_address(rpc.eth_call_at(ZENCHA_SWAP_FLASH_LOAN, _encode(GET_TOKEN, index), block_number))
        if actual != expected:
            raise RuntimeError(f"Unexpected Zencha token at index {index}: {actual}")


def _token_balance(rpc: EthereumRpcClient, index: int, block_number: int) -> int:
    return int(rpc.eth_call_at(ZENCHA_SWAP_FLASH_LOAN, _encode(GET_TOKEN_BALANCE, index), block_number), 16)


def _calculate_swap(rpc: EthereumRpcClient, token_in: int, token_out: int, amount_in: int, block_number: int) -> int:
    return int(rpc.eth_call_at(ZENCHA_SWAP_FLASH_LOAN, _encode(CALCULATE_SWAP, token_in, token_out, amount_in), block_number), 16)


def _encode(selector: str, *args: int) -> str:
    return selector + "".join(f"{arg:064x}" for arg in args)


def _decode_address(raw: str) -> str:
    return "0x" + raw[-40:].lower()


def _load_boba_zencha_probes(path: Path) -> list[BobaZenchaProbe]:
    if not path.exists():
        return []
    probes = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            probes.append(_decode_boba_zencha_probe(line))
    return probes


def _load_latest_boba_zencha_probe(path: Path) -> BobaZenchaProbe | None:
    if not path.exists():
        return None
    latest = None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                latest = line
    return _decode_boba_zencha_probe(latest) if latest is not None else None


def _decode_boba_zencha_probe(line: str) -> BobaZenchaProbe:
    payload = json.loads(line)
    payload["quotes"] = tuple(ZenchaQuote(**quote) for quote in payload["quotes"])
    return BobaZenchaProbe(**payload)


def _seconds_between(left: BobaZenchaProbe, right: BobaZenchaProbe) -> float:
    return (datetime.fromisoformat(right.observed_at) - datetime.fromisoformat(left.observed_at)).total_seconds()
