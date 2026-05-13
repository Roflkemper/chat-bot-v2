#!/bin/bash
# Установка bot7 на Mac как полный prod-сервис.
# Запуск: bash ~/Downloads/install_mac.sh
# Перед запуском должны быть в ~/Downloads/:
#   - bot7_repo.tar.gz
#   - mac_env_local.txt
#   - mac_ginarea_env.txt

set -e

DOWNLOADS=$HOME/Downloads
BOT7_PATH=$HOME/code/bot7

echo ""
echo "=== bot7 Mac installer ==="
echo ""

# Pre-flight
for f in bot7_repo.tar.gz mac_env_local.txt mac_ginarea_env.txt; do
    if [ ! -f "$DOWNLOADS/$f" ]; then
        echo "ERROR: $DOWNLOADS/$f not found. AirDrop missing?"
        exit 1
    fi
done

if ! command -v python3.10 >/dev/null 2>&1; then
    echo "Python 3.10 not found. Installing via Homebrew..."
    if ! command -v brew >/dev/null 2>&1; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    brew install python@3.10
fi

# 1. Unpack repo
echo "Step 1/6: Unpacking repo..."
mkdir -p $BOT7_PATH
tar xzf $DOWNLOADS/bot7_repo.tar.gz -C $BOT7_PATH

# 2. venv
echo "Step 2/6: Creating venv + installing dependencies..."
cd $BOT7_PATH
python3.10 -m venv .venv
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# 3. .env.local
echo "Step 3/6: Setting up .env.local..."
cp $DOWNLOADS/mac_env_local.txt $BOT7_PATH/.env.local
cp $DOWNLOADS/mac_ginarea_env.txt $BOT7_PATH/ginarea_tracker/.env

# 4. pmset (sleep settings)
echo "Step 4/6: Setting pmset (requires sudo for sleep prevention)..."
sudo pmset -c sleep 0
sudo pmset -c disksleep 0
sudo pmset -c powernap 0
sudo pmset -c standby 0

# 5. launchd plist setup
echo "Step 5/6: Setting up 4 launchd services..."
mkdir -p $BOT7_PATH/logs

for label in app-runner market-collector ginarea-tracker state-snapshot; do
    src=$BOT7_PATH/docs/launchd_templates/com.bot7.${label}.plist
    dst=$HOME/Library/LaunchAgents/com.bot7.${label}.plist
    if [ -f "$src" ]; then
        sed -e "s|%BOT7_PATH%|$BOT7_PATH|g" \
            -e "s|/Users/USERNAME/bot7|$BOT7_PATH|g" \
            "$src" > "$dst"
        launchctl unload "$dst" 2>/dev/null || true
        launchctl load "$dst"
        echo "  loaded: $label"
    else
        echo "  skipped: $label (template not found at $src)"
    fi
done

# 6. Smoke check
echo "Step 6/6: Smoke check (waiting 30s for startup)..."
sleep 30
echo ""
echo "Running processes:"
ps aux | grep -E "app_runner|market_collector|ginarea_tracker|state_snapshot" | grep -v grep | awk '{print "  PID="$2" CMD="$11" "$12" "$13}'
echo ""
echo "Loaded services:"
launchctl list | grep com.bot7 | awk '{print "  "$3" (status="$2")"}'

echo ""
echo "=== DONE ==="
echo ""
echo "Logs:"
echo "  tail -f $BOT7_PATH/logs/launchd_app_runner.log"
echo "  tail -f $BOT7_PATH/logs/app.log"
echo ""
echo "Telegram should receive startup messages within 1-2 minutes."
echo ""
echo "IMPORTANT: After verifying everything works, DELETE secrets:"
echo "  rm $DOWNLOADS/mac_env_local.txt $DOWNLOADS/mac_ginarea_env.txt"
