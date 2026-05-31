from __future__ import annotations

import argparse
import time
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from remotetrade.arbitrage import (
    append_arbitrage_tick,
    append_limit_arbitrage_tick,
    default_venues,
    fetch_order_books,
    fetch_quotes,
    scan_arbitrage,
    scan_limit_arbitrage,
)
from remotetrade.clients import Candle, CoinbaseClient, PolymarketClient
from remotetrade.config import Settings
from remotetrade.health import build_health_report
from remotetrade.limit_paper import LimitPaperBroker, adapt_limit_parameters, find_limit_candidate
from remotetrade.notify import format_discord_error, format_discord_tick, send_discord_message
from remotetrade.paper import PaperBroker
from remotetrade.patterns import Pattern, load_patterns
from remotetrade.polymarket_clob import collect_btc_5m_market_events
from remotetrade.polymarket_replay import build_replay_report, format_replay_report, write_replay_report
from remotetrade.polymarket_rtds import collect_crypto_prices
from remotetrade.profit_guard import best_depth_arbitrage
from remotetrade.report import build_daily_report
from remotetrade.spread import SpreadPaperBroker, best_spread_snapshot, decide_spread, zscore
from remotetrade.stock_app import run_stock_patterns_once
from remotetrade.strategy import PolymarketLeadStrategy
from remotetrade.variants import LimitPaperVariant, file_suffix, load_limit_paper_variants
from remotetrade.venue_discovery import append_market_discoveries, format_market_discoveries, scan_low_cost_markets
from remotetrade.wick import WickReversalStrategy, detect_wick_signal


@dataclass(frozen=True)
class TickResult:
    pattern_id: str
    line: str
    outcome: str


def run_arbitrage_once(settings: Settings) -> TickResult:
    quotes = fetch_quotes(default_venues(settings.crypto_product_id))
    opportunities = scan_arbitrage(
        quotes,
        notional_usd=settings.arbitrage_notional_usd,
        fee_bps=settings.arbitrage_fee_bps,
        min_net_spread_pct=settings.arbitrage_min_net_spread_pct,
    )
    append_arbitrage_tick(settings.arbitrage_ticks_path, quotes, opportunities)
    if opportunities:
        best = opportunities[0]
        line = (
            f"[Arbitrage] opportunity: buy={best.buy_venue} ask={best.buy_ask:.2f} "
            f"sell={best.sell_venue} bid={best.sell_bid:.2f} "
            f"net_spread={best.net_spread_pct:+.3%} est_profit=${best.estimated_profit_usd:.2f} "
            f"notional=${best.notional_usd:.2f}"
        )
        return TickResult("arbitrage", line, "opportunity")

    quote_line = " ".join(f"{quote.venue} bid={quote.bid:.2f} ask={quote.ask:.2f}" for quote in quotes)
    return TickResult("arbitrage", f"[Arbitrage] none: {quote_line}", "none")


def run_limit_arbitrage_once(settings: Settings) -> TickResult:
    quotes = fetch_quotes(default_venues(settings.crypto_product_id))
    orders = scan_limit_arbitrage(
        quotes,
        notional_usd=settings.arbitrage_notional_usd,
        maker_fee_bps=settings.limit_maker_fee_bps,
        min_net_spread_pct=settings.arbitrage_min_net_spread_pct,
        price_improvement_bps=settings.limit_price_improvement_bps,
    )
    data_dir = settings.state_path.parent
    append_limit_arbitrage_tick(data_dir / "limit_arbitrage_ticks.csv", quotes, orders)
    if orders:
        best = orders[0]
        line = (
            f"[LimitArb] quote: buy={best.buy_venue} limit={best.buy_limit:.2f} "
            f"sell={best.sell_venue} limit={best.sell_limit:.2f} qty={best.qty:.10f} "
            f"net_spread={best.net_spread_pct:+.3%} est_profit=${best.estimated_profit_usd:.2f}"
        )
        return TickResult("limit_arbitrage", line, "opportunity")

    quote_line = " ".join(f"{quote.venue} bid={quote.bid:.2f} ask={quote.ask:.2f}" for quote in quotes)
    return TickResult("limit_arbitrage", f"[LimitArb] none: {quote_line}", "none")


