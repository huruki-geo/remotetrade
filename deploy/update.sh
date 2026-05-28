#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/remotetrade}"
BRANCH="${BRANCH:-main}"
SERVICE="${SERVICE:-remotetrade-limit-paper.service}"

cd "$APP_DIR"

git config --global --add safe.directory "$APP_DIR" >/dev/null 2>&1 || true
git fetch origin "$BRANCH"

LOCAL="$(git rev-parse HEAD)"
REMOTE="$(git rev-parse "origin/$BRANCH")"

if [ "$LOCAL" = "$REMOTE" ]; then
  echo "remotetrade already up to date: $LOCAL"
  exit 0
fi

echo "updating remotetrade: $LOCAL -> $REMOTE"

git pull --ff-only origin "$BRANCH"

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -e "$APP_DIR"

install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-limit-paper.service" /etc/systemd/system/
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

systemctl daemon-reload
systemctl restart "$SERVICE"
systemctl restart remotetrade-depth-arb.timer
systemctl restart remotetrade-backup.timer
systemctl restart remotetrade-health.timer
systemctl restart remotetrade-report.timer
systemctl restart remotetrade-update.timer

echo "remotetrade updated to $REMOTE"
