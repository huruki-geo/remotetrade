# Botter Strategy Research Notes

Research date: **2026-06-01 JST**

This note separates strategies worth testing from promotional claims. A strategy is not ready for live funds merely because it appears here.

## Highest-Priority Experiments

### 1. Polymarket-led BTC/JPY inventory trading

Use Polymarket BTC Up/Down price changes as a short-horizon signal for a zero-fee BTC/JPY order book.

- Continue splitting LONG and inventory-backed SHORT.
- Add realistic Coincheck BTC/JPY book and fill simulation.
- Keep JST-hour breakdowns. Current directional paper logs suggest SHORT is stronger than LONG.
- Avoid naked shorts and leverage during validation.

### 2. Polymarket crypto maker rebates

Quote Polymarket crypto markets with post-only orders around an external fair price derived from Binance, Chainlink, and local CLOB state.

- Polymarket launched taker fees and maker rebates for 5-minute crypto markets on 2026-02-12.
- Crypto maker orders have zero maker fee and may receive daily USDC rebates funded by taker fees.
- Score expected spread capture, adverse selection, inventory, and rebate income separately.
- Use heartbeat-driven cancel-on-disconnect, post-only orders, and stale-feed rejection.
- Skew or stop quoting when Polymarket-led BTC/JPY signals indicate elevated directional risk.

### 3. Boba Zencha stablecoin canary research

Continue validating the observed Boba Zencha USDC/USDT divergence.

- Treat current output as theoretical until bridge fees, inventory, token redemption, withdrawal availability, failed transactions, and MEV are modeled.
- Prefer prefunded inventory on both sides over transferring assets after a signal.
- Run the smallest manually approved canary before considering larger capital.

### 4. Delta-neutral funding capture

Track spot-long/perpetual-short funding capture and cross-venue funding divergence.

- Normalize funding rates to a comparable time basis.
- Model entry and exit fees, basis movement, liquidation buffer, venue eligibility, and collateral fragmentation.
- Prefer slow-moving carry opportunities over latency races.
- Keep this as a separate research lane because derivative venue access and risk differ from domestic spot trading.

## Secondary Experiments

### Prediction-market complete-set and combinatorial arbitrage

- Scan for executable YES/NO or multi-market bundles priced below guaranteed settlement value after fees.
- Require simultaneous execution or explicitly model incomplete-leg risk.
- Recent NBA-market research found single-market anomalies rare and short-lived, so this is a scanner task rather than a core thesis.

### Reference-exchange market making

- Quote a thinner venue around a liquid reference venue's fair price.
- Cancel and replace orders when the reference market moves.
- Model inventory skew, taker hedge fallback, queue position, and adverse selection.
- Only pursue venues with zero maker fees, maker rebates, or explicit liquidity rewards.

### Polymarket liquidity rewards

- Scan market metadata for reward allocations, minimum incentive sizes, and maximum incentive spreads.
- Score expected reward income separately from trading PnL.
- Avoid assuming reward farming is profitable without competitive-share estimates.

## Low Priority

- Same-venue triangular arbitrage: current bitbank probe has found no candidates.
- Ethereum and BSC AMM cycles: current gas- and fee-aware probes remain negative.
- Pure latency races: likely require colocated infrastructure, faster event handling, and more capital than the current VPS setup.
- Generic grid and DCA bots: directional beta and marketing claims make them poor fits for the current market-neutral research goal.

## Sources

- Polymarket changelog: https://docs.polymarket.com/changelog
- Polymarket fees: https://docs.polymarket.com/trading/fees
- Polymarket maker rebates: https://docs.polymarket.com/market-makers/maker-rebates
- Polymarket liquidity rewards: https://docs.polymarket.com/market-makers/liquidity-rewards
- Polymarket post-only orders and heartbeat: https://docs.polymarket.com/developers/CLOB/orders/onchain-order-info
- OKX smart arbitrage overview: https://www.okx.com/en-us/help/whats-smart-arbitrage-bot-and-how-do-i-use-it
- Polymarket NBA arbitrage study: https://arxiv.org/abs/2605.00864
- Polymarket fill-side microstructure study: https://arxiv.org/abs/2605.11640
- OctoBot reference-exchange market-making implementation notes: https://github.com/Drakkar-Software/OctoBot-market-making

