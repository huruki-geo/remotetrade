# Botter Strategy Research Notes

Research date: **2026-06-01 JST**

This note separates strategies worth testing from promotional claims. A strategy is not ready for live funds merely because it appears here.

## QASH Notes

QASH's public notes emphasize structural edge over directional prediction:

- Commit capital only when execution makes the outcome close to deterministic.
- Treat bridge lag, chain lag, deposit and withdrawal suspension, failed transactions, gas, RPC quality, and cloud cost as real loss paths.
- Start with small capital. Increase only after direct validation.
- Continuously search for new venues and withdraw when flow, volatility, or competing bots remove the edge.
- Inspect successful on-chain wallets and protocol activity instead of relying on generic strategy marketing.
- Prefer major-chain repeatability now that low-TVL EVM chains have fewer users and fewer durable opportunities.
- For liquidation research, use transaction simulation and assume established chains have stronger competing bots.

This framing changes how RemoteTrade should interpret probes: an apparent spread is a lead for operational validation, not profit.

## Hoheto and QASH-Shared Botter Notes

The requested `Hoteto` reference appears to be **Hoheto** (`note.com/hht`). Hoheto's older HFT notes and the articles shared by QASH on **2026-05-13** reinforce the same operating rule: a strategy is only useful if it survives exchange behavior, stale data, adverse selection, regime changes, and fat-tail events.

### Execution reliability is part of the strategy

Hoheto's HFT architecture note separates WebSocket ingestion from heavier book-building and trading logic. The WebSocket process should do minimal work, filter redundant messages, and push updates into a queue. A monitor should detect stale feeds and stop trading when needed.

Hoheto's inventory-management note is even more important for RemoteTrade: exchange-reported positions can lag actual fills, especially during fast markets. A market-making bot can therefore skew quotes in the wrong direction precisely when the loss grows fastest.

Add these implementation requirements before any live market-making canary:

- Maintain a local fill-derived inventory ledger and reconcile it against exchange state.
- Record exchange timestamps, receive timestamps, processing timestamps, and order acknowledgements.
- Stop quoting when feed lag, acknowledgement lag, reconciliation error, or queue backlog exceeds a threshold.
- Treat REST position snapshots as reconciliation inputs, not an unquestioned real-time source of truth.
- Replay stale-feed, duplicate-message, dropped-message, delayed-fill, and partial-fill scenarios.

### Use regime filters to protect maker strategies

Hoheto's trend-market note suggests switching a maker bot to one-sided behavior when short-horizon return, moving-average change, and trade volume indicate a strong trend. His VPIN notes add a useful defensive interpretation: order-flow toxicity indicators may be more valuable as a reason to stop providing liquidity than as a standalone entry signal.

Candidate paper experiments:

- Build volume-time buckets from public trades and calculate buy/sell imbalance percentiles.
- Compare ordinary clock-time features with volume-time features during fast BTC moves.
- Suspend or widen maker quotes when toxicity, short-horizon trend, or feed lag is elevated.
- Evaluate asymmetric quoting: inventory-backed quotes only on the safer side during a detected trend.
- Stress-test consecutive shocks. Percentile-based indicators can under-react after an earlier extreme event changes the reference distribution.

### Search exchange mechanics, not generic indicators

Hoheto's HFT overview distinguishes passive market making, arbitrage, structural strategies, and directional strategies. The useful research habit is to inspect exchange-specific mechanics: fee rounding, maker rebates, circuit breakers, order-book depth far from mid, API behavior, and specification changes.

Hoheto's 2024 order-book note also suggests a capital-allocation idea: idle arbitrage inventory may be reusable for carefully constrained mispricing-catch orders. Do not assume a visible tail order is fillable profit; model circuit breakers, stale books, cancellation behavior, and the scenario where the price continues through the order.

Add a venue-mechanics checklist to each probe:

- Current fee and rebate schedule.
- Minimum size, tick size, rounding, and order-rejection behavior.
- Circuit-breaker and price-band behavior.
- Order-book depth around mid and at large deviations.
- API rate limits, WebSocket lag, maintenance, and specification-change history.
- Whether prefunded inventory can serve more than one strategy without creating conflicting obligations.