def run_depth_arbitrage_once(settings: Settings) -> TickResult:
    books = fetch_order_books(default_venues(settings.crypto_product_id))
    best = best_depth_arbitrage(
        books,
        notional_usd=settings.arbitrage_notional_usd,
        fee_bps=settings.arbitrage_fee_bps,
        min_net_spread_pct=settings.arbitrage_min_net_spread_pct,
        safety_bps=settings.arbitrage_safety_bps,
    )
    if best and best.allowed:
        line = (
            f"[DepthArb] opportunity: buy={best.buy_venue} avg={best.buy_avg_price:.2f} "
            f"sell={best.sell_venue} avg={best.sell_avg_price:.2f} qty={best.qty:.10f} "
            f"net_spread={best.net_spread_pct:+.3%} net_profit=${best.net_profit_usd:.2f}"
        )
        return TickResult("depth_arbitrage", line, "opportunity")

    if best:
        line = (
            f"[DepthArb] none: best={best.buy_venue}->{best.sell_venue} "
            f"net_spread={best.net_spread_pct:+.3%} reason={best.reason}"
        )
        return TickResult("depth_arbitrage", line, "none")
    return TickResult("depth_arbitrage", "[DepthArb] none: no_books", "none")


def run_limit_paper_once(settings: Settings) -> TickResult:
    return run_limit_paper_for(
        settings,
        product_id=settings.crypto_product_id,
        variant=LimitPaperVariant(
            "default",
            settings.arbitrage_min_net_spread_pct,
            settings.limit_price_improvement_bps,
        ),
        suffix="",
    )


def run_limit_paper_for(
    settings: Settings,
    product_id: str,
    variant: LimitPaperVariant,
    suffix: str,
) -> TickResult:
    data_dir = settings.state_path.parent
    books = fetch_order_books(default_venues(product_id))
    file_prefix = "limit_paper" if not suffix else f"limit_paper_{suffix}"
    broker = LimitPaperBroker(
        data_dir / f"{file_prefix}_state.json",
        data_dir / f"{file_prefix}_trades.csv",
        data_dir / f"{file_prefix}_ticks.csv",
        data_dir / f"orderbook_snapshots{'' if not suffix else '_' + suffix}.jsonl",
        settings.start_cash_usd,
        settings.limit_maker_fee_bps,
        settings.limit_taker_fee_bps,
        settings.limit_order_ttl_ticks,
    )
    broker.append_snapshots(books)
    fill_outcome, fill_pnl, fill_result = broker.evaluate_pending(books)
    tuning = adapt_limit_parameters(
        broker.state,
        variant.min_net_spread_pct,
        variant.price_improvement_bps,
        settings.limit_max_hedge_slippage_bps,
    )
    candidate = None
    place_outcome = "no_candidate"
    if broker.state.pending is None:
        candidate = find_limit_candidate(
            books,
            settings.arbitrage_notional_usd,
            settings.limit_maker_fee_bps,
            tuning.min_net_spread_pct,
            tuning.price_improvement_bps,
            tuning.max_hedge_slippage_bps,
        )
        if candidate:
            place_outcome = broker.place_order(candidate)
    broker.append_tick(place_outcome if fill_outcome == "no_pending" else fill_outcome, candidate, fill_pnl)

    pending_label = "NONE"
    if broker.state.pending:
        pending_label = (
            f"{broker.state.pending.buy_venue}@{broker.state.pending.buy_limit:.2f}/"
            f"{broker.state.pending.sell_venue}@{broker.state.pending.sell_limit:.2f}"
        )
    fill_label = fill_result.outcome if fill_result else fill_outcome
    line = (
        f"[LimitPaper {product_id} {variant.id}] {place_outcome if fill_outcome == 'no_pending' else fill_outcome}: "
        f"fill={fill_label} pnl={fill_pnl:+.4f} realized_pnl={broker.state.realized_pnl:.4f} "
        f"pending={pending_label} both={broker.state.both_filled} "
        f"one_leg={broker.state.buy_only + broker.state.sell_only} expired={broker.state.expired} "
        f"tune={tuning.mode} min_net={tuning.min_net_spread_pct:.4%} "
        f"improve={tuning.price_improvement_bps:.2f}bps hedge_slip={tuning.max_hedge_slippage_bps:.1f}bps"
    )
    return TickResult(f"limit_paper_{product_id}_{variant.id}", line, place_outcome if place_outcome != "no_candidate" else fill_outcome)


