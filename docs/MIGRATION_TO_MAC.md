# Bot7 — миграция Windows → Mac (full production)

**Дата обновления:** 2026-05-13
**Цель:** перенести live-production bot7 с Windows на MacBook Air M1. Mac работает 24/7 в charger как замена PC. После cutover — Win можно выключить.

## Зачем

- Mac M1 потребляет 4-8 Вт vs PC 50-100 Вт (~10× экономия электричества).
- Тише, не нужно спать с включённым PC.
- Удобнее dev: тот же файловой системе пишешь фичи / гоняешь backtests / запускаешь prod.
- Один компьютер вместо двух.

## Что переезжает (всё)

| Компонент | Mac-готовность | Заметки |
|---|---|---|
| `app_runner.py` (main bot) | ✓ cross-platform | основной asyncio loop |
| `market_collector` (WS) | ✓ | Bybit/Binance/OKX streams |
| `ginarea_tracker` | ✓ | снапшоты ботов |
| `scripts/watchdog.py` | ✓ уже cross-platform | psutil based |
| `services/` (50+) | ✓ | pathlib везде |
| `tests/` (1500+) | ✓ после 2026-05-13 fix | hardcoded `C:/bot7` убраны |
| `data/historical/` | ✓ | parquet/csv |
| **Task Scheduler** | ❌ → launchd | 12 plist в `docs/launchd_templates/` |
| `bot7_start.bat` / `RUN_APP.bat` | ❌ → launchd plist | можно удалить после cutover |

## Pre-flight на Windows (старая машина)

```bash
# 1. Зафиксировать всё
cd c:/bot7
git status                    # должно быть clean
git log --oneline | head -1   # запомнить commit hash
git push origin main          # убедиться что remote up-to-date

# 2. Сделать backup state (опционально)
cd ..
tar czf bot7_state_backup_$(date +%Y%m%d).tar.gz \
    --exclude='bot7/.venv' \
    --exclude='bot7/__pycache__' \
    --exclude='bot7/logs' \
    bot7/state bot7/ginarea_live bot7/market_live

# 3. .env.local — секреты на безопасный transfer
cat c:/bot7/.env.local  # скопировать содержимое в защищённый channel
# Варианты переноса:
#   а) 1Password / Bitwarden secure note
#   б) USB-флешка
#   в) AirDrop в iCloud Keychain
#   г) Encrypted ZIP через cloud
```

## Установка на Mac M1

### 1. Python 3.10 + Homebrew

```bash
# Если Homebrew нет:
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python 3.10 (важно: 3.10 как на prod, не 3.11+ — много прод-зависимостей tested против 3.10)
brew install python@3.10
brew install git

# Проверка
python3.10 --version  # должно быть 3.10.x
```

### 2. Clone repo

```bash
mkdir -p ~/code
cd ~/code
git clone <YOUR_REMOTE_URL> bot7
cd bot7

# Если есть state backup из Win:
tar xzf ~/Downloads/bot7_state_backup_YYYYMMDD.tar.gz -C ..
# должно создать ~/code/bot7/state, ~/code/bot7/ginarea_live, ~/code/bot7/market_live
```

### 3. Venv + зависимости

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install pytest-httpx  # dev dep, чтобы ginarea_api тесты тоже проходили
```

### 4. Конфигурация secrets

```bash
cp .env.example .env.local
nano .env.local   # вставить BOT_TOKEN, BITMEX_*, GINAREA_*, ADVISOR_DEPO_TOTAL и т.д.
```

Минимум для запуска (см. `.env.example` для полного списка):
- `BOT_TOKEN` — Telegram bot
- `ALLOWED_CHAT_IDS` — твои chat IDs
- `BITMEX_API_KEY` + `BITMEX_API_SECRET` — read-only (для margin poller)
- `GINAREA_EMAIL` + `GINAREA_PASSWORD` + `GINAREA_TOTP_SECRET` + `GINAREA_API_URL`
- `ADVISOR_DEPO_TOTAL` — текущий депозит USD

### 5. Smoke test

```bash
# Status report (no live processes)
python -c "from services.status_report import build_status_report; print(build_status_report())"

