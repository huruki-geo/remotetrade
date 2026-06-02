#!/usr/bin/env bash
set -euo pipefail

ASSET_PATH="${1:?usage: upload-github-release-asset.sh ASSET_PATH [RELEASE_TAG]}"
RELEASE_TAG="${2:-remotetrade-data-$(date -u +%Y%m%d)}"
REPOSITORY="${GITHUB_ARCHIVE_REPOSITORY:?set GITHUB_ARCHIVE_REPOSITORY to owner/repository}"
TOKEN="${GITHUB_ARCHIVE_TOKEN:?set GITHUB_ARCHIVE_TOKEN}"
API_URL="${GITHUB_API_URL:-https://api.github.com}"
UPLOADS_URL="${GITHUB_UPLOADS_URL:-https://uploads.github.com}"
API_VERSION="${GITHUB_API_VERSION:-2026-03-10}"
RELEASE_NAME="RemoteTrade data $(date -u +%Y-%m-%d)"
TEMP_RESPONSE="$(mktemp)"

trap 'rm -f "$TEMP_RESPONSE"' EXIT

github_api() {
  curl --fail-with-body --silent --show-error \
    -H "Accept: application/vnd.github+json" \
    -H "Authorization: Bearer $TOKEN" \
    -H "X-GitHub-Api-Version: $API_VERSION" \
    "$@"
}

STATUS="$(
  github_api \
    --output "$TEMP_RESPONSE" \
    --write-out '%{http_code}' \
    "$API_URL/repos/$REPOSITORY/releases/tags/$RELEASE_TAG" || true
)"
if [ "$STATUS" = "404" ]; then
  github_api \
    --request POST \
    --output "$TEMP_RESPONSE" \
    "$API_URL/repos/$REPOSITORY/releases" \
    -d "$(printf '{"tag_name":"%s","name":"%s","body":"Automated VPS paper-trading data archive.","draft":false,"prerelease":false}' "$RELEASE_TAG" "$RELEASE_NAME")"
elif [ "$STATUS" != "200" ]; then
  echo "Could not read GitHub release $RELEASE_TAG (HTTP $STATUS)." >&2
  cat "$TEMP_RESPONSE" >&2
  exit 1
fi

RELEASE_ID="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["id"])' "$TEMP_RESPONSE")"
ASSET_NAME="$(basename "$ASSET_PATH")"
ENCODED_ASSET_NAME="$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$ASSET_NAME")"

github_api \
  --request POST \
  -H "Content-Type: application/gzip" \
  --data-binary "@$ASSET_PATH" \
  "$UPLOADS_URL/repos/$REPOSITORY/releases/$RELEASE_ID/assets?name=$ENCODED_ASSET_NAME" \
  >/dev/null

echo "Uploaded $ASSET_NAME to GitHub release $RELEASE_TAG."
