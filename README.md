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
