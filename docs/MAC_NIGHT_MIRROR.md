# Mac как ночное зеркало bot7

**Сценарий:** Win остаётся main dev машиной (работа над фичами, бектесты, тесты, разработка). Mac M1 24/7 в charger тихо запускает копию bot7 чтобы:
- Ночью TG-алерты приходили (каскады, сетапы, истощение)
- Live data (liquidations, OHLCV) накапливалась без перерывов
- Не нужно было оставлять Win включённым по ночам

**Главный принцип:** обе машины работают одновременно, **без конфликтов**:
- Mac → real bot, real чаты, real GinArea (живой prod)
- Win → dev-bot, тестовый чат, GinArea отключён (только разработка)

## Архитектура

```
┌──────────────────────────────────┐         ┌──────────────────────────────────┐
│  Mac M1 (24/7, prod)             │         │  Win PC (дневной dev)            │
├──────────────────────────────────┤         ├──────────────────────────────────┤
│ Bot: @bot7_main (existing)        │         │ Bot: @bot7_dev (new, see below)  │
│ ALLOWED_CHAT_IDS=<personal>       │         │ ALLOWED_CHAT_IDS=<test_chat>     │
│ ROUTINE_CHAT_IDS=<group>          │         │ ROUTINE_CHAT_IDS=               │
│                                  │         │                                  │
│ BITMEX_API_KEY=<real>             │         │ BITMEX_API_KEY=<real, read-only> │
│ GINAREA_*=<real>                  │         │ GINAREA_*= (empty)               │
│                                  │         │                                  │
│ ✓ app_runner.py                   │         │ ✓ app_runner.py (dev mode)       │
│ ✓ market_collector                │         │ ✓ market_collector (parallel)    │
│ ✓ ginarea_tracker                 │         │ ✗ ginarea_tracker (no creds)     │
│ ✓ watchdog                        │         │ ✗ watchdog (manual control)      │
│                                  │         │                                  │
│ → real TG чаты                    │         │ → test TG чат                    │
└──────────────────────────────────┘         └──────────────────────────────────┘
        │                                              │
        │   git push/pull через GitHub                 │
        └──────────────────────────────────────────────┘
```

Оба бота **независимы** в TG (разные токены), но имеют **одинаковый код** (через git).

## Шаг 1: Создать dev-бота в BotFather

В Telegram:

