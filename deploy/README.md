# Deploy on DigitalOcean Ubuntu

Create a small Ubuntu 24.04 Droplet, SSH in as root, then run:

```bash
git clone https://github.com/huruki-geo/remotetrade.git /opt/remotetrade
cd /opt/remotetrade
bash deploy/install.sh
```

Edit runtime settings:

```bash
nano /opt/remotetrade/.env
```

At minimum, set:

```env
DISCORD_WEBHOOK_URL=...
POLL_SECONDS=15
ARBITRAGE_NOTIONAL_USD=100
```

Useful commands:

```bash
systemctl status remotetrade-limit-paper.service
journalctl -u remotetrade-poly-5m.service -f
journalctl -u remotetrade-poly-rtds.service -f
journalctl -u remotetrade-poly-clob.service -f
journalctl -u remotetrade-poly-replay.service -n 50 --no-pager
journalctl -u remotetrade-venue-discovery.service -n 50 --no-pager
journalctl -u remotetrade-limit-paper.service -f
systemctl list-timers 'remotetrade-*'
systemctl restart remotetrade-limit-paper.service
journalctl -u remotetrade-update.service -n 50 --no-pager
journalctl -u remotetrade-report.service -n 50 --no-pager
```

The VPS runs two always-on paper-trading services. The Polymarket service evaluates the current BTC Up/Down 5m market every `POLL_SECONDS` and can trade each five-minute window when its signal threshold is met:

```bash
python -m remotetrade.app --patterns patterns.json --discord --discord-events-only
```

The cross-exchange service remains available for execution-quality research:

```bash
python -m remotetrade.app --portfolio-paper --discord --discord-events-only
```

The public Polymarket RTDS collector stores Binance and Chainlink crypto price events for replay:

```bash
python -m remotetrade.app --collect-poly-rtds
```

Events are appended to `data/polymarket_crypto_prices.jsonl`.

The public Polymarket CLOB collector follows the current BTC Up/Down 5m market and stores order-book and trade events:

```bash
python -m remotetrade.app --collect-poly-clob
```

Events are appended to `data/polymarket_btc_5m_clob.jsonl`.

The hourly replay report applies the configured validation gate:

```bash
python -m remotetrade.app --poly-replay --discord
```

The default gate requires at least `30` trades, a positive validation-period PnL, and a validation win rate of at least `70%`.

The venue discovery timer checks low-cost GMO Coin, bitbank, and MEXC research markets every five minutes:

```bash
python -m remotetrade.app --discover-venues
```

It stores current fees, minimum order notionals, spreads, and top-of-book depth in `data/venue_market_discoveries.jsonl`. MEXC results are research-only until the API account's actual fees and venue eligibility are confirmed.

The depth arbitrage guard runs every 5 minutes.

The health check runs every 5 minutes and only sends Discord messages when something needs attention.

The daily report is sent at 00:05 UTC, which is 09:05 JST.

Manual report:

```bash
cd /opt/remotetrade
.venv/bin/python -m remotetrade.app --once --report --discord
```

The auto-updater checks GitHub every 30 minutes and runs:

```bash
deploy/update.sh
```

Manual update:

```bash
cd /opt/remotetrade
bash deploy/update.sh
```

Daily data backups are written to:

```text
/opt/remotetrade/backups/
```
