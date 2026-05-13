# launchd templates для bot7 на macOS

Готовый стек `.plist` файлов для запуска bot7 как production-сервиса на маке.
Заменяет Windows Task Scheduler полностью.

## Стек процессов (4 main + 8 cron = 12 plist)

### Main процессы (long-running, KeepAlive=true)

| Plist | Что делает | RAM | Под caffeinate |
|---|---|---:|:---:|
| `com.bot7.app-runner.plist` | Главный бот (asyncio loop, ~30 tasks) | ~700 MB | ✓ (-di) |
| `com.bot7.market-collector.plist` | WS streams Bybit/Binance/OKX | ~150 MB | ✓ (-i) |
| `com.bot7.ginarea-tracker.plist` | Snapshots ботов GinArea | ~100 MB | ✓ (-i) |
| `com.bot7.state-snapshot.plist` | Periodic state-snapshot.zip | ~50 MB | (no) |

### Cron tasks (StartInterval, KeepAlive=false)

| Plist | Скрипт | Расписание |
|---|---|---|
| `com.bot7.watchdog.plist` | `scripts/watchdog.py` | каждые 120s |
| `com.bot7.rotate-journals.plist` | `scripts/rotate_state_journals.py` | daily 06:00 |
| `com.bot7.precision-tracker.plist` | `scripts/setup_precision_tracker.py` | daily 08:00 |
| `com.bot7.daily-kpi.plist` | `scripts/daily_kpi_report.py` | daily 09:00 |
| `com.bot7.change-log.plist` | `scripts/daily_change_log.py` | daily 09:30 |
| `com.bot7.refresh-ict.plist` | `scripts/refresh_ict_levels.py` | weekly Sun 05:00 |
| `com.bot7.restart-check.plist` | `scripts/check_restart_frequency.py` | hourly |
| `com.bot7.pipeline-growth.plist` | `scripts/pipeline_growth_monitor.py` | every 6h |

## Установка (фоновый prod на Mac M1)

### Step 1 — Pre-flight pmset

Мак должен быть **всегда в charger** + не засыпать. Команды через `sudo`:

```bash
sudo pmset -c sleep 0          # на charge — не засыпать
sudo pmset -c disksleep 0      # диски не парковать
sudo pmset -c displaysleep 10  # экран гасить через 10 мин — не влияет на bg процессы
sudo pmset -c powernap 0       # отключить PowerNap (мак тогда вообще не уйдёт в спящий)
sudo pmset -c standby 0        # отключить Standby (deep sleep с RAM в SSD)

# Проверка:
pmset -g | head -15
```

Дополнительно — **отключить sleep при закрытой крышке** (Clamshell mode):
- Способ 1 (легко): включить через **Amphetamine** app из Mac App Store, режим "Quick Action: Allow lid close".
- Способ 2 (CLI): `sudo pmset -c lidwake 0` (но это другое — мак НЕ просыпается при открытии).
- Способ 3 (внутри plist): уже сделано через `caffeinate -di` в `app-runner.plist` — пока процесс жив, мак не уснёт даже при закрытой крышке.

**Caffeinate** работает даже с закрытой крышкой на Apple Silicon **только если ноут в charger** (твой случай).

### Step 2 — Подготовка plist'ов

Все шаблоны используют `%BOT7_PATH%` placeholder. Заменить:

```bash
cd ~/bot7
mkdir -p logs

export BOT7_PATH=$HOME/bot7

# Скопировать с подставленным путём
for src in docs/launchd_templates/com.bot7.*.plist; do
    dst=~/Library/LaunchAgents/$(basename "$src")
    sed "s|%BOT7_PATH%|$BOT7_PATH|g" "$src" > "$dst"
    # Также заменить старый USERNAME placeholder в старых файлах (cron tasks)
    sed -i.bak "s|USERNAME|$(whoami)|g" "$dst"
    rm -f "$dst.bak"
done

ls ~/Library/LaunchAgents/com.bot7.*.plist  # должно быть 12 файлов
```

### Step 3 — Загрузка в launchd