### Cross-venue basis and funding remain worth monitoring

The botter articles shared by QASH describe a path from stablecoin lending to delta-neutral BTC positions, then to monitoring cross-exchange price and funding-rate divergence. The author used manual approval before becoming comfortable with more automation and explicitly warns that leveraged cross-venue hedges can split apart.

For RemoteTrade, this supports keeping the existing funding-capture lane, with:

- Manual approval for early entries.
- Per-leg fill simulation and partial-fill handling.
- Venue-failure and withdrawal-suspension scenarios.
- Conservative leverage and collateral fragmentation limits.
- A clear exit rule when funding divergence disappears or reverses.

### Liquidation signals are a filter, not a free edge

Hoheto's 2025 CEX-liquidation retrospective found that dip-buying beyond estimated liquidation clusters could work in ordinary markets and fail badly in a large crash. The strategy's profitable regime and its catastrophic regime are uncomfortably close.

Keep this paper-only:

- Use liquidation intensity or estimated liquidation clusters as an additional feature, not a standalone reason to trade.
- Separate BUY and SELL behavior by market regime.
- Stress-test correlated fills across many altcoins during a crash.
- Cap aggregate exposure below the level that appears comfortable in ordinary backtests.

### Public-preview limitation

QASH shared a paid article titled `【0.001秒で+20%】仮想通貨の過去のエッジ`. Only its public preview was reviewed. The preview says it concerns an intermittent Bybit distortion observed from May 2022 through 2025, with short holding periods and a logic that no longer works unchanged. Do not infer or reproduce the paywalled logic from the preview.

## Japan Operating Constraint

Polymarket lists Japan (`JP`) as a completely restricted location. Do not place orders, provide liquidity, collect maker rebates, or use a VPN or similar tool to bypass the restriction.

Use Polymarket only as a public market-data signal source for strategies executed on venues legally available from Japan.

## Highest-Priority Experiments

### 1. Polymarket-led Coincheck BTC/JPY inventory trading

Use Polymarket BTC Up/Down price changes as a short-horizon public-data signal for Coincheck's zero-fee BTC/JPY order book.

- Continue splitting LONG and inventory-backed SHORT.
- Add realistic Coincheck BTC/JPY book and fill simulation.
- Keep JST-hour breakdowns. Current directional paper logs suggest SHORT is stronger than LONG.
- Avoid naked shorts and leverage during validation.

Keep the existing Polymarket-led bitbank BTC/JPY maker paper lane running in parallel. It remains useful as an execution-quality comparison because it already collects conservative post-only fill simulations and current maker-fee observations.

### 2. Boba Zencha stablecoin canary research

Continue validating the observed Boba Zencha USDC/USDT divergence.

- Treat current output as theoretical until bridge fees, inventory, token redemption, withdrawal availability, failed transactions, and MEV are modeled.
- Prefer prefunded inventory on both sides over transferring assets after a signal.
- Verify that the canonical stablecoins are redeemable and that the target bridge and exchange routes are actually usable before sending funds.
- Add transaction simulation and RPC-health gates before any manually approved canary.
- Run the smallest manually approved canary before considering larger capital.

### 3. Delta-neutral funding capture

Track spot-long/perpetual-short funding capture and cross-venue funding divergence.

- Normalize funding rates to a comparable time basis.
- Model entry and exit fees, basis movement, liquidation buffer, venue eligibility, and collateral fragmentation.
- Prefer slow-moving carry opportunities over latency races.
- Keep this as a separate research lane because derivative venue access and risk differ from domestic spot trading.

## Secondary Experiments

### Reference-exchange market making

- Quote a Japan-accessible thinner venue around a liquid reference venue's fair price.
- Cancel and replace orders when the reference market moves.
- Model inventory skew, taker hedge fallback, queue position, and adverse selection.
- Only pursue venues with zero maker fees, maker rebates, or explicit liquidity rewards.
- Keep GMO Coin in public venue discovery only. The account is not available for this project's execution experiments.

