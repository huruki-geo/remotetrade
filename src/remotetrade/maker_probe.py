from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from remotetrade.venue_discovery import BitbankPublicClient, GmoCoinPublicClient


@dataclass(frozen=True)
class MakerProbeTarget:
    venue: str
    symbol: str


@dataclass(frozen=True)
class MakerProbeObservation:
    time: str
    venue: str
    symbol: str
    bid: float
    ask: float
    spread_bps: float
    maker_fee_bps: float
    taker_fee_bps: float
    maker_round_trip_edge_bps: float
    bid_depth_quote: float
    ask_depth_quote: float


@dataclass(frozen=True)
class MakerProbeReport:
    venue: str
    symbol: str
    quotes: int
    both_filled: int
    buy_only: int
    sell_only: int
    unfilled: int
    average_hedged_pnl_bps: float
    average_markout_bps: float


DEFAULT_TARGETS = (
    MakerProbeTarget("bitbank", "mana_jpy"),
    MakerProbeTarget("bitbank", "omg_jpy"),
)


def fetch_maker_probe_observations(
    targets: tuple[MakerProbeTarget, ...] = DEFAULT_TARGETS,
    depth_levels: int = 5,
    bitbank_client: BitbankPublicClient | None = None,
    gmo_client: GmoCoinPublicClient | None = None,
) -> list[MakerProbeObservation]:
    bitbank_targets = [target for target in targets if target.venue == "bitbank"]
    gmo_targets = [target for target in targets if target.venue == "gmo_coin"]
    observations: list[MakerProbeObservation] = []

    if bitbank_targets:
        client = bitbank_client or BitbankPublicClient()
        rules = {str(rule["name"]): rule for rule in client.get_pairs()}
        for target in bitbank_targets:
            rule = rules.get(target.symbol)
            if rule is None:
                continue
            book = client.get_order_book(target.symbol)
            bids = book.get("bids") or []
            asks = book.get("asks") or []
            observations.append(
                _observation(
                    target,
                    bids,
                    asks,
                    float(rule["maker_fee_rate_quote"]) * 10_000,
                    float(rule["taker_fee_rate_quote"]) * 10_000,
                )
            )

    if gmo_targets:
        client = gmo_client or GmoCoinPublicClient()
        rules = {str(rule["symbol"]): rule for rule in client.get_symbols()}
        for target in gmo_targets:
            rule = rules.get(target.symbol)
            if rule is None:
                continue
            book = client.get_order_book(target.symbol)
            bids = [[level["price"], level["size"]] for level in book.get("bids") or []]
            asks = [[level["price"], level["size"]] for level in book.get("asks") or []]
            observations.append(
                _observation(
                    target,
                    bids,
                    asks,
                    float(rule["makerFee"]) * 10_000,
                    float(rule["takerFee"]) * 10_000,
                    depth_levels,
                )
            )

    return observations