```bash
cd ~/Library/LaunchAgents

# Idempotent reload (unload если был + load)
for plist in com.bot7.*.plist; do
    launchctl unload "$plist" 2>/dev/null
    launchctl load "$plist" && echo "OK: $plist" || echo "FAIL: $plist"
done

# Проверка процессов через 30s
sleep 30
launchctl list | grep com.bot7
ps aux | grep -E "app_runner|market_collector|ginarea_tracker|watchdog" | grep -v grep
```

Ожидание: 4-5 python процессов running.

### Step 4 — Проверка логов

```bash
# launchd выводы
tail -f ~/bot7/logs/launchd_app_runner.log
tail -f ~/bot7/logs/launchd_collector.log
tail -f ~/bot7/logs/launchd_watchdog.log

# App-логи (внутренние)
tail -f ~/bot7/logs/app.log
tail -f ~/bot7/market_live/collector.log
```

В TG должны прийти стандартные стартап-уведомления (если `ENABLE_TELEGRAM=1` в `.env.local`).

## Управление

```bash
# Status
launchctl list | grep com.bot7

# Stop one
launchctl unload ~/Library/LaunchAgents/com.bot7.app-runner.plist

# Restart one (kill+reload — самое надёжное)
launchctl unload ~/Library/LaunchAgents/com.bot7.app-runner.plist
launchctl load ~/Library/LaunchAgents/com.bot7.app-runner.plist

# Restart все main (после git pull)
for label in app-runner market-collector ginarea-tracker state-snapshot; do
    launchctl unload ~/Library/LaunchAgents/com.bot7.${label}.plist
    launchctl load   ~/Library/LaunchAgents/com.bot7.${label}.plist
done

# Stop all
for plist in ~/Library/LaunchAgents/com.bot7.*.plist; do
    launchctl unload "$plist"
done
```

## launchctl notes

- `RunAtLoad=true` — task runs immediately после `launchctl load`.
- `KeepAlive=true` — рестарт после любого exit (даже успешного). Для long-running daemon.
- `StartInterval=N` — countdown N сек от previous start. Для cron-style.
- `StartCalendarInterval` — точный cron (`Hour: 6, Minute: 0` = daily 06:00).
- `ThrottleInterval=30` — минимум 30s между restart attempts (anti crash-loop).

## Troubleshooting

**Процесс не стартует:**
```bash
launchctl list com.bot7.app-runner
# Status code != 0 — есть ошибка. Подробнее:
cat ~/bot7/logs/launchd_app_runner.err
```

**Мак засыпает несмотря на caffeinate:**
- Проверь зарядное: caffeinate с закрытой крышкой работает только на charger.
- Проверь `pmset -g | grep -i lid`.
- Жёсткий вариант: оставить открытую крышку + Auto-Lock OFF в System Preferences.

**Дубли процессов:**
- Если launchctl load был запущен дважды без unload — может быть. Проверь `ps aux | grep app_runner`.
- Решение: `launchctl unload`, `pkill -f app_runner.py`, `launchctl load`.

**Mac restart — что произойдёт:**
- При логине пользователя launchd agents автоматически загружаются (RunAtLoad=true).
- **Важно:** агенты грузятся при логине пользователя, не при boot. Если ноут перезагружается и пользователь не залогинен — bot7 НЕ стартует. Решение: автологин пользователя в System Preferences → Users & Groups → Login Options → Automatic login.

## Memory budget на M1 8GB

| Процесс | RAM (live data) |
|---|---:|
| app_runner.py | ~700 MB |
| market_collector | ~150 MB |
| ginarea_tracker | ~100 MB |
| state_snapshot | ~50 MB |
| **Total bot7** | **~1 GB** |
| macOS система | ~3 GB |
| Браузер + IDE | ~2-3 GB |
| Свободно | **~1-2 GB** (норма) |

⚠ **pytest** с heavy fixtures съест до 8GB — упрётся в swap. Перед прогоном full test suite — остановить app_runner.

## Безопасный stop при git pull

```bash
# Workflow для обновления:
cd ~/bot7
git pull origin main
# Если изменились .plist или main код:
launchctl unload ~/Library/LaunchAgents/com.bot7.app-runner.plist
launchctl load ~/Library/LaunchAgents/com.bot7.app-runner.plist
# Если изменился collector:
launchctl unload ~/Library/LaunchAgents/com.bot7.market-collector.plist
launchctl load ~/Library/LaunchAgents/com.bot7.market-collector.plist
```
