#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/remotetrade}"
REPO_URL="${REPO_URL:-https://github.com/huruki-geo/remotetrade.git}"
SERVICE_USER="${SERVICE_USER:-remotetrade}"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run as root: sudo bash deploy/install.sh"
  exit 1
fi

apt-get update
apt-get install -y git python3 python3-venv python3-pip

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  useradd --system --create-home --shell /usr/sbin/nologin "$SERVICE_USER"
fi

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
else
  git -C "$APP_DIR" pull --ff-only
fi

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -e "$APP_DIR"

mkdir -p "$APP_DIR/data" "$APP_DIR/backups"
if [ ! -f "$APP_DIR/.env" ]; then
  cp "$APP_DIR/.env.example" "$APP_DIR/.env"
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-limit-paper.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-poly-5m.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-poly-rtds.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-poly-clob.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-poly-replay.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-poly-replay.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-venue-discovery.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-venue-discovery.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-bitbank-route-probe.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-bitbank-route-probe.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-dex-route-probe.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-dex-route-probe.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-maker-probe.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-depth-arb.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-depth-arb.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-backup.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-backup.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-health.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-health.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-report.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-report.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-update.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-update.timer" /etc/systemd/system/
chmod +x "$APP_DIR/deploy/backup-data.sh"
chmod +x "$APP_DIR/deploy/update.sh"

systemctl daemon-reload
systemctl enable --now remotetrade-limit-paper.service
systemctl enable --now remotetrade-poly-5m.service
systemctl enable --now remotetrade-poly-rtds.service
systemctl enable --now remotetrade-poly-clob.service
systemctl enable --now remotetrade-poly-replay.timer
systemctl enable --now remotetrade-venue-discovery.timer
systemctl enable --now remotetrade-bitbank-route-probe.timer
systemctl enable --now remotetrade-dex-route-probe.timer
systemctl enable --now remotetrade-maker-probe.service
systemctl enable --now remotetrade-depth-arb.timer
systemctl enable --now remotetrade-backup.timer
systemctl enable --now remotetrade-health.timer
systemctl enable --now remotetrade-report.timer
systemctl enable --now remotetrade-update.timer

echo "Installed remotetrade at $APP_DIR"
echo "Edit config: sudo nano $APP_DIR/.env"
echo "Logs: sudo journalctl -u remotetrade-limit-paper.service -f"
echo "Updates: sudo journalctl -u remotetrade-update.service -n 50 --no-pager"