## Excluded From Japan Operation

### Polymarket crypto maker rebates and liquidity rewards

- Do not operate a Polymarket maker bot from Japan.
- Do not place post-only orders or attempt to collect maker rebates or liquidity rewards.
- Public documentation remains useful for understanding how other participants may affect Polymarket prices.

### Prediction-market complete-set and combinatorial arbitrage

- Do not operate a Polymarket execution bot from Japan.
- Public order-book research may still be used to understand signal quality.
- Recent NBA-market research found single-market anomalies rare and short-lived.

### Liquidation bots

- QASH's latest public note discusses transaction simulation work for liquidation bots.
- Keep liquidation bots as research-only until a specific Japan-accessible venue or on-chain protocol is selected.
- Model competing bots, gas bidding, reverted transactions, node latency, and RPC reliability.

## Low Priority

- Same-venue triangular arbitrage: current bitbank probe has found no candidates.
- Ethereum and BSC AMM cycles: current gas- and fee-aware probes remain negative.
- Pure latency races: likely require colocated infrastructure, faster event handling, and more capital than the current VPS setup.
- Generic grid and DCA bots: directional beta and marketing claims make them poor fits for the current market-neutral research goal.

## Sources

- Polymarket changelog: https://docs.polymarket.com/changelog
- Polymarket geographic restrictions: https://help.polymarket.com/en/articles/13364163-geographic-restrictions
- Polymarket fees: https://docs.polymarket.com/trading/fees
- Polymarket maker rebates: https://docs.polymarket.com/market-makers/maker-rebates
- Polymarket liquidity rewards: https://docs.polymarket.com/market-makers/liquidity-rewards
- Polymarket post-only orders and heartbeat: https://docs.polymarket.com/developers/CLOB/orders/onchain-order-info
- Coincheck exchange trading fees: https://coincheck.com/ja/exchange/fee
- OKX smart arbitrage overview: https://www.okx.com/en-us/help/whats-smart-arbitrage-bot-and-how-do-i-use-it
- Polymarket NBA arbitrage study: https://arxiv.org/abs/2605.00864
- Polymarket fill-side microstructure study: https://arxiv.org/abs/2605.11640
- OctoBot reference-exchange market-making implementation notes: https://github.com/Drakkar-Software/OctoBot-market-making
- QASH, August 2023 PnL and beginner-risk note: https://note.com/qash/n/ne0db5c579c54
- QASH, January 2026 low-TVL-chain history and liquidation-bot research note: https://note.com/qash/n/n1aed33af376f
- Hoheto profile and magazine index: https://note.com/hht
- Hoheto, HFT bot architecture example: https://note.com/hht/n/nabc23fa1a210
- Hoheto, market-making inventory-management concerns: https://note.com/hht/n/n868b0c36bfac
- Hoheto, cryptocurrency HFT strategy overview: https://note.com/hht/n/n29542dcec517
- Hoheto, trend filters for maker bots: https://note.com/hht/n/na333099d536f
- Hoheto, VPIN calculation and limitations: https://note.com/hht/n/nc435ab415d4a
- Hoheto, VPIN strategy simulation and defensive use: https://note.com/hht/n/nead1bea037db
- Hoheto, order-book depth check for mispricing-catch bots: https://note.com/hht/n/naa0c998b854d
- Hoheto, CEX liquidation-signal retrospective: https://note.com/hht/n/n18f711732497
- QASH-shared botter profile, part 1: https://note.com/1112345678999_/n/nea2dc4f51b9f
- QASH-shared botter profile, part 2: https://note.com/1112345678999_/n/nfd1c0b811ba7
- QASH-shared paid-edge public preview: https://note.com/1112345678999_/n/nda8c1b399f56
- QASH-shared cautionary beginner note: https://note.com/1112345678999_/n/n979dfcc55b63
- QASH-share follow-up and source tweet embed: https://note.com/1112345678999_/n/n4b1620660670
