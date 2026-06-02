#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/remotetrade}"
BACKUP_DIR="$APP_DIR/backups"
ARCHIVE_ENV_FILE="${ARCHIVE_ENV_FILE:-$APP_DIR/.archive.env}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
ARCHIVE="$BACKUP_DIR/data-$STAMP.tar.gz"
TEMP_ARCHIVE="$ARCHIVE.tmp"

if [ -f "$ARCHIVE_ENV_FILE" ]; then
  # shellcheck disable=SC1090
  source "$ARCHIVE_ENV_FILE"
fi
LOCAL_RETENTION_DAYS="${LOCAL_BACKUP_RETENTION_DAYS:-2}"

mkdir -p "$BACKUP_DIR" "$APP_DIR/data/archive"
trap 'rm -f "$TEMP_ARCHIVE"' EXIT
find "$APP_DIR/data" -maxdepth 1 -type f -name '*.previous' -exec mv -t "$APP_DIR/data/archive" -- {} +
tar --warning=no-file-changed --ignore-failed-read -czf "$TEMP_ARCHIVE" -C "$APP_DIR" data
mv "$TEMP_ARCHIVE" "$ARCHIVE"

if [ -n "${GITHUB_ARCHIVE_TOKEN:-}" ] && [ -n "${GITHUB_ARCHIVE_REPOSITORY:-}" ]; then
  "$APP_DIR/deploy/upload-github-release-asset.sh" "$ARCHIVE"
  rm -f "$ARCHIVE"
else
  echo "GitHub archive upload is disabled; keeping local backup $ARCHIVE."
fi

# Large JSONL segments are captured in the compressed backup above. Keep smaller CSV segments
# locally so multi-day paper-trading reports can still read the complete comparison window.
find "$APP_DIR/data/archive" -maxdepth 1 -type f \( -name '*.jsonl' -o -name '*.jsonl.previous' \) -delete
find "$BACKUP_DIR" -name 'data-*.tar.gz' -mtime "+$LOCAL_RETENTION_DAYS" -delete