def run_portfolio_paper_once(settings: Settings) -> list[TickResult]:
    results: list[TickResult] = []
    variants = load_limit_paper_variants(settings.limit_paper_variants)
    for product_id in settings.crypto_product_ids:
        for variant in variants:
            results.append(run_limit_paper_for(settings, product_id, variant, file_suffix(product_id, variant.id)))
    return results


def run_wick_once(settings: Settings, coinbase: CoinbaseClient | None = None) -> TickResult:
    data_dir = settings.state_path.parent
    wick_settings = replace(
        settings,
        state_path=data_dir / "wick_state.json",
        trades_path=data_dir / "wick_trades.csv",
        ticks_path=data_dir / "wick_ticks.csv",
    )
    coinbase = coinbase or CoinbaseClient(settings.coinbase_url)
    broker = PaperBroker(
        wick_settings.state_path,
        wick_settings.trades_path,
        wick_settings.start_cash_usd,
        wick_settings.ticks_path,
    )
    candles = coinbase.get_candles(settings.crypto_product_id, settings.wick_granularity_seconds)
    candle = _latest_closed_candle(candles, settings.wick_granularity_seconds)
    signal = detect_wick_signal(candle, settings.wick_min_ratio, settings.wick_min_range_pct)
    strategy = WickReversalStrategy(settings.take_profit_pct, settings.stop_loss_pct, settings.hold_seconds)
    pnl_pct = broker.mark_to_market_pct(candle.close)
    decision = strategy.decide(signal, broker.state.position, pnl_pct)

    if decision.action == "OPEN" and decision.side:
        notional = broker.size_for_trade(settings.risk_fraction, settings.max_trade_size_usd, settings.min_trade_size_usd)
        if notional == 0:
            outcome = "skip_size_too_small"
        else:
            outcome = broker.open_position(
                side=decision.side,
                notional_usd=notional,
                price=candle.close,
                market_slug=_wick_slug(settings.crypto_product_id, settings.wick_granularity_seconds, candle),
                signal=signal.strength if signal else 0.0,
                asset_id=settings.crypto_product_id,
            )
    elif decision.action == "CLOSE":
        outcome = broker.close_position(candle.close, signal.strength if signal else 0.0, decision.reason)
    else:
        broker.save()
        outcome = decision.action.lower()

    unrealized = broker.mark_to_market_pnl(candle.close)
    unrealized_pct = broker.mark_to_market_pct(candle.close)
    position = broker.state.position.side if broker.state.position else "NONE"
    signal_label = "n/a" if signal is None else f"{signal.side}:{signal.strength:.3f}"
    line = (
        f"[Wick] {outcome}: {settings.crypto_product_id} close={candle.close:.2f} "
        f"range={candle.range:.2f} signal={signal_label} position={position} "
        f"realized_pnl={broker.state.realized_pnl:.2f} unrealized_pnl={unrealized:.2f} "
        f"unrealized_pct={unrealized_pct:+.3%}"
    )
    broker.append_tick(
        "wick",
        _wick_slug(settings.crypto_product_id, settings.wick_granularity_seconds, candle),
        settings.crypto_product_id,
        candle.close,
        candle.close,
        signal.strength if signal else None,
        outcome,
        unrealized,
        unrealized_pct,
    )
    return TickResult("wick", line, outcome)


