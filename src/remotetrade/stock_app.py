from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from remotetrade.clients import PolymarketClient, StooqClient
from remotetrade.config import Settings
from remotetrade.paper import PaperBroker
from remotetrade.stock_patterns import StockCategory, StockPattern, load_stock_patterns
from remotetrade.strategy import PolymarketLeadStrategy


@dataclass(frozen=True)
class StockTickResult:
    pattern_id: str
    line: str
    outcome: str


@dataclass(frozen=True)
class CategorySignal:
    category: StockCategory
    market_slug: str
    market_question: str
    yes_price: float
    odds_delta: float


def run_stock_patterns_once(settings: Settings, patterns_path: Path) -> list[StockTickResult]:
    polymarket = PolymarketClient(settings.gamma_url)
    stocks = StooqClient()
    patterns = load_stock_patterns(patterns_path)
    return [run_stock_once(pattern.apply(settings), pattern, polymarket, stocks) for pattern in patterns]


def run_stock_once(
    settings: Settings,
    pattern: StockPattern,
    polymarket: PolymarketClient,
    stocks: StooqClient,
) -> StockTickResult:
    broker = PaperBroker(settings.state_path, settings.trades_path, settings.start_cash_usd)
    strategy = PolymarketLeadStrategy(
        settings.entry_threshold,
        settings.strong_threshold,
        settings.take_profit_pct,
        settings.stop_loss_pct,
        settings.hold_seconds,
    )
    signal = _strongest_signal(pattern, broker, polymarket)

    if broker.state.position:
        current_symbol = broker.state.position.asset_id
        current_price = stocks.get_price(current_symbol)
    else:
        current_symbol = ""
        current_price = 0.0

    pnl_pct = broker.mark_to_market_pct(current_price) if broker.state.position else 0.0
    decision = strategy.decide(
        market=_market_stub(signal),
        odds_delta=signal.odds_delta if signal else None,
        position=broker.state.position,
        pnl_pct=pnl_pct,
    )

    target_symbol, target_side = _target_trade(pattern, signal)
    if decision.action == "OPEN" and target_symbol and target_side:
        price = stocks.get_price(target_symbol)
        notional = broker.size_for_trade(settings.risk_fraction, settings.max_trade_size_usd, settings.min_trade_size_usd)
        if notional == 0:
            outcome = "skip_size_too_small"
        else:
            outcome = broker.open_position(
                side=target_side,
                notional_usd=notional,
                price=price,
                market_slug=signal.market_slug if signal else "",
                signal=signal.odds_delta if signal else 0.0,
                asset_id=target_symbol,
            )
            current_symbol = target_symbol
            current_price = price
    elif decision.action == "CLOSE" and broker.state.position:
        outcome = broker.close_position(current_price, signal.odds_delta if signal else 0.0, decision.reason)
    else:
        broker.save()
        outcome = decision.action.lower()

    unrealized = broker.mark_to_market_pnl(current_price) if broker.state.position else 0.0
    unrealized_pct = broker.mark_to_market_pct(current_price) if broker.state.position else 0.0
    position = f"{broker.state.position.side} {broker.state.position.asset_id}" if broker.state.position else "NONE"
    signal_label = "n/a"
    if signal:
        signal_label = f"{signal.category.id}:{signal.odds_delta:+.3f} yes={signal.yes_price:.3f}"
    line = (
        f"[{pattern.label}] {outcome}: signal={signal_label} target={target_side or '-'} {target_symbol or '-'} "
        f"position={position} price={current_price:.2f} realized_pnl={broker.state.realized_pnl:.2f} "
        f"unrealized_pnl={unrealized:.2f} unrealized_pct={unrealized_pct:+.3%}"
    )
    return StockTickResult(pattern.id, line, outcome)


def _strongest_signal(
    pattern: StockPattern,
    broker: PaperBroker,
    polymarket: PolymarketClient,
) -> CategorySignal | None:
    best: CategorySignal | None = None
    for category in pattern.categories:
        markets = []
        for slug in category.market_slugs:
            try:
                markets.append(polymarket.find_market(slug, ""))
            except Exception:
                continue
        if not markets:
            try:
                markets = polymarket.search_markets(category.query, limit=1)
            except Exception:
                markets = []
        markets = [market for market in markets if _market_matches_category(category, market.slug, market.question)]
        if not markets:
            continue
        market = markets[0]
        key = f"stock:{category.id}:{market.slug}"
        odds_delta = broker.record_observation(market.slug, market.yes_price, observation_key=key)
        if odds_delta is None:
            continue
        signal = CategorySignal(category, market.slug, market.question, market.yes_price, odds_delta)
        if best is None or abs(signal.odds_delta) > abs(best.odds_delta):
            best = signal
    return best


def _market_matches_category(category: StockCategory, slug: str, question: str) -> bool:
    if category.market_slugs:
        return True
    terms = [
        term
        for term in category.query.lower().replace("/", " ").replace("-", " ").split()
        if term not in {"a", "an", "or", "the", "will", "by", "in", "on", "2026"}
    ]
    if not terms:
        return True
    haystack = f"{slug} {question}".lower()
    return any(term in haystack for term in terms)


def _target_trade(pattern: StockPattern, signal: CategorySignal | None) -> tuple[str | None, str | None]:
    if signal is None:
        return None, None

    if signal.odds_delta >= pattern.entry_threshold:
        long_symbols = signal.category.up_long
        short_symbols = signal.category.up_short
    elif signal.odds_delta <= -pattern.entry_threshold:
        long_symbols = signal.category.down_long
        short_symbols = signal.category.down_short
    else:
        return None, None

    if pattern.prefer_short and short_symbols:
        return short_symbols[0], "SHORT"
    if long_symbols:
        return long_symbols[0], "LONG"
    if short_symbols:
        return short_symbols[0], "SHORT"
    return None, None


def _market_stub(signal: CategorySignal | None):
    from remotetrade.clients import PredictionMarket

    if signal is None:
        return PredictionMarket("", "", "", 0.5, 0.5, {})
    return PredictionMarket("", signal.market_slug, signal.market_question, signal.yes_price, 1.0 - signal.yes_price, {})
