# Botter Research Notes

This repo should prefer small, testable edges over broad prediction.

## References

- Hoheto, "暗号通貨市場におけるHFTまとめ"
  - Market-making bots should not just spray passive quotes. They need short-term price prediction from order book and trade-flow signals so quotes are placed at better prices.
  - Directional strategies exist, but they are a different game from liquidity provision.
  - Momentum ignition / manipulation-like behavior is out of scope.
- Hoheto, "専業botterのリアル"
  - Crypto bot revenue changes heavily with market regime. Multiple revenue sources and survival matter more than one perfect strategy.
- 日本爆損防止委員会, "MLbotで爆損するなかれ"
  - Easy API data plus generic ML plus market orders is not an edge.
  - Financial time series are noisy, non-stationary, and easy to overfit.
- あいば, "初心者botter向け バックテストとは？"
  - Backtesting is mandatory before running a guessed rule.
  - OHLCV backtests are enough for slower rules, but high-frequency rules need trade/order-book style data.

## Implications for remotetrade

1. Prioritize execution quality.
   - Prefer post-only limit quotes over market orders.
   - Track whether both legs would fill, one leg would fill, or neither leg would fill.
   - Penalize stale quotes and partial fills before counting paper profit.

2. Add microstructure filters before entry.
   - Order book imbalance.
   - Last-trade aggressor direction.
   - Spread width and depth at the target size.
   - Quote age / data freshness.

3. Treat ML as optional analysis, not the first trading signal.
   - Do not add generic ML until we have reliable labels, out-of-sample tests, and execution-cost modeling.

4. Build a replay backtester.
   - Current live paper ticks are useful, but too sparse.
   - For wick/spread/limit-arb, store enough quote snapshots to replay candidate rules.

5. Use strategy gating.
   - A signal is not enough.
   - A trade is allowed only if a profit guard says fees, spread, depth, latency, and inventory constraints are acceptable.

## Next Implementation Priority

1. Add order book clients for the exchanges. [done]
2. Add a `profit_guard` module that computes effective bid/ask for target notional. [done]
3. Add a limit-order fill simulator. [initial version done]
   - maker fill probability proxy
   - partial-fill handling
   - hedge path for single-leg fills
4. Add inventory checks. [initial version done]
5. Add live paper fill tracking for post-only limit pairs. [done]
6. Add replay reports from saved tick CSVs.
