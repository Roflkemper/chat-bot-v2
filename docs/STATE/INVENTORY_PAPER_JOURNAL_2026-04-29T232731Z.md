# INVENTORY PAPER JOURNAL 2026-04-29T232731Z

## PRE-FLIGHT

- [x] git status — clean (no staged changes)
- [x] .claude/skills/ — 15 skills confirmed
- [x] PROJECT_RULES.md — read
- [x] docs/STATE/ROADMAP.md — Phase 0 in_progress, Phase 1 = TZ-PAPER-JOURNAL-LIVE planned
- [x] docs/PROJECT_MAP.md — 95 active modules, 1 real conflict
- [x] docs/STATE/RESTORED_FEATURES_AUDIT_2026-04-29T200504Z.json — read (relevant entries below)
- [x] advise_signals.jsonl, advise_null_signals.jsonl, advise_action_match.jsonl,
      advise_followup.jsonl — all protected in .gitignore, not tracked

---

## 0. Sources прочитаны

| Source | Path | Key findings |
|---|---|---|
| app_runner.py | `app_runner.py` | asyncio tasks model, 6 existing tasks |
| orchestrator_loop.py | `core/orchestrator/orchestrator_loop.py` | OrchestratorLoop.start() coroutine |
| regime_classifier.py | `core/orchestrator/regime_classifier.py` | ACTIVE — RANGE/TREND_UP/TREND_DOWN/COMPRESSION/CASCADE labels |
| data_loader.py | `core/data_loader.py` | `load_klines()` REST + 12s TTL cache |
| pipeline.py | `core/pipeline.py` | `build_full_snapshot()` — all-in-one entry |
| state_latest.json | `docs/STATE/state_latest.json` | exposure (shorts/longs/net_btc), ts: 2026-04-29T23:45 |
| portfolio.py | `_recovery/restored/src/advisor/v2/portfolio.py` | `read_portfolio_state()` — reads snapshots_v2.csv |
| telegram_runtime.py | `services/telegram_runtime.py` lines 694-796 | existing /advisor pattern: build_full_snapshot + read_portfolio_state |
| signal_generator.py | `services/advise_v2/signal_generator.py` | `generate_signal(market_context, current_exposure)` |
| schemas.py | `services/advise_v2/schemas.py` | MarketContext.regime_label Literal (10 values) |

---

## 1. Scheduler model recommendation

### Available options

| Option | How | Idle RAM | Auto-restart | Startup | Integration cost |
|---|---|---|---|---|---|
| **app_runner.py embed** | asyncio coroutine, 8th task | 0 extra (shared process) | same as main process | 0s (в процессе) | small: 1 coroutine + 1 create_task |
| Standalone daemon | отдельный Python процесс, while True + sleep | ~50MB | нет (нужен Task Scheduler / supervisord) | <5s | medium: new entry point + config |
| Windows Task Scheduler | .bat/.ps1, каждые 5 мин | 0 idle | OS-managed | ~5-10s Python startup | small: new script, но 5min schedule granularity |
| apscheduler / celery | не установлены в requirements.txt | +dep overhead | нет по умолчанию | — | high: new dependency |

### Recommendation: **app_runner embed**

Pattern уже отработан для `_run_adaptive_grid` (300s interval):

```python
async def _run_paper_journal(stop_event: asyncio.Event) -> None:
    from services.paper_journal import run_once
    while not stop_event.is_set():
        try:
            await asyncio.to_thread(run_once)
        except Exception as exc:
            logger.exception("paper_journal.error: %s", exc)
        try:
            await asyncio.wait_for(asyncio.shield(stop_event.wait()), timeout=300.0)
        except asyncio.TimeoutError:
            pass
```

Добавить в `main()`:
```python
paper_journal_task = asyncio.create_task(_run_paper_journal(stop_event), name="paper_journal")
```

**Rationale:** app_runner.py уже работает 24/7. Нет новых зависимостей. 0 дополнительного RAM. Pattern идентичен существующим tasks. Единственный риск: если app_runner падает, бумажный журнал тоже останавливается — но это желаемое поведение.

---

## 2. Regime classifier status

### Найдено: ACTIVE (`core/orchestrator/regime_classifier.py`)

Компонент присутствует и активен. НО:

### SCHEMA MISMATCH — PARTIAL BLOCKER

| Существующие labels (regime_classifier.py) | Ожидаемые labels (MarketContext.regime_label) |
|---|---|
| `CASCADE_UP` | `impulse_up` |
| `CASCADE_DOWN` | `impulse_down` |
| — (нет) | `impulse_up_exhausting` |
| — (нет) | `impulse_down_exhausting` |
| `RANGE` (BB narrow) | `range_tight` |
| `RANGE` (BB wide) | `range_wide` |
| `TREND_UP` | `trend_up` |
| `TREND_DOWN` | `trend_down` |
| `COMPRESSION` | `consolidation` |
| — (fallback) | `unknown` |

**No mapping function exists anywhere** — ни в active, ни в restored.

### Mapping feasibility

`RegimeSnapshot` содержит `metrics.bb_width_pct_1h` и `metrics.adx_1h` — достаточно для расчёта вариантов:
- `RANGE` → `range_tight` если `bb_width_pct_1h < 3.0`, иначе `range_wide`
- `CASCADE_UP` → `impulse_up_exhausting` если `adx_1h > 40` И `metrics.adx_slope_1h < 0`, иначе `impulse_up`
- `CASCADE_DOWN` → аналогично
- Остальные — прямое 1:1

Scope: функция `map_regime_to_advise_label(snapshot: RegimeSnapshot) → str`, ~30 lines.

### Recommendation: **TZ-REGIME-ADAPTER (small TZ, BEFORE paper journal)**

