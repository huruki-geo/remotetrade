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

## Working Takeaways

- Do not try to win by broad prediction first. Survive by making execution quality measurable.
- Paper profit is not trusted unless it accounts for both-leg fills, one-leg fills, expirations, hedge cost, stale quotes, and fees.
- Limit/arbitrage style rules need order-book replay, not only OHLCV backtests.
- A bot should adapt conservatively: tighten when one-leg fills rise, only get more aggressive when fills are stable or orders expire without adverse fills.
- ML remains a later analysis layer. Add it only after labels, replay tests, execution-cost modeling, and out-of-sample checks exist.

## Current Direction

- Keep `profit_guard`, limit fill simulation, hedge-slippage filtering, and adaptive limit tuning as the core safety layer.
- Next useful build: replay reports from saved `orderbook_snapshots*.jsonl` so variants can be compared under the same market sequence.
- After replay exists, add entry gates for order-book imbalance, spread width, quote age, and last-trade aggressor direction.

## Hourly BTC Reversal Anomaly

Reference: Hoheto, "Bitcoin price time anomaly" (2020-09-14):
https://note.com/hht/n/nc0caf98477db

- The article reports a short-term reversal after the move around the start of each hour, especially entries around minute 1 through minute 5.
- The tested rule compares the previous five-minute move, trades in the opposite direction, and exits after roughly 20 to 30 minutes.
- The source uses 2019-07-01 through 2020-06-30 data and explicitly warns that spread and fees were not deducted from the headline result.
- The author also states that the simple strategy alone is not enough for a bot because frequent entries are costly and the profit ratio is limited.
- Treat this as a candidate feature for replay analysis, not as evidence of a risk-free standalone strategy.

Useful replay features:

- UTC minute and hour.
- Return over the previous 1, 3, and 5 minutes.
- Return after 5, 10, 20, and 30 minutes.
- Spread, depth, imbalance, and estimated round-trip fees at signal time.
- Maker-only fill outcome versus taker fallback outcome.
- Separate out-of-sample results by month and venue.

## High-Frequency Direction

The current always-on VPS process is a low-frequency REST polling paper trader. It polls every `POLL_SECONDS`, fetches three venue books sequentially, and only places a simulated limit pair when a cross-venue candidate passes the profit guard. It is not an HFT engine yet.

Before live high-frequency execution:

1. Collect WebSocket order-book deltas and trades with exchange timestamps.
2. Build deterministic replay from recorded market events.
3. Measure quote age, queue position proxies, partial fills, one-leg exposure, cancel latency, and emergency hedge cost.
4. Compare maker strategies under fees and adverse selection.
5. Keep the hourly anomaly as one optional feature in the replay report.
6. Only add authenticated order placement after the paper and replay results survive out-of-sample checks.

There is no risk-free version of cross-exchange market making. The main risks are one-leg fills, stale quotes, adverse selection, exchange outages, inventory drift, fee changes, and latency.

## Polymarket BTC 5m External Signal Research

Recommended signal source: public Polymarket `BTC Up or Down 5m` data. Do not place Polymarket orders. Test whether its public probability, order-book, and trade-flow changes lead executable price moves on legally eligible external venues.

- Each market resolves `Up` when the Chainlink BTC/USD price at the end of its five-minute window is greater than or equal to the opening reference price. Otherwise it resolves `Down`.
- The resolution source is Chainlink BTC/USD, not Coinbase spot. Coinbase can remain a secondary feature, but the next collector should subscribe to Polymarket RTDS Chainlink updates.
- Polymarket exposes a public CLOB WebSocket market channel for `book`, `price_change`, `last_trade_price`, and optional `best_bid_ask` events.
- Polymarket RTDS exposes live Binance and Chainlink crypto price updates without authentication.
- Current Polymarket crypto markets have zero maker fees, taker-only dynamic fees, and daily maker rebates funded from a share of taker fees.

Initial research rule:

- Evaluate every active five-minute window.
- Do not force a trade in every window. A skipped low-quality window is a valid outcome.
- Continue paper trading the existing `scalp_fast`, `balanced`, and `strong_only` external-venue proxy variants on the VPS.
- Record the Polymarket odds move and Coinbase proxy now.
- Add Chainlink distance-to-reference-price, time remaining, CLOB spread, imbalance, trade flow, and quote age before external authenticated trading.
- Label Polymarket feature rows with future executable BTC returns on the target external venue at 1, 3, 5, 15, 30, and 60 seconds.
- Prefer external-venue post-only maker orders after replay testing. Use taker execution only when its expected edge exceeds fees and slippage.

