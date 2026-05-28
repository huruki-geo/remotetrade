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
```

The main always-on service runs:

```bash
python -m remotetrade.app --limit-paper --discord --discord-events-only
```

The depth arbitrage guard runs every 5 minutes.

Daily data backups are written to:

```text
/opt/remotetrade/backups/
```
