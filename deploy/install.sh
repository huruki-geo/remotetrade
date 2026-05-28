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
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-depth-arb.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-depth-arb.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-backup.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-backup.timer" /etc/systemd/system/
chmod +x "$APP_DIR/deploy/backup-data.sh"

systemctl daemon-reload
systemctl enable --now remotetrade-limit-paper.service
systemctl enable --now remotetrade-depth-arb.timer
systemctl enable --now remotetrade-backup.timer

echo "Installed remotetrade at $APP_DIR"
echo "Edit config: sudo nano $APP_DIR/.env"
echo "Logs: sudo journalctl -u remotetrade-limit-paper.service -f"
