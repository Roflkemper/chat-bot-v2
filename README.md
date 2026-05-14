# Grid Orchestrator

Рабочий workspace: `C:\bot7`.

Проект управляет сеточными ботами GinArea на BitMEX и связанным analysis/backtest контуром. Текущий production runtime: `app_runner.py` (Unified Runtime: Telegram polling + OrchestratorLoop в одном процессе).

## Главное

- Актуальный архитектурный контекст: `docs/MASTER.md`
- Каталог playbook-приёмов: `docs/PLAYBOOK.md`
- Журнал сессий: `docs/SESSION_LOG.md`
- Reference по механике GinArea: `docs/GINAREA_MECHANICS.md`

## Текущее состояние

- `TZ-018` closed
- `TZ-019` closed
- `TZ-020 cleanup` partially done
- PLAYBOOK содержит 12 plays
- Валидатор: `12 OK / 0 errors`

Проверка:

```powershell
.venv\Scripts\python.exe -m src.playbook.cli validate
```

## Tests

```powershell
RUN_TESTS.bat
```

## Pre-commit hooks

Репо использует общие хуки в `.githooks/`. Установить один раз после `git clone`:

```powershell
.venv\Scripts\python.exe tools\install_hooks.py
```

Команда выставляет `core.hooksPath = .githooks` (idempotent — повторный запуск
безопасен) и помечает скрипты исполняемыми. Проверка статуса:

```powershell
.venv\Scripts\python.exe tools\install_hooks.py --check
```

Текущие проверки `pre-commit`:

- TZ-055 / TZ-064 — критические docs (`MASTER.md`, `PLAYBOOK.md`, `SESSION_LOG.md`,
  `HANDOFF*.md`, `STATE/QUEUE.md`, `PROJECT_RULES.md`, `GINAREA_MECHANICS.md`,
  `OPPORTUNITY_MAP_v1.md`) присутствуют.
- TZ-059 — все обязательные файлы скиллов в `.claude/skills/`.
- TZ-068 — `state_first_protocol.md` нельзя удалять.
- **TZ-VALIDATE-TZ-CI-PRECOMMIT** — каждый staged `docs/tz/*.md` проходит
  `python tools/validate_tz.py --file <path>`. Коммит блокируется только при
  `VERDICT: REJECTED` (hard errors). `REVIEW_NEEDED` warnings выводятся, но
  коммит проходит — оператор сам решает.

Bypass (только сознательно): `git commit --no-verify`.

Важно:

## frozen/ — исторические данные

| Файл | Описание | Размер |
|------|----------|--------|
| `frozen/labels/episodes.parquet` | BTC+ETH+XRP эпизоды (7401 штук) | ~214KB |
| `frozen/ETHUSDT_1m.parquet` | ETH USDT 1m klines, 366 дней | ~11MB |
| `frozen/XRPUSDT_1m.parquet` | XRP USDT 1m klines, 366 дней | ~8.6MB |
| `frozen/_metadata.json` | метаданные: источники, даты, кол-во баров | |
| `backtests/frozen/BTCUSDT_1m_2y.csv` | BTC 1m, 2 года (источник для BTC эпизодов) | 87MB |

Пересборка эпизодов: `python -m src.whatif.episodes_builder --symbols BTC,ETH,XRP`

---

- Не писать из тестов и бэктеста в live state `state/*.json`
- Frozen baseline в `state/baseline/*.json` не трогать без явного ТЗ
- Старый reference workspace с backtest/report артефактами: `C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat`
- При сверке использовать прежде всего `backtests/`, `reports/`, `data/`, `drafts/` из reference workspace
