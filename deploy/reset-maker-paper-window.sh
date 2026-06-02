#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/remotetrade}"
DATA_DIR="$APP_DIR/data"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
INVALIDATED_DIR="$DATA_DIR/invalidated/$STAMP"

mkdir -p "$INVALIDATED_DIR"
systemctl stop remotetrade-bitbank-poly-maker.service remotetrade-coincheck-poly-maker.service

move_if_present() {
  local path="$1"
  if [ -e "$path" ]; then
    mv -- "$path" "$INVALIDATED_DIR/"
  fi
}

move_if_present "$DATA_DIR/bitbank_poly_maker_events.csv"
move_if_present "$DATA_DIR/bitbank_poly_maker_state.json"
move_if_present "$DATA_DIR/coincheck_poly_maker_events.csv"
for path in "$DATA_DIR"/coincheck_poly_maker_*_state.json; do
  move_if_present "$path"
done

systemctl start remotetrade-bitbank-poly-maker.service remotetrade-coincheck-poly-maker.service
echo "Invalidated maker-paper window moved to $INVALIDATED_DIR."