1. Открыть [@BotFather](https://t.me/BotFather)
2. `/newbot`
3. Имя: `bot7 dev` (любое)
4. Username: `bot7_dev_yourname_bot` (должно заканчиваться на `_bot`, быть уникальным)
5. Скопировать **dev token** (формат `123456:ABC-DEF...`)

Создать тестовый чат:
- Личный DM с ботом: написать любому `/start` — бот тебе ответит, ID = твой Telegram ID
- Или групповой: создать группу, добавить бота, отправить любое сообщение, узнать chat_id через `@userinfobot` или `/showmytgid`

Запомни:
- `DEV_BOT_TOKEN=...`
- `DEV_CHAT_ID=...`

## Шаг 2: На Win — переключить на dev-бота

```powershell
# В Windows env vars (Control Panel → System → Environment Variables → User):
# ИЛИ через PowerShell для текущей сессии:

[System.Environment]::SetEnvironmentVariable("BOT_TOKEN_DEV", "<dev_token>", "User")
[System.Environment]::SetEnvironmentVariable("ALLOWED_CHAT_IDS_DEV", "<dev_chat_id>", "User")

# Текущие prod значения оставить как есть (BOT_TOKEN, CHAT_ID) — они уйдут на мак.
```

В `c:\bot7\.env.local` (на Win) добавить:

```env
# Override prod-bot креды для dev-mode на Win.
# Reads these instead of system BOT_TOKEN if set.
BOT_TOKEN=<dev_token_here>
CHAT_ID=<dev_chat_id_here>
ALLOWED_CHAT_IDS=<dev_chat_id_here>

# Закомментить чтобы dev не слал в production group чат:
# ROUTINE_CHAT_IDS=-1003968750380

# GinArea — отключаем чтобы не конкурировать с Mac
# (просто закомментить, и ginarea_tracker не запустится)
# GINAREA_EMAIL=
# GINAREA_PASSWORD=
# GINAREA_TOTP_SECRET=
# GINAREA_API_URL=
```

После рестарта Win-бота — он будет слать в dev-чат, не мешая Mac-боту.

## Шаг 3: На Mac — установка prod-бота

Полный гайд: [MIGRATION_TO_MAC.md](MIGRATION_TO_MAC.md). Краткие шаги:

```bash
# 1. Python + venv
brew install python@3.10 git
mkdir -p ~/code && cd ~/code
git clone <YOUR_REMOTE_URL> bot7
cd bot7
python3.10 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt pytest-httpx

# 2. .env.local на Mac — РЕАЛЬНЫЕ креды (те что сейчас в env на Win)
cp .env.example .env.local
nano .env.local
```

В `.env.local` на Mac:

```env
# Real production credentials — переносим с Windows
BOT_TOKEN=<real_prod_token>            # тот же что сейчас на Win
CHAT_ID=574716090                       # твой личный
ALLOWED_CHAT_IDS=574716090
ROUTINE_CHAT_IDS=-1003968750380        # group

BITMEX_API_KEY=<real_readonly>
BITMEX_API_SECRET=<real>

GINAREA_EMAIL=<real>
GINAREA_PASSWORD=<real>
GINAREA_TOTP_SECRET=<real>
GINAREA_API_URL=https://app.ginarea.io/api

ADVISOR_DEPO_TOTAL=15145
ENABLE_TELEGRAM=1
```

```bash
# 3. Pmset (не засыпать)
sudo pmset -c sleep 0
sudo pmset -c disksleep 0
sudo pmset -c powernap 0
sudo pmset -c standby 0

# 4. Smoke test
python -m pytest tests/services/cascade_alert/ tests/services/pre_cascade_alert/ -q
# Должно быть ~30 passed

# 5. Foreground test (5 минут)
python app_runner.py
# Ожидаем TG-стартап в личный чат с реального бота.
# Если ОК — Ctrl+C, переход к launchd.
```

## Шаг 4: Перенести журналы и live-данные с Win на Mac

Чтобы Mac запустился **с накопленной историей** (не с нуля), переносим:

- `state/` — все journals (paper_trades, setups, KPI, dedup)
- `ginarea_live/` — снапшоты ботов GinArea за всё время (для cliff_monitor history)
- `market_live/` — live CSV (liquidations, OHLCV)

### На Win — упаковать данные

В cmd или PowerShell:

```cmd
cd c:\bot7
scripts\prepare_mac_transfer.bat
```

Занимает ~30 секунд. Скрипт создаст в `C:\bot7-transfer\`:
- `bot7_state_<TIMESTAMP>.tar.gz` (~7 MB — все journals, KPI, dedup)
- `bot7_ginarea_live_<TIMESTAMP>.tar.gz` (~3 MB — снапшоты ботов)
- `bot7_market_live_<TIMESTAMP>.tar.gz` (~0.3 MB — live CSV, без orderbook 2.6 GB)
- `bot7_secrets_<TIMESTAMP>.txt` (СЕКРЕТЫ — .env.local + BOT_TOKEN/CHAT_ID из env)

**Итого ~11 MB** на 4 файла — моментально через AirDrop / iCloud / USB.

Скрипт **не** переносит:
- `market_live/orderbook/` (2.6 GB — не используется в services, мак соберёт заново при необходимости)
- `backtests/` (5.5 GB — research-only, остаётся на Win)
- `data/historical/` (R&D parquet — переносить если хочешь делать research на маке)
- `state/_archive/`, `state/decision_log/*.jsonl` (старые archives, не критично)

### Перенести архивы на Mac

Варианты:
- **AirDrop** (если оба в одной сети): открыть `C:\bot7-transfer\` в проводнике → правый клик → Share → AirDrop. На маке примет в `~/Downloads/`.
- **USB-флешка** / внешний диск
- **iCloud Drive** или Google Drive — закинул на Win, скачал на Mac
- **scp** (если на Mac включён SSH): `scp bot7_*.tar.gz mac_user@<mac_ip>:~/Downloads/`

Секреты (`bot7_secrets_*.txt`) перенеси **отдельным защищённым каналом**:
- Зашифрованный ZIP с паролем
- 1Password / Bitwarden secure note
- AirDrop напрямую (не через cloud)
- НЕ через обычный email / Telegram

### На Mac — распаковать

```bash
cd ~/code/bot7

# Распаковать архивы (заменят пустые папки state/, ginarea_live/, market_live/)
tar xzf ~/Downloads/bot7_state_*.tar.gz
tar xzf ~/Downloads/bot7_ginarea_live_*.tar.gz
tar xzf ~/Downloads/bot7_market_live_*.tar.gz

# Проверка
ls state/ | wc -l          # ожидание: 100+ файлов
ls ginarea_live/           # ожидание: snapshots.csv, params.csv, events.csv
ls market_live/            # ожидание: market_1m.csv, liquidations.csv, signals.csv

# Размеры
du -sh state/ ginarea_live/ market_live/
# state/      ~50 MB
# ginarea_live/  ~100 MB
# market_live/   ~10 MB
```

### Секреты — открыть и применить

```bash
# 1. Открой bot7_secrets_*.txt в любом текстовом редакторе
# 2. Скопируй секцию '=== .env.local content ===' (всё до '=== System env')
# 3. Вставь в ~/code/bot7/.env.local
# 4. Из секции '=== System env (Windows User scope) ===' тоже добавь в .env.local:
nano ~/code/bot7/.env.local
# Должно быть в итоге примерно:
#   BOT_TOKEN=<реальный prod>
#   CHAT_ID=574716090
#   ALLOWED_CHAT_IDS=574716090
#   ROUTINE_CHAT_IDS=-1003968750380
#   BITMEX_API_KEY=<реальный>
#   BITMEX_API_SECRET=<реальный>
#   GINAREA_EMAIL=<реальный>
#   GINAREA_PASSWORD=<реальный>
#   GINAREA_TOTP_SECRET=<реальный>
#   GINAREA_API_URL=https://app.ginarea.io/api
#   ADVISOR_DEPO_TOTAL=15145
#   ENABLE_TELEGRAM=1

# 5. После — УДАЛИ bot7_secrets_*.txt с обеих машин!
shred -u ~/Downloads/bot7_secrets_*.txt  # mac
# На Win:
#   Remove-Item C:\bot7-transfer\bot7_secrets_*.txt -Force
```

### Smoke test после переноса

```bash
cd ~/code/bot7
source .venv/bin/activate

# Проверка что state читается
python -c "
import json
from pathlib import Path

print('=== State sanity check ===')
print('paper_trades:', sum(1 for _ in Path('state/paper_trades.jsonl').open()) if Path('state/paper_trades.jsonl').exists() else 'missing')
print('setups:', sum(1 for _ in Path('state/setups.jsonl').open()) if Path('state/setups.jsonl').exists() else 'missing')
print('cascade_accuracy:', sum(1 for _ in Path('state/cascade_accuracy.jsonl').open()) if Path('state/cascade_accuracy.jsonl').exists() else 'missing')
print('p15_equity:', sum(1 for _ in Path('state/p15_equity.jsonl').open()) if Path('state/p15_equity.jsonl').exists() else 'missing')

# Live data
import csv
print()
print('=== Live data sanity ===')
with Path('ginarea_live/snapshots.csv').open() as f:
    n = sum(1 for _ in f) - 1
print('ginarea snapshots rows:', n)
with Path('market_live/market_1m.csv').open() as f:
    n = sum(1 for _ in f) - 1
print('market_1m candles:', n)
with Path('market_live/liquidations.csv').open() as f:
    n = sum(1 for _ in f) - 1
print('liquidations rows:', n)
"
```

## Шаг 5: На Mac — launchd для 4 main процессов

Используем готовые шаблоны из `docs/launchd_templates/`:

```bash
cd ~/code/bot7
mkdir -p logs

export BOT7_PATH=$HOME/code/bot7

# Скопировать только 4 main + watchdog (cron tasks не нужны для night mirror — это твоё разработке нужно)
for label in app-runner market-collector ginarea-tracker state-snapshot watchdog; do
    src=docs/launchd_templates/com.bot7.${label}.plist
    dst=~/Library/LaunchAgents/com.bot7.${label}.plist
    sed -e "s|%BOT7_PATH%|$BOT7_PATH|g" \
        -e "s|/Users/USERNAME/bot7|$BOT7_PATH|g" \
        "$src" > "$dst"
done

# Загрузить
for plist in ~/Library/LaunchAgents/com.bot7.*.plist; do
    launchctl unload "$plist" 2>/dev/null
    launchctl load "$plist" && echo "OK: $plist"
done

# Проверка через 30s
sleep 30
ps aux | grep -E "app_runner|market_collector|ginarea_tracker" | grep -v grep
launchctl list | grep com.bot7
```

Должны прийти TG-стартапы **в реальные чаты с Mac**. С Win-dev-бота — в тестовый чат.

## Шаг 6: Проверка что нет двойных алертов

Через 1-2 часа:

1. **Личный TG чат**: смотри что алерты приходят **один раз** (не дубли). Только Mac в него пишет.
2. **Group ROUTINE**: LEVEL_BREAK / PAPER_TRADE приходят один раз — только с Mac.
3. **Тестовый dev чат**: туда сыпет Win — это нормально, можно использовать для дев-тестов.

Если в `personal` чате приходят **дубли** — значит Win всё ещё имеет old BOT_TOKEN. Проверь env vars и `.env.local` на Win, перезапусти Win-бота.

## Что НЕ переносим на Mac

Эти процессы остаются **только на Win** где есть время на heavy compute:

- ❌ **Backtests** (`tools/_backtest_*.py`)
- ❌ **R&D скрипты** (calibration, sweep_runner)
- ❌ **Pytest полный** (1500+ тестов, до 8GB RAM)
- ❌ **8 cron-tasks** (rotate-journals, daily-kpi, refresh-ict и т.д.) — это для **dev-only**, на маке не нужны для basic night mirror

Если потом захочется на Mac запускать cron tasks тоже — добавить остальные `.plist` из `docs/launchd_templates/` (см. полный гайд MIGRATION_TO_MAC.md).

## Daily workflow

### Утром (просыпаешься)

```bash
# На Win: открыть IDE, проверить TG чаты — что прилетело ночью.
# Mac работает, ты тоже работаешь — параллельно, не мешают.

cd c:\bot7
git pull       # синхронизируешь свои коммиты если делал на маке (редко)
# Дальше — нормальная dev работа.
```

### Вечером (засыпаешь)

```bash
# На Win: закоммитить изменения, push.
cd c:\bot7
git add -A
git commit -m "wip: today's progress"
git push

# На Mac: автоматически (cron или ручной hook) или вручную
ssh mac "cd ~/code/bot7 && git pull && launchctl kickstart -k gui/\$(id -u)/com.bot7.app-runner"

# Win — выключаешь / ничего не делаешь, mac продолжает работать
```

### Если на маке надо что-то дёрнуть руками

```bash
# Через SSH (если включил Remote Login в System Preferences)
ssh username@<mac_ip>

# Или через Screen Sharing (VNC через iCloud)
# Или физически за маком
```

## Минимальный stack на Mac (резюме)

| Процесс | RAM | Запускается | Шлёт TG |
|---|---:|---|---|
| `app_runner.py` | 700 MB | launchd KeepAlive | ✓ (personal + group) |
| `market_collector` | 150 MB | launchd KeepAlive | (нет) |
| `ginarea_tracker` | 100 MB | launchd KeepAlive | (через app_runner cliff_monitor) |
| `state-snapshot` | 50 MB | launchd KeepAlive | (нет) |
| `watchdog` | 30 MB | launchd каждые 120s | (через done.py) |
| **Total** | **~1 GB** | | |

## Rollback (если Mac не справляется)

```bash
# На Mac:
for plist in ~/Library/LaunchAgents/com.bot7.*.plist; do
    launchctl unload "$plist"
done

# На Win: убрать DEV-override, вернуть на prod-bot
# Удалить из .env.local строки BOT_TOKEN= и CHAT_ID=
# Раскомментировать GINAREA_*
# Перезапустить app_runner.py — снова прод на Win.
```

## Что делать после первой недели наблюдения

Если Mac стабилен (нет крэшей, TG алерты приходят) — можно:
- Поднять кол-во cron tasks на Mac (daily KPI, weekly reports)
- Отключить ночные запуски Win (если что-то на нём ещё запускается по cron)
- Постепенно перенести heavy compute на Mac (бектесты), оставить Win только для острого dev

Но это уже **полный prod migration** — см. [MIGRATION_TO_MAC.md](MIGRATION_TO_MAC.md).
