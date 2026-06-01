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
else
  echo "updating remotetrade: $LOCAL -> $REMOTE"

  git pull --ff-only origin "$BRANCH"

  python3 -m venv "$APP_DIR/.venv"
  "$APP_DIR/.venv/bin/pip" install --upgrade pip
  "$APP_DIR/.venv/bin/pip" install -e "$APP_DIR"
fi

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
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-bitbank-poly-maker.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-coincheck-poly-maker.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-dex-route-probe.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-dex-route-probe.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-bsc-qash-route-probe.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-bsc-qash-route-probe.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-boba-cex-dex-probe.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-boba-cex-dex-probe.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-boba-zencha-probe.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-boba-zencha-probe.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-boba-synapse-probe.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-boba-synapse-probe.timer" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-boba-atomic-route-probe.service" /etc/systemd/system/
install -m 0644 "$APP_DIR/deploy/systemd/remotetrade-boba-atomic-route-probe.timer" /etc/systemd/system/
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

systemctl daemon-reload
systemctl enable remotetrade-poly-5m.service
systemctl enable remotetrade-poly-rtds.service
systemctl enable remotetrade-poly-clob.service
systemctl enable --now remotetrade-poly-replay.timer
systemctl enable --now remotetrade-venue-discovery.timer
systemctl enable --now remotetrade-bitbank-route-probe.timer
systemctl enable --now remotetrade-bitbank-poly-maker.service
systemctl enable --now remotetrade-coincheck-poly-maker.service
systemctl enable --now remotetrade-dex-route-probe.timer
systemctl enable --now remotetrade-bsc-qash-route-probe.timer
systemctl enable --now remotetrade-boba-cex-dex-probe.timer
systemctl enable --now remotetrade-boba-zencha-probe.timer
systemctl enable --now remotetrade-boba-synapse-probe.timer
systemctl enable --now remotetrade-boba-atomic-route-probe.timer
systemctl enable --now remotetrade-depth-arb.timer
systemctl enable --now remotetrade-backup.timer
systemctl enable --now remotetrade-health.timer
systemctl enable --now remotetrade-report.timer
systemctl enable --now remotetrade-update.timer
systemctl enable remotetrade-maker-probe.service
systemctl restart "$SERVICE"
systemctl restart remotetrade-poly-5m.service
systemctl restart remotetrade-poly-rtds.service
systemctl restart remotetrade-poly-clob.service
systemctl restart remotetrade-bitbank-poly-maker.service
systemctl restart remotetrade-coincheck-poly-maker.service
systemctl restart remotetrade-maker-probe.service

echo "remotetrade updated to $REMOTE"