VPS service:

```bash
python -m remotetrade.app --patterns patterns.json --discord --discord-events-only
```

This is an external-venue directional signal research lane, separate from the cross-exchange paired-order research lane.

## Complex Arbitrage Research

Reference: QASH_NFT, "May profit and how I turned 5,000 yen into 100 million yen with reproducible arbitrage" (2022-05-31):
https://note.com/qash/n/nf71c08f2a479

Keep the existing wick, spread, and cross-exchange arbitrage lanes. They are useful collectors and may still find profitable events. Do not treat the Polymarket BTC 5m lane as a replacement for them.

The article explains why simple major-exchange spread scanning is rarely enough:

- Obvious cross-exchange spreads are crowded and often disappear below a retail trader's all-in cost.
- Exchange fees, hedge cost, and execution drift must be included before calling a spread profitable.
- More interesting edges can exist inside one exchange across multiple quoted pairs, for example `JPY -> BTC -> XRP -> JPY`.
- Slow-to-close spreads can come from operational constraints such as deposit or withdrawal suspension and low hot-wallet balances.
- Very short-lived wick opportunities may only be visible in trade history, not in periodic best-bid / best-ask snapshots.
- DEX routes can make a trade atomic by reverting when final balance is not profitable, but gas cost, contract risk, MEV, bridge risk, and honeypots remain.

Recommended implementation order:

1. Preserve the current wick, spread, and depth-adjusted cross-exchange collectors.
2. Add a graph-based triangular and multi-hop arbitrage scanner for one venue at a time.
3. Record trade streams, not only order-book snapshots, so fleeting wick fills can be replayed.
4. Add venue metadata: fees, minimum sizes, deposit and withdrawal status, wallet constraints, and stale-data checks.
5. Add DEX route simulation separately. Only consider execution after contract allowlists, token allowlists, gas accounting, and atomic profit guards exist.

Avoid strategies that depend on manipulating liquidity, intentionally increasing gas prices, exploiting other users' collateral through oracle delay, or trading unreviewed tokens.

## Evidence-Based Edge Assessment

The project should target event-driven, medium-frequency execution on a VPS, not a pure latency race.

Evidence:

- Xu, Gould, and Howison, "Multi-Level Order-Flow Imbalance in a Limit Order Book" (2019): deeper order-book flow levels improve out-of-sample fit for contemporaneous mid-price changes.
- Cont, Cucuringu, and Zhang, "Cross-Impact of Order Flow Imbalance in Equity Markets" (2021): integrated multi-level OFI explains price impact better than best-level OFI, and lagged cross-asset OFI improves short-horizon forecasts.
- Kolm, Turiel, and Westray, "Deep Order Flow Imbalance" (2021): stationary order-flow inputs outperform raw order-book states for high-frequency return prediction in their data.
- "Wish or reality? On the exploitability of triangular arbitrage in cryptocurrency markets" (Finance Research Letters, 2025): Binance triangular opportunities exist, but fees, slippage, and limited order-book volume eliminate profitability in the tested strategy.

Implications:

- Do not make simple major-exchange triangular arbitrage the primary expected-profit strategy. Keep the scanner as a discovery and measurement tool.
- Collect event streams before adding complicated prediction models. Snapshot-only REST polling misses queue changes, fleeting wicks, and cancellations.
- Start with interpretable features: multi-level OFI, trade aggressor imbalance, spread, depth, quote age, short-window return, volatility, and time remaining.
- Use conditional entry filters. A strategy that skips most windows can be healthier than one that forces high trade count.
- Evaluate edge after fees, slippage, missed fills, partial fills, latency, and adverse selection.

## VPS Reality Check

Current state:

- The VPS loop is still REST polling every `POLL_SECONDS`, not high-frequency execution.
- It can run paper lanes for wick reversal, spread, cross-exchange arbitrage, depth-adjusted arbitrage, limit-fill simulation, and Polymarket BTC 5m directional evaluation.
- The code does not yet collect exchange trade streams or incremental order-book updates.
- It does not place authenticated live orders.