# Test suite (subset, ~30 sec)
python -m pytest tests/services/setup_detector/ tests/services/common/ tests/services/cascade_alert/ tests/services/pre_cascade_alert/ -q

# Полный test suite (~3 min, ожидается ~1500 passed)
python -m pytest tests/ -q --ignore=tests/services/ginarea_api -x
```

### 6. Запуск live (foreground первый раз)

```bash
# Не через launchd — чтобы убедиться что всё работает
python app_runner.py
# Жди стартап-логов:
#   cascade_alert.start ...
#   liq_pre_cascade.start ...
#   weekly_self_report.start ...
# Должно прийти стандартное TG-уведомление о старте

# Если всё ок — Ctrl+C, переход к launchd setup.
```

### 7. launchd setup (background prod)

См. полную инструкцию: [`docs/launchd_templates/README.md`](launchd_templates/README.md).

```bash
# pmset (отключить sleep на charge)
sudo pmset -c sleep 0
sudo pmset -c disksleep 0
sudo pmset -c powernap 0
sudo pmset -c standby 0

# Скопировать plist'ы с подстановкой $BOT7_PATH
export BOT7_PATH=$HOME/code/bot7
mkdir -p $BOT7_PATH/logs

for src in $BOT7_PATH/docs/launchd_templates/com.bot7.*.plist; do
    dst=~/Library/LaunchAgents/$(basename "$src")
    sed -e "s|%BOT7_PATH%|$BOT7_PATH|g" \
        -e "s|/Users/USERNAME/bot7|$BOT7_PATH|g" \
        "$src" > "$dst"
done

# Loading
for plist in ~/Library/LaunchAgents/com.bot7.*.plist; do
    launchctl unload "$plist" 2>/dev/null
    launchctl load "$plist" && echo "OK: $plist"
done

