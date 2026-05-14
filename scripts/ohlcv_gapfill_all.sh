#!/bin/bash
# Hourly gap-fill: append latest 1m bars from Binance for all tracked symbols.
# Run by LaunchAgent com.bot7.ohlcv-gapfill.
set -euo pipefail

ROOT="/Users/alexeychechikov/code/bot7"
PY="$ROOT/.venv/bin/python"
SCRIPT="$ROOT/scripts/ohlcv_ingest.py"
SYMBOLS=("BTCUSDT" "ETHUSDT" "XRPUSDT")

# Target = now (UTC), formatted ISO-8601 with Z.
TARGET_END="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cd "$ROOT"

for sym in "${SYMBOLS[@]}"; do
    echo "=== $sym  target=$TARGET_END ==="
    "$PY" "$SCRIPT" --symbol "$sym" --interval 1m --target-end "$TARGET_END" --workers 4 || {
        echo "FAILED: $sym (continuing with next symbol)"
    }
done

echo "=== gap-fill cycle done $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