Realistic VPS target:

- WebSocket collection with exchange timestamps.
- Event-driven feature updates and decisions on a sub-second to several-second horizon.
- Small, selective trades where the measured expected edge exceeds all modeled costs.
- Multiple independent lanes: wick replay, constraint-driven arbitrage discovery, Polymarket public-data research, and order-flow filters.

Not a realistic first target:

- Winning a pure millisecond race on major Binance triangular paths.
- Continuously quoting tight spreads against colocated professional market makers.
- Assuming maker rebates alone compensate for adverse selection.

## Polymarket Compliance Boundary

Polymarket documents geographic restrictions for order placement. The public documentation lists the United States as blocked and Japan as frontend-UI restricted. Before any authenticated integration, call:

```text
GET https://polymarket.com/api/geoblock
```

Use Polymarket only as a public-data source for research. Do not place Polymarket orders or use VPS location changes to bypass restrictions.

## Validation Plan

Phase 1: observe before optimizing.

1. Collect WebSocket trades and incremental books from selected liquid venues.
2. Store raw events with exchange timestamp, receive timestamp, sequence identifiers, and reconnect gaps.
3. Build replay labels at 1, 3, 5, 15, 30, and 60 seconds.
4. Measure baseline conditional outcomes for wick, OFI, trade imbalance, spread widening, and route-arbitrage signals.

Phase 2: require evidence.

1. Split replay chronologically into development and untouched out-of-sample periods.
2. Require positive expected value after conservative fees, latency, and slippage.
3. Track trade count, hit rate, average edge, worst loss, drawdown, fill rate, and adverse move after fill.
4. Reject strategies whose profit comes from a few unrepeatable events unless they are explicitly treated as event strategies.

Phase 3: only then consider small live execution on legally eligible venues.

## C-Class Botter Operating Notes

Reference: QASH_NFT, "Let's become a C-class botter earning 10,000 yen per month with crypto" (2023-12-02):
https://note.com/qash/n/n11f79a69daad

Useful operating principles from the article:

- Run always-on bots in cloud infrastructure when continuous observation matters.
- Start with detection bots and manual or very small execution while finding operational errors.
- Validate exchange-specific contract size, lot size, and API values before allowing an order.
- Reject implausible zero or out-of-range prices instead of trusting every API response.
- Use Discord-style alerts for errors and detected opportunities.
- Build many small experiments because edges can disappear quickly.

Applied here:

- Keep the existing wick, spread, depth-arbitrage, route-arbitrage, and Polymarket lanes independent.
- Store raw public WebSocket data before optimizing a model.
- Run hourly replay reports for the Polymarket BTC 5m collector.
- Treat win rate as a reference metric, not a hard gate. Require a minimum sample size and positive validation-period PnL so asymmetric payoff strategies are not rejected solely for winning less often.
- Keep authenticated execution out of scope until paper validation, venue eligibility, value sanity checks, and small-size operational testing exist.

## Low-Cost Venue Discovery

The VPS should discover small-maker candidates continuously instead of relying on a static exchange list.

Initial supported discovery venues: GMO Coin and bitbank spot markets, plus MEXC public-market research.

- GMO Coin publishes unauthenticated symbol rules, tickers, order books, and trades.
- Its symbol rules include current minimum order size, price tick, maker fee, and taker fee.
- Current GMO Coin spot fees are maker `-0.01%` and taker `0.05%` for BTC, ETH, XRP, and DAI. Other spot symbols are maker `-0.03%` and taker `0.09%`.
- GMO Coin supports public and private WebSocket APIs. Its documented Tier 1 private API limit is `20req/s` for GET and `20req/s` for POST.
- bitbank documents PostOnly orders and publishes current pair fees, minimum amounts, status, tickers, and books through public APIs. Many pairs currently use a maker rebate of `-0.02%`.
- MEXC publishes spot symbols, public commission fields, and all best bid / ask tickers through public REST APIs. Store these rows as `mexc_research`: MEXC's published zero-fee promotions can exclude API users, so account-specific API fees must be verified before any order placement.

The initial VPS collector runs every five minutes and stores:

- Live spread in basis points.
- Current maker and taker fees from the venue API.
- Maker and taker round-trip edge estimates.
- Minimum order notional in the venue quote asset.
- Top-level bid and ask depth.
- Eligibility for a configured small-order budget, minimum depth, and maximum-spread sanity gate.

This is a discovery feed, not a live-order permission.

## Next Implementation Priority

1. Add order book clients for the exchanges. [done]
2. Add a `profit_guard` module that computes effective bid/ask for target notional. [done]
3. Add a limit-order fill simulator. [initial version done]
   - maker fill probability proxy
   - partial-fill handling
   - hedge path for single-leg fills
4. Add inventory checks. [initial version done]
5. Add live paper fill tracking for post-only limit pairs. [done]
6. Add replay reports from saved tick CSVs and `orderbook_snapshots*.jsonl`.
7. Keep the Polymarket BTC 5m directional paper service running on the VPS. [done]
8. Add Polymarket RTDS collection for Chainlink BTC/USD and Binance BTC/USDT.
   - Public WebSocket collector and VPS service added. [done]
9. Add Polymarket CLOB WebSocket collection for BTC 5m order-book and trade events.
   - Public WebSocket collector and VPS service added. [done]
10. Add a same-venue triangular and multi-hop arbitrage scanner.
11. Add trade-stream collection for wick replay.
12. Add microstructure and hourly-anomaly features to replay reports.
13. Add multi-level OFI and trade-aggressor features. [initial version done]
14. Add chronological out-of-sample reports with modeled execution costs.
   - Polymarket BTC 5m replay now gates on the final chronological 30% with configurable per-share costs. [initial version done]
15. Add VPS low-cost venue discovery.
   - GMO Coin, bitbank, and MEXC research-only public symbol, fee, ticker, status, and order-book discovery runs every five minutes. [initial version done]

## Strategy Selection: "Omae mo botter ni naranai ka?"

Reference: Hoheto, "Omae mo botter ni naranai ka? Cryptocurrency bot revenue methods summary" (2021):
https://note.com/hht/n/n61e6ecefd059

The article separates bot revenue sources into high-frequency trading, swing trading, arbitrage, wick capture, interest and futures basis, mirror trading, momentum chasing, trend following, and bitFlyer SFD. The best first target for this repo is not every category at once.

Primary research lane:

- Run selective two-sided PostOnly market-making experiments on low-cost spot venues.
- Prefer markets with a maker rebate, sufficient depth, stable API behavior, and enough trade flow for both sides to fill.
- Quote a small passive buy and passive sell around a reference price.
- Treat spread capture and maker rebates as candidate gross edge only.
- Cancel or skew quotes when short-horizon order-flow features suggest adverse selection.
- Measure both-side fill rate, single-leg fill rate, emergency hedge cost, inventory age, post-fill adverse move, and net PnL after fees.

Why this lane comes first:

- It matches the VPS low-cost venue discovery feed already running every five minutes.
- GMO Coin documents public WebSocket books and trades, private order APIs, and spot maker rebates.
- bitbank documents PostOnly behavior and current maker rebates on supported pairs.
- Small orders make operational mistakes cheaper while the fill simulator and replay reports mature.

Secondary lanes to preserve:

- Wick capture: keep collecting rare mispricing events because it can complement a market-making lane.
- Depth-adjusted and route arbitrage: keep as event-driven discovery lanes, but reject routes after fees, slippage, stale quotes, and limited depth.
- Polymarket BTC 5m: keep as public-data replay research until venue eligibility is confirmed.
- Interest and futures-basis research: consider later because it needs separate capital, venue-risk, and liquidation-risk accounting.

Do not prioritize:

- Pure millisecond latency races on major overseas venues from a general-purpose VPS.
- Mirror trading, social-media chasing, or manipulation-like behavior.
- SFD as the main build target. The article describes a venue-specific historical edge; bitFlyer Lightning FX ended on 2024-03-28 and was replaced by Crypto CFD.
- Authenticated automatic execution before replay evidence, hard position limits, cancel-all handling, and emergency stop controls exist.

The working hypothesis is narrow: a VPS may support event-driven, selective small-maker experiments, but stable prices do not make the strategy risk-free. Single-leg fills and adverse selection remain the core risks.

## QASH Arbitrage Research Backlog

