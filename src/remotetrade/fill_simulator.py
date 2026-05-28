from __future__ import annotations

from dataclasses import dataclass

from remotetrade.arbitrage import LimitArbitrageOrder
from remotetrade.clients import OrderBook
from remotetrade.profit_guard import effective_buy, effective_sell


@dataclass(frozen=True)
class LimitFillResult:
    outcome: str
    buy_filled: bool
    sell_filled: bool
    hedge_cost_usd: float
    reason: str


def simulate_limit_pair_fill(
    order: LimitArbitrageOrder,
    buy_book_after: OrderBook,
    sell_book_after: OrderBook,
) -> LimitFillResult:
    buy_filled = bool(buy_book_after.asks and buy_book_after.best_ask <= order.buy_limit)
    sell_filled = bool(sell_book_after.bids and sell_book_after.best_bid >= order.sell_limit)

    if buy_filled and sell_filled:
        return LimitFillResult("both_filled", True, True, 0.0, "both_limits_crossed")
    if not buy_filled and not sell_filled:
        return LimitFillResult("none", False, False, 0.0, "neither_limit_crossed")

    if buy_filled:
        hedge = effective_sell(sell_book_after.bids, order.qty)
        hedge_cost = max(0.0, order.notional_usd - hedge.notional) if hedge.complete else order.notional_usd
        return LimitFillResult("buy_only", True, False, hedge_cost, "sell_leg_missed")

    hedge = effective_buy(buy_book_after.asks, order.notional_usd)
    expected_buy_cost = order.qty * order.buy_limit
    hedge_cost = max(0.0, hedge.notional - expected_buy_cost) if hedge.complete else order.notional_usd
    return LimitFillResult("sell_only", False, True, hedge_cost, "buy_leg_missed")