def run_spread_once(settings: Settings) -> TickResult:
    quotes = fetch_quotes(default_venues(settings.crypto_product_id))
    snapshot = best_spread_snapshot(quotes)
    data_dir = settings.state_path.parent
    broker = SpreadPaperBroker(
        data_dir / "spread_state.json",
        data_dir / "spread_trades.csv",
        settings.start_cash_usd,
        settings.spread_window,
    )
    observations = broker.record_observation(snapshot.spread_pct)
    spread_zscore = zscore(snapshot.spread_pct, observations[:-1])
    pnl_pct = broker.mark_to_market_pct(snapshot)
    decision = decide_spread(
        broker.state.position,
        spread_zscore,
        settings.spread_entry_zscore,
        settings.spread_exit_zscore,
        settings.spread_stop_zscore,
        pnl_pct,
        settings.stop_loss_pct,
    )

    if decision.action == "OPEN":
        outcome = broker.open_position(snapshot, settings.spread_notional_usd, spread_zscore)
    elif decision.action == "CLOSE":
        outcome = broker.close_position(snapshot, decision.reason)
    else:
        broker.save()
        outcome = decision.action.lower()

    unrealized = broker.mark_to_market_pnl(snapshot)
    unrealized_pct = broker.mark_to_market_pct(snapshot)
    broker.append_tick(data_dir / "spread_ticks.csv", snapshot, spread_zscore, outcome)
    position = "NONE"
    if broker.state.position:
        position = f"LONG {broker.state.position.long_venue} / SHORT {broker.state.position.short_venue}"
    line = (
        f"[Spread] {outcome}: long={snapshot.long_venue} mid={snapshot.long_mid:.2f} "
        f"short={snapshot.short_venue} mid={snapshot.short_mid:.2f} spread={snapshot.spread_pct:+.3%} "
        f"z={spread_zscore:+.2f} position={position} realized_pnl={broker.state.realized_pnl:.2f} "
        f"unrealized_pnl={unrealized:.2f} unrealized_pct={unrealized_pct:+.3%}"
    )
    return TickResult("spread", line, outcome)


def _latest_closed_candle(candles: list[Candle], granularity_seconds: int) -> Candle:
    if not candles:
        raise RuntimeError("No Coinbase candles returned.")
    cutoff = datetime.now(UTC) - timedelta(seconds=granularity_seconds)
    closed = [candle for candle in candles if candle.time <= cutoff]
    return closed[-1] if closed else candles[-1]


def _wick_slug(product_id: str, granularity_seconds: int, candle: Candle) -> str:
    return f"wick:{product_id}:{granularity_seconds}:{int(candle.time.timestamp())}"


def run_once(
    settings: Settings,
    polymarket: PolymarketClient | None = None,
    coinbase: CoinbaseClient | None = None,
    pattern: Pattern | None = None,
) -> TickResult:
    polymarket = polymarket or PolymarketClient(settings.gamma_url)
    coinbase = coinbase or CoinbaseClient(settings.coinbase_url)
    broker = PaperBroker(settings.state_path, settings.trades_path, settings.start_cash_usd, settings.ticks_path)
    strategy = PolymarketLeadStrategy(
        settings.entry_threshold,
        settings.strong_threshold,
        settings.take_profit_pct,
        settings.stop_loss_pct,
        settings.hold_seconds,
    )

    market = polymarket.find_market(settings.market_slug, settings.market_query)
    spot_price = coinbase.get_price(settings.crypto_product_id)
    odds_delta = broker.record_observation(market.slug, market.yes_price)
    pnl_pct = broker.mark_to_market_pct(spot_price)
    decision = strategy.decide(market, odds_delta, broker.state.position, pnl_pct)

    if decision.action == "OPEN" and decision.side:
        notional = broker.size_for_trade(settings.risk_fraction, settings.max_trade_size_usd, settings.min_trade_size_usd)
        if notional == 0:
            outcome = "skip_size_too_small"
        else:
            outcome = broker.open_position(
                side=decision.side,
                notional_usd=notional,
                price=spot_price,
                market_slug=market.slug,
                signal=odds_delta or 0.0,
                asset_id=settings.crypto_product_id,
            )
    elif decision.action == "CLOSE":
        outcome = broker.close_position(spot_price, odds_delta or 0.0, decision.reason)
    else:
        broker.save()
        outcome = decision.action.lower()

    unrealized = broker.mark_to_market_pnl(spot_price)
    unrealized_pct = broker.mark_to_market_pct(spot_price)
    position = broker.state.position.side if broker.state.position else "NONE"
    delta_label = "n/a" if odds_delta is None else f"{odds_delta:+.3f}"
    pattern_label = pattern.label if pattern else "default"
    line = (
        f"[{pattern_label}] {outcome}: {settings.crypto_product_id} spot={spot_price:.2f} "
        f"up={market.yes_price:.3f} odds_delta={delta_label} "
        f"position={position} realized_pnl={broker.state.realized_pnl:.2f} "
        f"unrealized_pnl={unrealized:.2f} unrealized_pct={unrealized_pct:+.3%}"
    )
    broker.append_tick(
        pattern.id if pattern else "default",
        market.slug,
        settings.crypto_product_id,
        spot_price,
        market.yes_price,
        odds_delta,
        outcome,
        unrealized,
        unrealized_pct,
    )
    return TickResult(pattern.id if pattern else "default", line, outcome)


