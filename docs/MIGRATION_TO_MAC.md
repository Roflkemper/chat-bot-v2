# Bot7 — миграция Windows → Mac

Полная инструкция для второго Claude Code на маке. Делает копию текущего бота со всеми трекерами read-only и observability стэком.

## Что переезжает

| Компонент | Назначение | Mac-готовность |
|---|---|---|
| `app_runner.py` + setup_detector | Главный pipeline, 14 детекторов | ✓ pathlib, conditional sys.platform |
| `services/` (50+ модулей) | Pipeline / observability / TG | ✓ all paths via pathlib |
| `scripts/` (cron-ready) | rotate, KPI, precision, change-log, ICT refresh | ✓ universal |
| `tests/` (484+ tests) | Регрессия | ✓ |
| `state/*.json*` | Runtime state (P-15 leg, dedup) | ✓ переносится 1:1 |
| `ginarea_live/*.csv` | GinArea tracker output (read-only мониторинг) | ✓ переносится |
| `market_live/*.csv` | Live BTCUSDT/ETH/XRP 1m | ✓ переносится |
| `backtests/frozen/*.csv` | Frozen 2y OHLCV | Optional, можно скачать на Mac |
| **Windows Task Scheduler** | 14 cron tasks | **❌ Заменяется launchd .plist (см. ниже)** |

## Что НЕ переносим (Windows-only)

1. **services/cron_report.py** — использует `schtasks /Query`. На Mac обернуть в `sys.platform == "win32"` или сделать launchd-эквивалент.
2. **scripts/watchdog.py BREAKAWAY_FROM_JOB flags** — Windows process detachment. На Mac уже есть fallback `start_new_session=True`. Работает сразу.
3. **6 backtest research tools** с хардкодом `C:\Users\Kemper\Documents\Codex\...` — research-only, не production. Если нужны на маке — заменить путь через env var (см. fix-list ниже).

## Шаги миграции

### 1. На Windows (исходная машина) — подготовка пакета

```bash
# Заархивировать чистый snapshot
cd c:/bot7
git status -s   # должно быть clean (или закоммитить всё)
git log --oneline | head -1  # запомнить commit hash

# Архив исходников (без data/)
tar czf bot7_source_$(date +%Y%m%d).tar.gz \
  --exclude='.venv' --exclude='__pycache__' --exclude='node_modules' \
  --exclude='data/historical' --exclude='data/ict_levels' \
  --exclude='backtests/frozen' --exclude='logs' \
  --exclude='state/pipeline_metrics_*.jsonl' \
  app_runner.py config.py services/ scripts/ tools/ tests/ \
  handlers/ models/ core/ storage/ renderers/ \
  conftest.py pytest.ini .env.example .gitignore docs/ \
  ginarea_tracker/ market_collector/

# Архив state (runtime) — переносится отдельно
tar czf bot7_state_$(date +%Y%m%d).tar.gz \
  state/p15_state.json \
  state/p15_equity.jsonl \
  state/setups.jsonl \
  state/setup_outcomes.jsonl \
  state/setup_precision_outcomes.jsonl \
  state/gc_confirmation_audit.jsonl \
  state/grid_coordinator_fires.jsonl \
  state/disabled_detectors.json \
  state/setup_precision_prev_status.json

# Live data (optional — Mac будет собирать заново при запуске)
tar czf bot7_live_data_$(date +%Y%m%d).tar.gz \
  ginarea_live/ market_live/ 2>/dev/null

# Перенести .env.local руками (содержит secrets)
cat .env.local  # скопировать в безопасный канал
```

### 2. На Mac — установка

Требуется: macOS 12+, Python 3.10+, ~5GB свободного места.

```bash
# Создать рабочую директорию
mkdir -p ~/bot7
cd ~/bot7

# Распаковать пакет
tar xzf ~/Downloads/bot7_source_YYYYMMDD.tar.gz
tar xzf ~/Downloads/bot7_state_YYYYMMDD.tar.gz
tar xzf ~/Downloads/bot7_live_data_YYYYMMDD.tar.gz  # если переносим

# Создать venv
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt  # или собрать из imports

# .env.local руками — paste secrets
cp .env.example .env.local
# отредактировать: BOT_TOKEN, BITMEX_API_KEY, ADVISOR_DEPO_TOTAL, etc

# Smoke test — статус
python -c "from services.status_report import build_status_report; print(build_status_report())"
# Должно показать что нет процессов (бот не запущен) но state читается

# Запустить тесты
python -m pytest tests/services/setup_detector/ tests/services/common/ -q
# Ожидается ~250 passed

# Запустить full suite (исключив ginarea_api который требует pytest-httpx)
python -m pytest tests/ -q --ignore=tests/services/ginarea_api -x
# Ожидается 900+ passed
```

### 3. На Mac — launchd cron setup

Создать `~/Library/LaunchAgents/com.bot7.watchdog.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.bot7.watchdog</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/USERNAME/bot7/.venv/bin/python</string>
        <string>/Users/USERNAME/bot7/scripts/watchdog.py</string>
    </array>
    <key>WorkingDirectory</key><string>/Users/USERNAME/bot7</string>
    <key>StartInterval</key><integer>120</integer>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>/Users/USERNAME/bot7/logs/launchd_watchdog.log</string>
    <key>StandardErrorPath</key><string>/Users/USERNAME/bot7/logs/launchd_watchdog.err</string>
</dict>
</plist>
```