# Verify через 30 sec
sleep 30
launchctl list | grep com.bot7
ps aux | grep -E "app_runner|market_collector|ginarea_tracker|watchdog" | grep -v grep
```

## Cutover (переключение Win → Mac)

### День 0 (подготовка)

- [ ] На Mac: всё установлено, smoke test зелёный, launchd готов но НЕ load'ен
- [ ] На Win: live работает, `.env.local` экспортирован

### День 1 (переключение, ~30 минут)

**Внимание:** не запускать оба бота одновременно — будут двойные TG-алерты + race в GinArea API.

```bash
# 1. На Win: остановить prod (НЕ удалять, на случай rollback)
# В PowerShell:
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
  Where-Object { $_.CommandLine -match 'app_runner|market_collector|ginarea_tracker' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# Подождать 30 сек, убедиться что в TG прекратились новые алерты.

# 2. На Mac: запустить prod через launchd
for plist in ~/Library/LaunchAgents/com.bot7.*.plist; do
    launchctl load "$plist"
done

# 3. Проверка TG: должны прийти стартап-уведомления С MAC.
#    Если в течение 5 минут пришли cascade_alert, liq_pre_cascade.start логи — OK.

# 4. На Win: отключить Task Scheduler bot7 tasks (но НЕ удалить)
# В PowerShell:
schtasks /Change /TN "\bot7-supervisor" /Disable
schtasks /Change /TN "\bot7-watchdog" /Disable
# и т.д. для всех bot7-* tasks
```

### Дни 2-3 (наблюдение)

- Мониторить TG: алерты идут с мака?
- Проверить через 24h: пришёл daily KPI (если включён)?
- Проверить через 48h: ginarea_live/snapshots.csv обновляется?
- Win — оставить как hot-standby. Если что — можно перезапустить за 5 минут.

### День 4+ (финальный)

Если 48h на маке без проблем:

```powershell
# На Win: задизейбли Task Scheduler tasks, потом можно spaceshut Win.
# Опционально: удалить bot7 tasks и вообще выключить PC.
```

## Что делать на Mac в режиме live + dev одновременно

**Главное правило:** prod процессы крутятся 24/7 через launchd. Dev работаешь в **той же файловой системе** через git branches.

### Workflow

```bash
# Утром — pull последних изменений
cd ~/code/bot7
git pull origin main

# Создать feature branch
git checkout -b feat/new-edge

# Писать код, тестировать
python -m pytest tests/services/<твой модуль> -q

# ⚠ Не редактировать live config / .env.local во время prod — может ребутнуть launchd

# Когда готов — merge
git checkout main
git merge feat/new-edge
git push

# Применить к prod:
launchctl unload ~/Library/LaunchAgents/com.bot7.app-runner.plist
launchctl load   ~/Library/LaunchAgents/com.bot7.app-runner.plist
# Или kickstart:
launchctl kickstart -k gui/$(id -u)/com.bot7.app-runner
```

### Heavy R&D (backtests) — без помех prod

Backtest-tools (`tools/_backtest_*.py`) могут потреблять много RAM/CPU. На M1 8GB:

```bash
# Перед heavy backtest — посмотреть память
top -l 1 | head -10  # check RAM headroom

# Если меньше 2GB свободно — временно остановить app_runner:
launchctl unload ~/Library/LaunchAgents/com.bot7.app-runner.plist

# Запустить backtest
python tools/_backtest_session_breakout.py

# После — запустить обратно
launchctl load ~/Library/LaunchAgents/com.bot7.app-runner.plist
```

## Pre-existing issues (фиксы уже сделаны 2026-05-13)

- ✅ `collectors/config.py` — default path через `Path(__file__).resolve()` вместо `C:/bot7/`
- ✅ `tests/tools/test_sweep_runner.py` — cross-platform пути
- ✅ `tests/services/managed_grid_sim/conftest.py` — fixture path через `Path(__file__)`
- ✅ `tests/services/managed_grid_sim/test_sweep_engine.py` — пути через `_REPO_ROOT`
- ⚠ 6 backtest tools (`tools/_backtest_combined_*.py`, `tools/_validate_engine_short_objem.py`, etc) с hardcoded `C:\Users\Kemper\Documents\Codex\...` — research-only, не production. Запускать с env var `CODEX_ROOT=$HOME/Codex` если нужны.

## Rollback план

Если на маке что-то критично сломалось (например, GinArea API не работает с Mac IP, или WS падают):

```bash
# 1. На Mac: остановить launchd
for plist in ~/Library/LaunchAgents/com.bot7.*.plist; do
    launchctl unload "$plist"
done

# 2. На Win: re-enable Task Scheduler
schtasks /Change /TN "\bot7-supervisor" /Enable
# или ручной запуск:
C:\bot7\bot7_start.bat
```

Win остаётся как hot-standby пока не уверен в стабильности мака (рекомендую 1-2 недели).

## Контрольный список миграции

- [ ] git push с последними изменениями на remote
- [ ] state backup (state/, ginarea_live/, market_live/) — опционально
- [ ] `.env.local` скопирован через secure channel
- [ ] Mac M1: Python 3.10, Homebrew, Git установлены
- [ ] `git clone` + `python3.10 -m venv .venv` + `pip install -r requirements.txt`
- [ ] `.env.local` отредактирован на маке
- [ ] Smoke test зелёный: `python -m pytest tests/services/cascade_alert/ -q`
- [ ] Live foreground test: `python app_runner.py` (Ctrl+C через 2 мин)
- [ ] `pmset -c sleep 0` + `pmset -c powernap 0`
- [ ] 12 launchd .plist скопированы в `~/Library/LaunchAgents/`
- [ ] `launchctl load` всех plist
- [ ] Через 30 сек: 4-5 процессов в `ps aux`
- [ ] TG получает алерты с мака
- [ ] Win: prod процессы остановлены
- [ ] Win: Task Scheduler tasks disabled (не удалены)
- [ ] 48h наблюдение: всё стабильно
- [ ] (опц) Win: выключить PC