def append_maker_probe_observations(path: Path, observations: list[MakerProbeObservation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(MakerProbeObservation.__dataclass_fields__))
        if not exists:
            writer.writeheader()
        for observation in observations:
            writer.writerow(asdict(observation))


def format_maker_probe_observations(observations: list[MakerProbeObservation]) -> str:
    lines = ["Maker probe tick"]
    for observation in observations:
        lines.append(
            f"[MakerProbe {observation.venue}:{observation.symbol}] "
            f"bid={observation.bid:g} ask={observation.ask:g} spread={observation.spread_bps:.2f}bps "
            f"maker_rt={observation.maker_round_trip_edge_bps:+.2f}bps "
            f"depth={min(observation.bid_depth_quote, observation.ask_depth_quote):.0f}"
        )
    return "\n".join(lines)


def build_maker_probe_reports(path: Path) -> list[MakerProbeReport]:
    grouped: dict[tuple[str, str], list[MakerProbeObservation]] = {}
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            observation = _observation_from_row(row)
            grouped.setdefault((observation.venue, observation.symbol), []).append(observation)

    reports: list[MakerProbeReport] = []
    for (venue, symbol), rows in sorted(grouped.items()):
        both_filled = 0
        buy_only = 0
        sell_only = 0
        unfilled = 0
        hedged_pnls: list[float] = []
        markouts: list[float] = []
        for index, (placed, current) in enumerate(zip(rows, rows[1:])):
            buy_filled = current.ask <= placed.bid
            sell_filled = current.bid >= placed.ask
            if buy_filled and sell_filled:
                both_filled += 1
                hedged_pnls.append(_round_trip_bps(placed.bid, placed.ask) - placed.maker_fee_bps * 2)
            elif buy_filled:
                buy_only += 1
                hedged_pnls.append(_round_trip_bps(placed.bid, current.bid) - placed.maker_fee_bps - placed.taker_fee_bps)
            elif sell_filled:
                sell_only += 1
                hedged_pnls.append(_round_trip_bps(current.ask, placed.ask) - placed.maker_fee_bps - placed.taker_fee_bps)
            else:
                unfilled += 1
            if index + 2 >= len(rows):
                continue
            future_mid = (rows[index + 2].bid + rows[index + 2].ask) / 2
            if buy_filled:
                markouts.append((future_mid / placed.bid - 1) * 10_000)
            if sell_filled:
                markouts.append((placed.ask / future_mid - 1) * 10_000)
        reports.append(
            MakerProbeReport(
                venue=venue,
                symbol=symbol,
                quotes=max(0, len(rows) - 1),
                both_filled=both_filled,
                buy_only=buy_only,
                sell_only=sell_only,
                unfilled=unfilled,
                average_hedged_pnl_bps=_average(hedged_pnls),
                average_markout_bps=_average(markouts),
            )
        )
    return reports


def format_maker_probe_reports(reports: list[MakerProbeReport]) -> str:
    lines = ["**Small maker probe replay**"]
    for report in reports:
        lines.append(
            f"- `{report.venue}:{report.symbol}` quotes `{report.quotes}` / both `{report.both_filled}` "
            f"/ buy-only `{report.buy_only}` / sell-only `{report.sell_only}` / unfilled `{report.unfilled}` "
            f"/ hedged pnl `{report.average_hedged_pnl_bps:+.2f}bps` / markout `{report.average_markout_bps:+.2f}bps`"
        )
    return "\n".join(lines)


def _observation(
    target: MakerProbeTarget,
    bids: list[Any],
    asks: list[Any],
    maker_fee_bps: float,
    taker_fee_bps: float,
    depth_levels: int = 5,
) -> MakerProbeObservation:
    if not bids or not asks:
        raise RuntimeError(f"No maker probe book for {target.venue}:{target.symbol}.")
    bid = float(bids[0][0])
    ask = float(asks[0][0])
    if bid <= 0 or ask <= bid:
        raise RuntimeError(f"Invalid maker probe quote for {target.venue}:{target.symbol}.")
    spread_bps = (ask - bid) / ((ask + bid) / 2) * 10_000
    return MakerProbeObservation(
        time=datetime.now(UTC).isoformat(timespec="seconds"),
        venue=target.venue,
        symbol=target.symbol,
        bid=bid,
        ask=ask,
        spread_bps=spread_bps,
        maker_fee_bps=maker_fee_bps,
        taker_fee_bps=taker_fee_bps,
        maker_round_trip_edge_bps=spread_bps - maker_fee_bps * 2,
        bid_depth_quote=_depth_quote(bids, depth_levels),
        ask_depth_quote=_depth_quote(asks, depth_levels),
    )


def _depth_quote(levels: list[Any], depth_levels: int) -> float:
    return sum(float(price) * float(size) for price, size in levels[:depth_levels])


def _observation_from_row(row: dict[str, str]) -> MakerProbeObservation:
    return MakerProbeObservation(
        time=row["time"],
        venue=row["venue"],
        symbol=row["symbol"],
        bid=float(row["bid"]),
        ask=float(row["ask"]),
        spread_bps=float(row["spread_bps"]),
        maker_fee_bps=float(row["maker_fee_bps"]),
        taker_fee_bps=float(row["taker_fee_bps"]),
        maker_round_trip_edge_bps=float(row["maker_round_trip_edge_bps"]),
        bid_depth_quote=float(row["bid_depth_quote"]),
        ask_depth_quote=float(row["ask_depth_quote"]),
    )


def _round_trip_bps(buy_price: float, sell_price: float) -> float:
    return (sell_price / buy_price - 1) * 10_000


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
