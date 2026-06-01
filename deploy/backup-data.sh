#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/remotetrade}"
BACKUP_DIR="$APP_DIR/backups"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$BACKUP_DIR/data-$STAMP.tar.gz"
TEMP_ARCHIVE="$ARCHIVE.tmp"

mkdir -p "$BACKUP_DIR"
trap 'rm -f "$TEMP_ARCHIVE"' EXIT
tar --warning=no-file-changed --ignore-failed-read -czf "$TEMP_ARCHIVE" -C "$APP_DIR" data
mv "$TEMP_ARCHIVE" "$ARCHIVE"
find "$BACKUP_DIR" -name 'data-*.tar.gz' -mtime +14 -delete