References:

- QASH_NFT, "5月の損益と再現性のあるアビトラで5000円を1億円にした話":
  https://note.com/qash/n/nf71c08f2a479
- QASH, "7/1-7/6の損益とバブル崩壊後の安定戦略":
  https://qash-tit.hatenablog.com/entry/2021/12/21/195509
- QASH, "2021年の年次と、今年どうやって稼いだか":
  https://qash-tit.hatenablog.com/entry/2021/12/30/220812
- QASH, "11/12までの損益と$OMG戦の思考経過":
  https://qash-tit.hatenablog.com/entry/2021/12/21/195649
- QASH_NFT, "2022年の年次と、仮想通貨で今年どうやって稼いだか":
  https://note.com/qash/n/n4bfdc14c507a
- QASH, "6月の損益とOasisNetworkで死にかけた話":
  https://qash-tit.hatenablog.com/entry/2022/06/30/195015

Useful pattern: do not merely scan for a large spread. Explain why competition has not already closed it.

Candidate causes:

1. Same-venue market fragmentation: the same asset trades against multiple quote assets, leaving a profitable conversion route.
2. Slow price propagation: a quiet venue or stale market maker lags a liquid reference venue during a sharp move.
3. Operational constraints: deposit or withdrawal suspension, hot-wallet depletion, borrow scarcity, or changing funding and lending rates prevent normal arbitrageurs from closing a spread.
4. Event structure: snapshots, airdrops, listings, or settlement mechanics temporarily change the fair value of spot, dated futures, perpetuals, or borrow inventory.
5. DEX fragmentation: stale pools and route-dependent pricing can leave atomic routes, but large spreads must be treated as a warning until token identity, redemption, bridge backing, gas, and contract behavior are verified.

Implementation order for this repository:

1. Connect the existing `route_arbitrage` graph search to bitbank public JPY and BTC pairs.
   - Start with `JPY -> BTC -> asset -> JPY` and the reverse direction.
   - Apply current taker fees, minimum order sizes, top-of-book depth, stale-data rejection, and conservative slippage.
   - Keep it same-venue and paper-only first: no transfer risk and no authenticated API needed.
2. Add cross-venue divergence persistence tracking.
   - Record spread onset, peak spread, duration, estimated executable notional, and time to convergence.
   - Do not alert on a spread alone; alert when a spread survives costs and has an explainable operational constraint.
3. Add a reference-price wick probe.
   - Quote small post-only orders on a domestic venue around a liquid overseas reference price.
   - On a simulated fill, measure immediate hedge cost, single-leg rate, and post-fill markout.
   - This is distinct from passively quoting the domestic bid and ask.
4. Add venue-constraint metadata.
   - Deposit and withdrawal status, hot-wallet observations where public, borrow availability, lending rates, funding rates, and event calendars.
5. Keep DEX route simulation separate and disabled for execution.
   - Require token contract allowlists, canonical-asset checks, bridge-backing checks, atomic profit guards, gas accounting, and tiny test transactions before considering live use.

Reject or quarantine an apparent edge when:

- The asset contract differs across venues or chains.
- A wrapped stablecoin is not canonically issued or redeemable.
- Withdrawals, deposits, bridges, or borrow inventory are unavailable.
- The route profit disappears after fees, depth walking, FX hedge costs, funding, borrow interest, or failed-transaction costs.
- The edge exists only because the quote is stale or the venue is operationally unreliable.

The next low-risk build target is same-venue bitbank triangular route monitoring. It matches the existing graph search, uses public data, and tests the article's highest-signal idea without introducing transfer or bridge risk.

## BOBA CEX-DEX Stablecoin Probe

The January 31, 2026 QASH note says an older Curve fork used on BOBA still has a spread. The public article does not name the fork or pool contract. Public project material identifies Zencha Finance as BOBA's first StableSwap using the StableSwap invariant for `DAI / USDC / USDT`, but this is only a candidate until its live contracts are identified.

As an immediately verifiable BOBA CEX-DEX baseline, monitor the canonical OolongSwap `USDT / USDC` pool against Coinbase `USDT-USD`:

