#!/bin/bash
# Bot7 → Mac migration package builder.
# Run on Windows source machine. Produces 3 tarballs in current dir.
#
# Usage: bash scripts/prepare_mac_migration.sh

set -e
cd "$(dirname "$0")/.."

DATE=$(date +%Y%m%d_%H%M%S)
OUTDIR="../bot7_mac_$DATE"
mkdir -p "$OUTDIR"

echo "[migrate] Preparing migration package: $OUTDIR"

# 1. Verify clean working tree
DIRTY=$(git status --porcelain | wc -l)
if [ "$DIRTY" -gt 0 ]; then
    echo "[migrate] WARNING: working tree not clean ($DIRTY changes)"
    echo "[migrate] Continuing anyway — but commit first for reproducible state"
fi

COMMIT=$(git rev-parse --short HEAD)
echo "[migrate] Current commit: $COMMIT"
echo "$COMMIT" > "$OUTDIR/COMMIT_HASH.txt"

# 2. Source archive (no .venv, no caches, no big data)
echo "[migrate] Building source archive..."
tar czf "$OUTDIR/bot7_source.tar.gz" \
    --exclude='.venv' \
    --exclude='__pycache__' \
    --exclude='node_modules' \
    --exclude='.git' \
    --exclude='data/historical' \
    --exclude='data/ict_levels' \
    --exclude='backtests/frozen' \
    --exclude='logs' \
    --exclude='state/pipeline_metrics_*.jsonl' \
    --exclude='state/setups_*.jsonl' \
    --exclude='*.pyc' \
    --exclude='*.bak*' \
    app_runner.py config.py conftest.py pytest.ini \
    .env.example .gitignore \
    services/ scripts/ tools/ tests/ \
    handlers/ models/ core/ storage/ renderers/ \
    docs/ collectors/ market_collector/ ginarea_tracker/ \
    requirements.txt 2>/dev/null || echo "[migrate]   (some optional dirs missing — ok)"

# 3. State archive (runtime state — small, must transfer)
echo "[migrate] Building state archive..."
STATE_FILES=$(ls state/p15_state.json state/p15_equity.jsonl \
    state/setups.jsonl state/setup_outcomes.jsonl \
    state/setup_precision_outcomes.jsonl \
    state/gc_confirmation_audit.jsonl \
    state/grid_coordinator_fires.jsonl \
    state/disabled_detectors.json \
    state/setup_precision_prev_status.json \
    state/app_runner_starts.jsonl \
    state/regime_state.json \
    state/state_latest.json 2>/dev/null || true)
if [ -n "$STATE_FILES" ]; then
    tar czf "$OUTDIR/bot7_state.tar.gz" $STATE_FILES
fi

# 4. Live data archive (large but recoverable; optional transfer)
echo "[migrate] Building live data archive (large)..."
if [ -d "market_live" ] || [ -d "ginarea_live" ]; then
    tar czf "$OUTDIR/bot7_live_data.tar.gz" \
        market_live/ ginarea_live/ 2>/dev/null || true
fi

# 5. Summary
echo "[migrate] === Package contents ==="
ls -la "$OUTDIR/"
echo ""
echo "[migrate] === Sizes ==="
du -sh "$OUTDIR"/* 2>/dev/null

cat > "$OUTDIR/README_MIGRATION.txt" <<EOF
Bot7 migration package
======================

Source commit: $COMMIT
Built: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Builder OS: $(uname -s 2>/dev/null || echo Windows)

Files in this directory:
  bot7_source.tar.gz       — code + tests + docs (no .venv, no big data)
  bot7_state.tar.gz        — runtime state (P-15 leg, dedup, outcomes)
  bot7_live_data.tar.gz    — market_live + ginarea_live (LARGE, optional)
  COMMIT_HASH.txt          — source commit for reference

On Mac:
  1. Read docs/MIGRATION_TO_MAC.md (in bot7_source archive)
  2. tar xzf bot7_source.tar.gz   →  ~/bot7
  3. tar xzf bot7_state.tar.gz    →  ~/bot7
  4. tar xzf bot7_live_data.tar.gz  →  ~/bot7  (optional)
  5. cp .env.example .env.local + paste secrets
  6. python3 -m venv .venv && source .venv/bin/activate
  7. pip install -r requirements.txt
  8. cp docs/launchd_templates/*.plist ~/Library/LaunchAgents/
     # On Mac, run this with literal \$(whoami) — it expands to your username:
     sed -i '' "s/USERNAME/\$(whoami)/g" ~/Library/LaunchAgents/com.bot7.*.plist
     for p in ~/Library/LaunchAgents/com.bot7.*.plist; do launchctl load \$p; done
  9. python -m pytest tests/services/setup_detector/ -q
EOF

echo ""
echo "[migrate] ✓ Done. Package at: $OUTDIR"
echo "[migrate] Next: copy $OUTDIR to Mac and follow README_MIGRATION.txt"
