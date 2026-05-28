#!/usr/bin/env bash
set -euo pipefail

# Paste this into DigitalOcean "Startup scripts".
# If the repository is private, set GITHUB_TOKEN below to a fine-grained token
# with read-only Contents access, or use a deploy key instead.

REPO_OWNER="huruki-geo"
REPO_NAME="remotetrade"
APP_DIR="/opt/remotetrade"
GITHUB_TOKEN=""

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y git ca-certificates

if [ -n "$GITHUB_TOKEN" ]; then
  REPO_URL="https://${GITHUB_TOKEN}@github.com/${REPO_OWNER}/${REPO_NAME}.git"
else
  REPO_URL="https://github.com/${REPO_OWNER}/${REPO_NAME}.git"
fi

if [ ! -d "$APP_DIR/.git" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
REPO_URL="$REPO_URL" bash deploy/install.sh
