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

## Japan Operating Constraint

Polymarket lists Japan (`JP`) as a completely restricted location. Do not place orders, provide liquidity, collect maker rebates, or use a VPN or similar tool to bypass the restriction.

Use Polymarket only as a public market-data signal source for strategies executed on venues legally available from Japan.

## Highest-Priority Experiments

### 1. Polymarket-led BTC/JPY inventory trading

Use Polymarket BTC Up/Down price changes as a short-horizon signal for a zero-fee BTC/JPY order book.

- Continue splitting LONG and inventory-backed SHORT.
- Add realistic Coincheck BTC/JPY book and fill simulation.
- Keep JST-hour breakdowns. Current directional paper logs suggest SHORT is stronger than LONG.
- Avoid naked shorts and leverage during validation.

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
- OKX smart arbitrage overview: https://www.okx.com/en-us/help/whats-smart-arbitrage-bot-and-how-do-i-use-it
- Polymarket NBA arbitrage study: https://arxiv.org/abs/2605.00864
- Polymarket fill-side microstructure study: https://arxiv.org/abs/2605.11640
- OctoBot reference-exchange market-making implementation notes: https://github.com/Drakkar-Software/OctoBot-market-making
- QASH, August 2023 PnL and beginner-risk note: https://note.com/qash/n/ne0db5c579c54
- QASH, January 2026 low-TVL-chain history and liquidation-bot research note: https://note.com/qash/n/n1aed33af376f