def run_patterns_once(settings: Settings, patterns_path: Path) -> list[TickResult]:
    patterns = load_patterns(patterns_path)
    polymarket = PolymarketClient(settings.gamma_url)
    coinbase = CoinbaseClient(settings.coinbase_url)
    return [run_once(pattern.apply(settings), polymarket, coinbase, pattern) for pattern in patterns]


def has_trade_event(results: list[TickResult]) -> bool:
    return any(result.outcome in {"opened", "closed", "skip_size_too_small", "opportunity"} for result in results)


def maybe_send_discord(message: str, results: list[TickResult] | None = None, events_only: bool = False) -> None:
    if events_only and results is not None and not has_trade_event(results):
        print("discord notification skipped: no trade event", flush=True)
        return
    try:
        if send_discord_message(message):
            print("discord notification sent", flush=True)
    except Exception as exc:
        print(f"discord notification failed: {exc}", flush=True)


def notify_tick(title: str, results: list[TickResult], enabled: bool, events_only: bool) -> None:
    if not enabled:
        return
    message = format_discord_tick(title, [result.line for result in results])
    maybe_send_discord(message, results, events_only)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Polymarket-led crypto paper trading.")
    parser.add_argument("--once", action="store_true", help="Evaluate one tick and exit.")
    parser.add_argument("--patterns", type=Path, help="Run multiple paper-trading patterns from a JSON file.")
    parser.add_argument("--stock-patterns", type=Path, help="Run stock paper-trading patterns from a JSON file.")
    parser.add_argument("--arbitrage", action="store_true", help="Scan exchange bid/ask spreads for paper arbitrage.")
    parser.add_argument("--limit-arbitrage", action="store_true", help="Quote post-only limit arbitrage candidates.")
    parser.add_argument("--depth-arbitrage", action="store_true", help="Scan depth-adjusted arbitrage opportunities.")
    parser.add_argument("--limit-paper", action="store_true", help="Run post-only limit arbitrage paper fills.")
    parser.add_argument("--portfolio-paper", action="store_true", help="Run limit paper across configured products and variants.")
    parser.add_argument("--wick", action="store_true", help="Run candle-wick reversal paper trading.")
    parser.add_argument("--spread", action="store_true", help="Run cross-exchange spread mean-reversion paper trading.")
    parser.add_argument("--report", action="store_true", help="Print a daily paper-trading report.")
    parser.add_argument("--health-check", action="store_true", help="Check data freshness and disk health.")
    parser.add_argument("--collect-poly-rtds", action="store_true", help="Collect public Polymarket RTDS crypto prices.")
    parser.add_argument("--collect-poly-clob", action="store_true", help="Collect public Polymarket BTC 5m CLOB events.")
    parser.add_argument("--poly-replay", action="store_true", help="Report Polymarket BTC 5m replay validation.")
    parser.add_argument("--discover-venues", action="store_true", help="Discover low-cost small-maker markets.")
    parser.add_argument("--discord", action="store_true", help="Send tick results to DISCORD_WEBHOOK_URL.")
    parser.add_argument("--discord-events-only", action="store_true", help="Notify Discord only when a trade event occurs.")
    parser.add_argument("--duration-seconds", type=int, help="Run for this many seconds, then exit.")
    args = parser.parse_args()

    settings = Settings.from_env()
    if args.collect_poly_rtds:
        collect_crypto_prices(settings.state_path.parent / "polymarket_crypto_prices.jsonl")
        return
    if args.collect_poly_clob:
        collect_btc_5m_market_events(
            settings.state_path.parent / "polymarket_btc_5m_clob.jsonl",
            settings.gamma_url,
            settings.market_query,
        )
        return
    if args.poly_replay:
        report = build_replay_report(
            settings.state_path.parent / "polymarket_btc_5m_clob.jsonl",
            settings.replay_required_win_rate,
            settings.replay_min_trades,
            settings.replay_imbalance_threshold,
            settings.replay_fee_per_share,
            settings.state_path.parent / "polymarket_crypto_prices.jsonl",
        )
        write_replay_report(settings.state_path.parent / "polymarket_btc_5m_replay.json", report)
        message = format_replay_report(report)
        print(message, flush=True)
        if args.discord:
            maybe_send_discord(message)
        return
    if args.discover_venues:
        discoveries = scan_low_cost_markets(
            max_order_notional_jpy=settings.discovery_max_order_notional_jpy,
            max_order_notional_usdt=settings.discovery_max_order_notional_usdt,
            min_depth_jpy=settings.discovery_min_depth_jpy,
            min_depth_usdt=settings.discovery_min_depth_usdt,
            max_spread_bps=settings.discovery_max_spread_bps,
        )
        append_market_discoveries(settings.state_path.parent / "venue_market_discoveries.jsonl", discoveries)
        message = format_market_discoveries(discoveries)
        print(message, flush=True)
        if args.discord:
            maybe_send_discord(message)
        return
    deadline = datetime.now(UTC) + timedelta(seconds=args.duration_seconds) if args.duration_seconds else None
    while True:
        try:
            if args.patterns:
                results = run_patterns_once(settings, args.patterns)
                message = "Polymarket paper tick\n" + "\n".join(result.line for result in results)
                print(message, flush=True)
                notify_tick("Polymarket紙トレード", results, args.discord, args.discord_events_only)
            elif args.stock_patterns:
                results = run_stock_patterns_once(settings, args.stock_patterns)
                message = "Stock event paper tick\n" + "\n".join(result.line for result in results)
                print(message, flush=True)
                notify_tick("株式イベント紙トレード", results, args.discord, args.discord_events_only)
            elif args.arbitrage:
                result = run_arbitrage_once(settings)
                print(result.line, flush=True)
                notify_tick("裁定チェック", [result], args.discord, args.discord_events_only)
            elif args.limit_arbitrage:
                result = run_limit_arbitrage_once(settings)
                print(result.line, flush=True)
                notify_tick("指値裁定候補", [result], args.discord, args.discord_events_only)
            elif args.depth_arbitrage:
                result = run_depth_arbitrage_once(settings)
                print(result.line, flush=True)
                notify_tick("板厚込み裁定チェック", [result], args.discord, args.discord_events_only)
            elif args.limit_paper:
                result = run_limit_paper_once(settings)
                print(result.line, flush=True)
                notify_tick("指値裁定紙トレード", [result], args.discord, args.discord_events_only)
            elif args.portfolio_paper:
                results = run_portfolio_paper_once(settings)
                message = "Portfolio paper tick\n" + "\n".join(result.line for result in results)
                print(message, flush=True)
                notify_tick("ポートフォリオ紙トレード", results, args.discord, args.discord_events_only)
            elif args.wick:
                result = run_wick_once(settings)
                print(result.line, flush=True)
                notify_tick("ひげ取り紙トレード", [result], args.discord, args.discord_events_only)
            elif args.spread:
                result = run_spread_once(settings)
                print(result.line, flush=True)
                notify_tick("スプレッド紙トレード", [result], args.discord, args.discord_events_only)
            elif args.report:
                report = build_daily_report(settings.state_path.parent)
                print(report, flush=True)
                if args.discord:
                    maybe_send_discord(report)
            elif args.health_check:
                report = build_health_report(
                    settings.state_path.parent,
                    settings.health_max_tick_age_seconds,
                    settings.health_min_free_disk_mb,
                )
                print(report.message, flush=True)
                if args.discord and not report.ok:
                    maybe_send_discord(report.message)
            else:
                result = run_once(settings)
                print(result.line, flush=True)
                notify_tick("Polymarket紙トレード", [result], args.discord, args.discord_events_only)
        except Exception as exc:
            print(f"error: {exc}", flush=True)
            if args.discord:
                maybe_send_discord(format_discord_error("紙トレードtick", exc))

        if args.once:
            break
        if deadline and datetime.now(UTC) >= deadline:
            break
        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()
