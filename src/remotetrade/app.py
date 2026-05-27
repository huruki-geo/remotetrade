from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from remotetrade.clients import CoinbaseClient, PolymarketClient
from remotetrade.config import Settings
from remotetrade.notify import send_discord_message
from remotetrade.paper import PaperBroker
from remotetrade.patterns import Pattern, load_patterns
from remotetrade.stock_app import run_stock_patterns_once
from remotetrade.strategy import PolymarketLeadStrategy


@dataclass(frozen=True)
class TickResult:
    pattern_id: str
    line: str
    outcome: str


def run_once(
    settings: Settings,
    polymarket: PolymarketClient | None = None,
    coinbase: CoinbaseClient | None = None,
    pattern: Pattern | None = None,
) -> TickResult:
    polymarket = polymarket or PolymarketClient(settings.gamma_url)
    coinbase = coinbase or CoinbaseClient(settings.coinbase_url)
    broker = PaperBroker(settings.state_path, settings.trades_path, settings.start_cash_usd)
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
    return TickResult(pattern.id if pattern else "default", line, outcome)


def run_patterns_once(settings: Settings, patterns_path: Path) -> list[TickResult]:
    patterns = load_patterns(patterns_path)
    polymarket = PolymarketClient(settings.gamma_url)
    coinbase = CoinbaseClient(settings.coinbase_url)
    return [run_once(pattern.apply(settings), polymarket, coinbase, pattern) for pattern in patterns]


def has_trade_event(results: list[TickResult]) -> bool:
    return any(result.outcome in {"opened", "closed", "skip_size_too_small"} for result in results)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Polymarket-led crypto paper trading.")
    parser.add_argument("--once", action="store_true", help="Evaluate one tick and exit.")
    parser.add_argument("--patterns", type=Path, help="Run multiple paper-trading patterns from a JSON file.")
    parser.add_argument("--stock-patterns", type=Path, help="Run stock paper-trading patterns from a JSON file.")
    parser.add_argument("--discord", action="store_true", help="Send tick results to DISCORD_WEBHOOK_URL.")
    parser.add_argument("--discord-events-only", action="store_true", help="Notify Discord only when a trade event occurs.")
    parser.add_argument("--duration-seconds", type=int, help="Run for this many seconds, then exit.")
    args = parser.parse_args()

    settings = Settings.from_env()
    deadline = datetime.now(UTC) + timedelta(seconds=args.duration_seconds) if args.duration_seconds else None
    while True:
        try:
            if args.patterns:
                results = run_patterns_once(settings, args.patterns)
                message = "Polymarket paper tick\n" + "\n".join(result.line for result in results)
                print(message, flush=True)
                if args.discord and (not args.discord_events_only or has_trade_event(results)):
                    send_discord_message(message)
            elif args.stock_patterns:
                results = run_stock_patterns_once(settings, args.stock_patterns)
                message = "Stock event paper tick\n" + "\n".join(result.line for result in results)
                print(message, flush=True)
                if args.discord and (not args.discord_events_only or has_trade_event(results)):
                    send_discord_message(message)
            else:
                result = run_once(settings)
                print(result.line, flush=True)
                if args.discord and (not args.discord_events_only or has_trade_event([result])):
                    send_discord_message("Polymarket paper tick\n" + result.line)
        except Exception as exc:
            print(f"error: {exc}", flush=True)
            if args.discord:
                send_discord_message(f"Polymarket paper tick error\n{exc}")

        if args.once:
            break
        if deadline and datetime.now(UTC) >= deadline:
            break
        time.sleep(settings.poll_seconds)


if __name__ == "__main__":
    main()
