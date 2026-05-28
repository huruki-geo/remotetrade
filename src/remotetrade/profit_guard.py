from __future__ import annotations

from dataclasses import dataclass

from remotetrade.clients import OrderBook, OrderBookLevel


@dataclass(frozen=True)
class EffectiveFill:
    avg_price: float
    qty: float
    notional: float
    complete: bool


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    buy_venue: str
    sell_venue: str
    buy_avg_price: float
    sell_avg_price: float
    qty: float
    gross_profit_usd: float
    fees_usd: float
    net_profit_usd: float
    net_spread_pct: float
    reason: str


def evaluate_depth_arbitrage(
    buy_book: OrderBook,
    sell_book: OrderBook,
    notional_usd: float,
    fee_bps: float,
    min_net_spread_pct: float,
    safety_bps: float,
) -> GuardResult:
    buy = effective_buy(buy_book.asks, notional_usd)
    if not buy.complete or buy.qty <= 0:
        return _rejected(buy_book, sell_book, "insufficient_buy_depth")

    sell = effective_sell(sell_book.bids, buy.qty)
    if not sell.complete:
        return _rejected(buy_book, sell_book, "insufficient_sell_depth")

    fee_pct = fee_bps / 10_000
    safety_pct = safety_bps / 10_000
    gross_profit = sell.notional - buy.notional
    fees = (buy.notional + sell.notional) * fee_pct
    safety_cost = buy.notional * safety_pct
    net_profit = gross_profit - fees - safety_cost
    net_spread_pct = net_profit / buy.notional if buy.notional else 0.0
    allowed = net_spread_pct >= min_net_spread_pct
    return GuardResult(
        allowed=allowed,
        buy_venue=buy_book.venue,
        sell_venue=sell_book.venue,
        buy_avg_price=buy.avg_price,
        sell_avg_price=sell.avg_price,
        qty=buy.qty,
        gross_profit_usd=gross_profit,
        fees_usd=fees,
        net_profit_usd=net_profit,
        net_spread_pct=net_spread_pct,
        reason="allowed" if allowed else "net_spread_below_threshold",
    )


def best_depth_arbitrage(
    books: list[OrderBook],
    notional_usd: float,
    fee_bps: float,
    min_net_spread_pct: float,
    safety_bps: float,
) -> GuardResult | None:
    results: list[GuardResult] = []
    for buy_book in books:
        for sell_book in books:
            if buy_book.venue == sell_book.venue:
                continue
            result = evaluate_depth_arbitrage(
                buy_book,
                sell_book,
                notional_usd,
                fee_bps,
                min_net_spread_pct,
                safety_bps,
            )
            results.append(result)
    if not results:
        return None
    return max(results, key=lambda result: result.net_profit_usd)


def effective_buy(asks: list[OrderBookLevel], notional_usd: float) -> EffectiveFill:
    remaining = notional_usd
    qty = 0.0
    spent = 0.0
    for level in asks:
        take_notional = min(remaining, level.notional)
        take_qty = take_notional / level.price
        qty += take_qty
        spent += take_notional
        remaining -= take_notional
        if remaining <= 1e-9:
            break
    avg = spent / qty if qty else 0.0
    return EffectiveFill(avg, qty, spent, remaining <= 1e-9)


def effective_sell(bids: list[OrderBookLevel], qty: float) -> EffectiveFill:
    remaining = qty
    sold_qty = 0.0
    proceeds = 0.0
    for level in bids:
        take_qty = min(remaining, level.qty)
        sold_qty += take_qty
        proceeds += take_qty * level.price
        remaining -= take_qty
        if remaining <= 1e-12:
            break
    avg = proceeds / sold_qty if sold_qty else 0.0
    return EffectiveFill(avg, sold_qty, proceeds, remaining <= 1e-12)


def _rejected(buy_book: OrderBook, sell_book: OrderBook, reason: str) -> GuardResult:
    return GuardResult(
        allowed=False,
        buy_venue=buy_book.venue,
        sell_venue=sell_book.venue,
        buy_avg_price=0.0,
        sell_avg_price=0.0,
        qty=0.0,
        gross_profit_usd=0.0,
        fees_usd=0.0,
        net_profit_usd=0.0,
        net_spread_pct=0.0,
        reason=reason,
    )
