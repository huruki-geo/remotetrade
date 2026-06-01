# Polymarket Signal Live-Canary Checklist

Review date: **2026-06-15 JST**

Do not enable automatic live trading merely because the review date has arrived.
Use the review to decide whether a small, manually authorized live canary is justified.

Polymarket lists Japan (`JP`) as a completely restricted location. Do not place Polymarket orders or bypass the restriction. Polymarket is a public market-data signal source only. Any approved live canary must execute on a venue legally available from Japan.

## Lane Overview

- Primary: Polymarket-public-signal Coincheck BTC/JPY post-only paper lane. Collection active.
- Parallel: Polymarket-public-signal bitbank BTC/JPY maker paper lane. Collection active.
- Research: arbitrage candidate probes. Keep paper-only until each route passes fee, depth, latency, inventory, and venue-eligibility checks.

## Shared Requirements

- Keep each venue lane paper-only until the review.
- Evaluate LONG and inventory-backed SHORT separately.
- Report fill rate, closed trades, win rate, average net PnL in bps, total net PnL in bps, maximum drawdown, and maximum losing streak.
- Break results down by JST entry hour. Require at least 30 closed trades before trusting a specific hourly filter.
- Include weekdays and weekends. Prefer at least 14 calendar days of observations.
- Reject stale books, API errors, disconnected streams, and unavailable venue states.
- Do not use leverage or naked shorts.
- Require explicit manual approval before any live order is enabled.

## Polymarket-Led Coincheck BTC/JPY Lane

Status: **paper collection active**

Coincheck is the preferred execution venue for the next Polymarket-public-signal paper lane because BTC/JPY exchange trading currently has zero maker and taker fees, and the exchange API supports `post_only`.

Fee source: https://coincheck.com/ja/exchange/fee

Before a live canary:

- Continue the Coincheck BTC/JPY order-book paper lane using public WebSocket data.
- Simulate realistic fills from the observed book and trades, not Coinbase ticker prices.
- Collect at least 300 closed paper trades.
- Require average net PnL of at least `+1.0 bps` per closed trade after spread and fill assumptions.
- Require results not to depend on a single JST hour for more than half of total profit.
- Run SHORT only as inventory-backed sell-then-buy-back trading.
- Start any approved live canary near the venue minimum order size and stop after 50 closed canary trades for review.

Data files:

- `data/coincheck_poly_maker_events.csv`
- `data/coincheck_poly_maker_scalp_fast_state.json`
- `data/coincheck_poly_maker_balanced_state.json`
- `data/coincheck_poly_maker_strong_only_state.json`

Report command:

```bash
python -m remotetrade.app --coincheck-poly-maker-report --hourly
```

## bitbank BTC/JPY Maker Lane

Status: **paper collection active**

Data files:

- `data/bitbank_poly_maker_events.csv`
- `data/bitbank_poly_maker_state.json`

Before a live canary:

- Collect at least 300 closed paper trades and at least 14 calendar days.
- Keep the conservative post-only fill model.
- Require average net PnL of at least `+1.0 bps` per closed trade.
- Require a stable fill rate and review unfilled, canceled, and requoted orders.
- Re-check the current BTC/JPY maker fee from the bitbank public API on the review date.
- If approved, start near the minimum order size and stop after 50 closed canary trades for review.

## Existing Polymarket Directional Patterns

The current Coinbase-ticker paper patterns are hypothesis generators, not live-trading evidence.
Their configured round-trip cost assumption is deliberately conservative.

On the review date:

- Compare `scalp_fast`, `balanced`, and `strong_only`.
- Prioritize `strong_only`, SHORT results, and JST-hour breakdowns.
- Treat apparent hourly effects as unproven until the relevant lane has enough realistic fill samples.
- Use `python -m remotetrade.polymarket_trade_analysis --hourly ...` for the JST-hour report.