- Verify the pool tokens against BOBA's official L2 token list on every scan.
- Model constant-product price impact at the configured small size.
- Treat the Oolong stable-pair fee as a configurable assumption. Public Oolong material says stable-pair fees may be lower than the default dynamic fee.
- Record both directions and retain the better route.
- Alert only as a research candidate. Bridge latency, bridge fee, CEX inventory, deposit and withdrawal status, and operational reliability remain unmodeled.

Initial May 31, 2026 observations showed a real but tiny-capacity divergence:

- `$1`: approximately `+1.76%`
- `$5`: approximately `+1.35%`
- `$10`: approximately `+0.81%`
- `$20`: approximately `-0.24%`

The pool is shallow enough that price impact consumes the edge quickly. This is closer to the article's point than scanning deep mainnet pools: the reason the spread survives is also the reason it is difficult to monetize at size.

## BOBA Zencha StableSwap Probe

The tiny Oolong pool is a useful baseline, but it is not the only BOBA candidate. The QASH article refers to an older Curve fork without naming it. Zencha Finance is a strong public candidate, not a confirmed identification: its archived material describes a BOBA StableSwap for `DAI / USDC / USDT`, and DeFiLlama's adapter points to live `SwapFlashLoan` contract `0x2D027B49B8960810F84D5fE172d07FFf62311852`.

Verify the contract directly before treating it as a candidate:

- Require BOBA chain ID `288`.
- Read all three token indexes from the Saddle-compatible contract on every scan.
- Quote Coinbase-anchored `USDC <-> USDT` directions with on-chain `calculateSwap`; retain the DAI balance for later venue-specific expansion.
- Compare the output to Coinbase stablecoin USD bids and subtract an estimated BOBA transaction cost.
- Record the full size curve and alert only on a paper candidate.

Initial May 31, 2026 direct RPC observations:

- DeFiLlama reported approximately `$85.9k` protocol TVL.
- Contract balances were approximately `DAI 59.2k / USDC 8.8k / USDT 16.6k`.
- `USDC -> USDT` pool-only quotes were approximately `+1.84%` at `$1`, `+1.53%` at `$1,000`, and `+0.57%` at `$5,000`.

The frontend is no longer available and DeFiLlama marks the protocol unaudited. This remains a paper-only observation. Token redemption, bridge status, bridge fees, CEX inventory, and withdrawal availability must be checked separately before any test transaction.

The five-minute timer records every quote, but repeated observations of an untouched spread are not repeated profits. Use `python -m remotetrade.app --boba-zencha-report` to count independent episodes. A new episode requires a candidate to disappear and return, or a gap of more than ten minutes. Discord alerts fire on candidate appearance or reappearance rather than every timer tick.

### Zencha Live Canary

Live execution is deliberately separate from the paper timer. Create a dedicated wallet, fund only the canary amount and gas, then preflight:

```bash
python -m remotetrade.zencha_live --create-wallet
python -m remotetrade.zencha_live --preflight --amount-usdc 10
```

The dedicated CLI refuses amounts above `$10 USDC`, reads the private key only from `secrets/zencha_wallet.key`, requires restrictive file permissions on Linux, checks BOBA chain ID `288`, verifies balances, calculates the live quote, applies a slippage floor, and waits for successful approval and swap receipts. Execution remains manual:

```bash
python -m remotetrade.zencha_live --execute --amount-usdc 10 --confirm EXECUTE_ZENCHA_CANARY
```

Do not fund the canary wallet until its address has been backed up and the BOBA token contracts, bridge route, and recovery plan have been checked independently.

## BOBA Synapse StableSwap Probe

Synapse's BOBA pool is a second observable BOBA StableSwap candidate. Its legacy `nUSD` token is severely divergent and must remain quarantined. Monitor only the BOBA allowlisted `USDC <-> USDT` directions and record the legacy balances for context.

Initial May 31, 2026 direct RPC observations:

- Pool balances were approximately `nUSD 1.12 / DAI 702 / USDC 581 / USDT 644`.
- `USDC -> USDT` returned approximately `+1.83%` after the Coinbase `USDT-USD` bid and estimated BOBA gas at `$1`.
- Price impact consumed the edge quickly: the observed maximum was approximately `+$0.25` around `$20`.

This pool is useful as another BOBA replenishment signal, not as a standalone target for new bridge costs. Never treat apparent `nUSD` routes as USD arbitrage without independently proving redemption.