Аналогично для остальных 8 cron'ов (см. таблицу ниже). Шаблон в `docs/launchd_templates/`.

```bash
launchctl load ~/Library/LaunchAgents/com.bot7.watchdog.plist
launchctl list | grep com.bot7  # должна появиться запись
```

### 4. Cron jobs to recreate (8 штук)

| Plist label | Schedule | Script |
|---|---|---|
| `com.bot7.watchdog` | every 2 min | `scripts/watchdog.py` |
| `com.bot7.rotate-journals` | daily 06:00 | `scripts/rotate_state_journals.py` |
| `com.bot7.precision-tracker` | daily 08:00 | `scripts/setup_precision_tracker.py` |
| `com.bot7.daily-kpi` | daily 09:00 | `scripts/daily_kpi_report.py` |
| `com.bot7.change-log` | daily 09:30 | `scripts/daily_change_log.py` |
| `com.bot7.refresh-ict` | weekly Sun 05:00 | `scripts/refresh_ict_levels.py` |
| `com.bot7.restart-check` | hourly | `scripts/check_restart_frequency.py` |
| `com.bot7.pipeline-growth` | every 6h | `scripts/pipeline_growth_monitor.py` |

## Pre-existing issues для исправления на Mac

1. **Backtest tools hardcode** — 6 файлов содержат `C:\Users\Kemper\Documents\Codex\...`:
   - `tools/_backtest_combined_all_bots.py:23`
   - `tools/_backtest_combined_all_bots_v2.py:28`
   - `tools/_backtest_combined_all_bots_v3_adaptive.py:32`
   - `tools/_backtest_grid_interventions.py:36`
   - `tools/_validate_engine_short_objem.py:32`
   - `tools/calibrate_ginarea.py:27`
   - `scripts/reconcile_production.py:40`
   
   Если не нужны для production — оставить как есть. Если нужны — заменить:
   ```python
   CODEX_ROOT = os.environ.get("CODEX_ROOT", str(Path.home() / "Codex"))
   sys.path.insert(0, f"{CODEX_ROOT}/src")
   ```

2. **services/cron_report.py** — wrap `_query_tasks` в `if sys.platform != "win32": return []`. Или сделать launchd version (`launchctl list`).

3. **pytest-httpx** не установлен → ginarea_api тесты не собираются. Запустить:
   ```bash
   pip install pytest-httpx
   ```

## Архитектура (для второго Claude Code)

**Главный observability стэк:**
- `services/setup_detector/pipeline_metrics.py` пишет каждое событие detection pipeline в `state/pipeline_metrics.jsonl`
- 8 cron-скриптов вычитывают этот файл + другие state файлы и формируют отчёты в Telegram
- 19 TG команд: `/status /p15 /ginarea /pipeline /precision /histogram /inspect /cron /disable /enable /changelog /audit /report_today ...`

**Live trading (paper only):**
- bot7 НЕ ОТКРЫВАЕТ реальные сделки на BitMEX
- Все decisions в `state/paper_trades.jsonl`
- GinArea grid bots работают отдельно (трекаются read-only)

**P-15 multi-asset (валидированная стратегия):**
- BTC × LONG/SHORT, ETH × LONG/SHORT, XRP × LONG/SHORT — 6 параллельных legs
- Per-pair sizing factor: BTC×1.0, ETH×0.5, XRP×0.3
- Max 2 same-direction legs одновременно
- Backtest 2y PF 3.04-3.91 на каждой паре

**Сейчас в production:**
- `short_pdh_rejection` DISABLED через `.env.local` (DEGRADED)
- `GC_SHADOW_MODE=1` — GC решения записываются но не применяются (1-2 недели данных собираем)
- 9 cron'ов работают
- ~50 событий pipeline в час, ~5-10 setups в день

## Mac Claude Code ТЗ (на одну строку)

> Запустить bot7 на маке как read-only replica для observability (без вмешательства в торговлю): распаковать архивы, создать venv, скопировать `.env.local`, написать 8 launchd `.plist` (templates в `docs/launchd_templates/`), запустить `python -m pytest tests/services/setup_detector/ -q` (≥250 passed), запустить watchdog вручную для smoke, потом загрузить `launchctl load`. Проверить через 24 часа что cron daily KPI пришёл в TG.

## Контрольный список миграции

- [ ] git status clean на Windows, последний commit в безопасном месте
- [ ] 3 архива созданы (source + state + live)
- [ ] `.env.local` скопирован безопасно
- [ ] Python 3.10+ на Mac, venv создан
- [ ] requirements.txt установлен
- [ ] tests/services/setup_detector/ passed
- [ ] `python -c "from services.status_report import build_status_report; print(build_status_report())"` работает
- [ ] 8 launchd .plist созданы и loaded
- [ ] watchdog вручную тикнут, поднял app_runner
- [ ] 24h: пришёл daily KPI в TG
- [ ] 48h: pipeline_metrics.jsonl растёт, нет detector_failed flood