Не нужен новый TZ-REGIME-CLASSIFIER. Нужен только adapter ~30 строк в
`services/advise_v2/regime_adapter.py`. Без него `generate_signal()` будет
работать с `regime_label="unknown"` → majority of setups won't match.

**Severity: partial blocker** — paper journal запустится, но сигналы не будут генерироваться корректно. Требует TZ-REGIME-ADAPTER до Phase 1 launch.

---

## 3. Live OHLCV source

### Что есть

- `core.data_loader.load_klines(symbol, timeframe, limit, use_cache=True)` — REST API (Binance/Bybit), in-process cache TTL = **12 секунд**
- `core.pipeline.build_full_snapshot(symbol)` — вызывает `get_klines()` внутри + запускает `classify()` → возвращает dict с `regime`, `price`, `candles_1h_last`, `rsi`, etc.
- **НЕТ WebSocket OHLCV** — все данные через REST
- Collectors: WebSocket только для liquidations (Binance liq stream) — не OHLCV

### Paper journal pattern (уже используется в telegram_runtime.py /advisor)

```python
snapshot = build_full_snapshot(symbol='BTCUSDT')
```

Один вызов даёт: `price`, `regime.primary`, `metrics.rsi_1h`, `metrics.rsi_5m`,
`candles_*`, `bb_*`. Latency: ~1-2s REST round-trip. Достаточно для 300s interval.

### Recommendation: **`build_full_snapshot('BTCUSDT')` как single OHLCV source**

Для 300s интервала: 1 REST call каждые 5 минут = приемлемо. 12s TTL cache не мешает — при вызове раз в 5 минут cache always expired.

Freshness: данные будут ~1-2s old на момент записи в JSONL — достаточно для бумажного журнала.

---

## 4. CurrentExposure source

### state_latest.json

Файл `docs/STATE/state_latest.json` (ts: 2026-04-29T23:45) содержит:
```json
"exposure": {
  "shorts_btc": -0.284,
  "longs_btc": 0.2715,
  "net_btc": -0.0125,
  "nearest_short_liq": {"price": 129960.0},
  "nearest_long_liq": {"price": 43919.2}
}
```

**Отсутствуют**: `free_margin_pct`, `available_usd`, `margin_coef_pct` — обязательные поля `CurrentExposure`.

### read_portfolio_state() — ESTABLISHED SOURCE

`_recovery/restored/src/advisor/v2/portfolio.py` — `read_portfolio_state()`:
- Читает `ginarea_tracker/ginarea_live/snapshots_v2.csv` (TTL cache 10s)
- Возвращает `PortfolioState` с: `depo_total`, `depo_available`, `free_margin_pct`, `dd_pct`, `primary_balance`
- Уже используется: `telegram_runtime.py` `/advisor` и `orchestrator_loop.py`
- **Работает** пока ginarea_tracker запущен (snapshots_v2.csv актуален)

### CurrentExposure mapping из PortfolioState + exposure dict

```
CurrentExposure(
  net_btc     = state_latest.exposure.net_btc,
  shorts_btc  = state_latest.exposure.shorts_btc,
  longs_btc   = state_latest.exposure.longs_btc,
  free_margin_pct = portfolio.free_margin_pct,
  available_usd   = portfolio.depo_available,
  margin_coef_pct = portfolio.dd_pct,   # proxy
)
```

### Recommendation: **read_portfolio_state() для margin data + state_latest.json для positions**

Fallback: если snapshots_v2.csv не существует → `free_margin_pct=50.0`, `available_usd=env.ADVISOR_DEPO_TOTAL`.

---

## 5. Implementation plan summary

| Область | Action | Complexity | Blocker |
|---|---|---|---|
| Scheduler | Add `_run_paper_journal` coroutine в app_runner.py | small | нет |
| Regime adapter | `TZ-REGIME-ADAPTER`: `services/advise_v2/regime_adapter.py` ~30 lines | small | **ДА** — partial blocker для сигналов |
| OHLCV | Use `build_full_snapshot('BTCUSDT')` — уже есть | none | нет |
| CurrentExposure | `read_portfolio_state()` + fallback env vars | small | нет |

### Порядок выполнения

```
1. TZ-REGIME-ADAPTER (blocker — small TZ)
   → services/advise_v2/regime_adapter.py
   → 1 function: map_regime_to_advise_label(snapshot)
   → tests: test_regime_adapter.py

2. TZ-PAPER-JOURNAL-LIVE
   → services/paper_journal.py (или services/advise_v2/paper_journal.py)
   → app_runner.py: add _run_paper_journal coroutine
   → reads: build_full_snapshot + read_portfolio_state
   → writes: state/advise_signals.jsonl + state/advise_null_signals.jsonl
```

### Нет новых зависимостей

Все компоненты уже в codebase: `generate_signal`, `signal_logger`, `build_full_snapshot`,
`read_portfolio_state`, `regime_classifier`. Нужен только adapter (~30 lines) + integration glue.

---

## 6. Skills applied

- `state_first_protocol`: read state_latest.json + verified ts freshness
- `project_inventory_first`: прочитал PROJECT_MAP + RESTORED_FEATURES_AUDIT + 10 source files
- `encoding_safety`: markdown output via UTF-8
- `regression_baseline_keeper`: read-only, no code changes
- `operator_role_boundary`: recommendations only, no implementation in this TZ
- `untracked_protection`: only docs/STATE/ new markdown

---

## OPEN_QUESTIONS resolved

1. **Regime classifier missing?** НЕТ — активен. Но schema mismatch → TZ-REGIME-ADAPTER обязателен.
2. **app_runner 24/7?** ДА — unified runtime, постоянно работает. Embed feasible.
3. **Live OHLCV?** НЕТУ WebSocket OHLCV — REST с 12s TTL. Для 300s interval достаточно.
