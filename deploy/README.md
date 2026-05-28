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
journalctl -u remotetrade-limit-paper.service -f
systemctl list-timers 'remotetrade-*'
systemctl restart remotetrade-limit-paper.service
journalctl -u remotetrade-update.service -n 50 --no-pager
journalctl -u remotetrade-report.service -n 50 --no-pager
```

The main always-on service runs portfolio paper trading:

```bash
python -m remotetrade.app --portfolio-paper --discord --discord-events-only
```

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
