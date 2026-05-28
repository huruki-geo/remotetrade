#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/remotetrade}"
BACKUP_DIR="$APP_DIR/backups"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

mkdir -p "$BACKUP_DIR"
tar -czf "$BACKUP_DIR/data-$STAMP.tar.gz" -C "$APP_DIR" data
find "$BACKUP_DIR" -name 'data-*.tar.gz' -mtime +14 -delete
