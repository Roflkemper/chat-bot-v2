# HANDOFF 2026-04-30 part01

Generated: 2026-04-30T02:04Z by TZ-HANDOFF-2026-04-30
State snapshot: run at 2026-04-30T02:04 (CURRENT_STATE_2026-04-30_0204.md)

---

## How to use this handoff (для нового Claude)

1. Прочитать через Code этот файл целиком
2. Прочитать `docs/STATE/ROADMAP.md`
3. Прочитать `docs/STATE/state_latest.json`
4. Прочитать `docs/PROJECT_MAP.md`
5. Apply skills: `state_first_protocol`, `project_inventory_first`,
   `architect_inventory_first`, `session_handoff_protocol`,
   `operator_role_boundary`
6. Перейти к секции "Open TZs" ниже и работать по приоритету
7. **IMPORTANT:** TZ-PAPER-JOURNAL-LIVE уже выполнен в этой сессии.
   Не перевыполнять.

---

## Living state references

| Артефакт | Путь | Timestamp |
|---|---|---|
| Текущий стейт | [CURRENT_STATE_2026-04-30_0204.md](STATE/CURRENT_STATE_2026-04-30_0204.md) | 2026-04-30T02:04 |
| state_latest.json | [docs/STATE/state_latest.json](STATE/state_latest.json) | 2026-04-30T02:04 |
| PROJECT_MAP.md | [docs/PROJECT_MAP.md](PROJECT_MAP.md) | 2026-04-30T02:04 |
| ROADMAP.md | [docs/STATE/ROADMAP.md](STATE/ROADMAP.md) | current Phase 1 in_progress |
| state_inline.js | `docs/state_inline.js` | 2026-04-30T02:04 |

---

## Active threads

### THREAD 1: Phase 0 завершена

Status: **complete**

Что закрыто за сессию (commits):
- TZ-PROJECT-MEMORY-DEFENSE `9d7e5c2` (3-layer defense)
- TZ-CONFLICTS-TRIAGE `a91d317` (57 pairs classified, 0 real)
- TZ-ROADMAP-INTEGRATION `3620c20` (ROADMAP.md + dashboard + /roadmap)
- TZ-PROJECT-MAP-WHITELIST `dccd209` (58 false positives suppressed, 1 PARTIAL_OVERLAP остался)
- TZ-CALENDAR-REACTIVATION `345491f` (calendar.py + weekend_gap из restored в src/features/)
- TZ-INVENTORY-SIGNAL-LOGGER `b1d0a20`
- TZ-SIGNAL-LOGGER `6c10fb4`
- TZ-ACTION-TRACKER `d982d73`
- TZ-CALENDAR-INTO-MARKETCONTEXT `0cd11c9` (SessionContext + 6 pattern modifiers в setup_matcher)
- TZ-SKILL-ARCHITECT-INVENTORY-FIRST (architect self-defense skill + INC-013)
- TZ-INVENTORY-WEEKLY-COMPARISON-REPORT
- TZ-WEEKLY-COMPARISON-REPORT `f26ea35`
- TZ-GITIGNORE-ADVISE-RUNTIME `8a8b5cc`
- TZ-INVENTORY-PAPER-JOURNAL `059bb14`
- TZ-REGIME-ADAPTER `f5294ff` (10 mappings: TREND_UP/DOWN, COMPRESSION, RANGE+bb_width, CASCADE+adx exhaustion)

Test count: ~155 в services/advise_v2/, baseline 467+ full project, no new failures.

---

### THREAD 2: Phase 1 launch — TZ-PAPER-JOURNAL-LIVE

Status: **DONE commit `ef74db7`** (выполнен в этой же сессии)

**CORRECTION от архитектора:** TZ был нарезан и немедленно выполнен в той же сессии.
Не требует выполнения в новой сессии.

Что сделано:
- `services/advise_v2/paper_journal.py` — async paper journal loop (300s interval)
  - `_rsi()` pandas ewm RSI, `_build_market_context_sync()`, `_build_current_exposure_sync()`
  - `_run_one_iteration_sync()`: full error-wrapped pipeline → log_signal / log_null_signal
  - `paper_journal_loop()`: asyncio.to_thread, stop_event, runs first iteration before checking stop
- `services/advise_v2/regime_adapter.py`: добавлена `map_regime_dict_to_advise_label(regime: dict)`
- `services/advise_v2/__init__.py`: re-export paper_journal_loop, PAPER_JOURNAL_INTERVAL_SEC
- `app_runner.py`: `_run_paper_journal` coroutine + `paper_journal_task` как 8-й asyncio task
- `tests/services/advise_v2/test_paper_journal.py`: 16 tests, all green

CurrentExposure source: `docs/STATE/state_latest.json` + `config.ADVISOR_DEPO_TOTAL` (НЕ read_portfolio_state — `src.advisor.v2` не в active Python path, `snapshots_v2.csv` не существует).

Phase 1 running: paper journal пишет в `state/advise_signals.jsonl` + `state/advise_null_signals.jsonl` каждые 300s когда app_runner запущен.

Exit criteria Phase 1:
- Paper journal пишется minimum 14 дней непрерывно ← **waiting**
- Первый weekly report сгенерирован (модуль уже есть в `services/advise_v2/weekly_report.py`)
- Operator confirms comparison report даёт useful insight

---

### THREAD 3: Phase 0.5 — engine validation

Status: **blocked, ждём GinArea backtest скрины от operator**

Last verdict: TZ-RECONCILE-01-METHODOLOGY-FIX commit `fd003ff`
выдал RED по resolution gap — grid_step 0.03% слишком мал для
1m bar resolution (4-12× under-counting trades)

Strategy решение принято:
- Используем GinArea native backtest как ground truth
- Operator запускает manually backtests в UI (не API)
- Operator уже дал 2 скрина: short (test bot) + не помню что
  ещё было — operator подтвердит

Pending от operator:
- Long backtest скрин на BTCUSD inverse (для калибровки
  лонгов отдельно)
- Уточнение что доступно для экспорта из GinArea UI
  (только скриншот / есть кнопка экспорта / DevTools network)

Когда данные будут — нарезать TZ-CALIBRATE-VS-GINAREA
(sim vs GinArea на 6 production ботов).

---

### THREAD 4: PARTIAL_OVERLAP в conflicts

Status: **deferred, не блокер**

horizon_runner vs profit_lock_restart — semantic overlap
detected by PROJECT_MAP. Прочитать оба, решить keep/merge/rename.
TZ-HORIZON-PROFIT-LOCK-REVIEW в QUEUE, ~30 мин Code когда
дойдёт.

---

### THREAD 5: TZ-PROJECT-MAP-SEMANTIC-DETECTION

Status: **deferred**

Existing detector ловит symbol overlap (44 false positives на
collectors interface). Реальный конфликт cascade.py vs
setup_matcher.py не поймал (разные имена символов, одна
семантика). Усиление: docstring similarity или import graph
analysis. Не срочно, после Phase 1 stable.

---

### THREAD 6: TZ-FLAKY-TESTS-PROTECTION-ALERTS

Status: **deferred**

test_protection_alerts.py содержит 12 flaky tests rotating
1-2 failures каждый прогон. Идентифицировать root cause,
стабилизировать. ~30 мин Code.

---

### THREAD 7: TZ-PARAMS-FRESHNESS-GUARD

Status: **deferred**

state_snapshot.py должен проверять mtime params.csv. Если
age > 15 min И tracker не запущен — anomaly "params possibly
stale". ~15 мин Code.

---

### THREAD 8: TZ-OKX-EXTEND-INGESTION

Status: **deferred operational**

Расширить OKX historical ingestion до полных 90 дней через
--max-pages большее значение. Operator-side run, ~1 час сбора.

---

### THREAD 9: TZ-LIQ-COUNTERFACTUAL

Status: **deferred, ждёт Phase 1 paper data**

Counterfactual analysis влияния liq данных на PnL для решения
Coinglass подписки. Pre-requisites: paper journal data
накопилось 14+ дней + reconcile resolved.

---

### THREAD 10: TZ-COINGLASS — отменён

Status: **NOT proceeding**

Operator определил что использует Coinglass только для liq
heatmap вручную (утром/днём/вечером). Не покупаем API.
Manual /liq_set Telegram команда планируется как часть
Phase 1+ вместо API integration.

---

## Pending decisions от operator

### DECISION 1: GinArea UI экспорт — какой формат доступен

- (a) Только скриншоты UI
- (b) Есть кнопка "Export CSV" с trades list
- (c) DevTools network log (F12) с XHR JSON response
- (d) Что-то ещё

Влияет на дизайн TZ-CALIBRATE-VS-GINAREA.

### DECISION 2: Дополнительные backtest скрины

Operator готов сделать N backtests руками. Какие приоритеты:
- Long на BTCUSD inverse (LONG_C parameters) — критично для
  калибровки лонгов
- Short с другим target (например 0.20 или 0.30) — sanity
  check калибровочного фактора
- Другое?

### DECISION 3: PARTIAL_OVERLAP horizon_runner vs profit_lock_restart

Operator знает эти модули? Дать TZ-HORIZON-PROFIT-LOCK-REVIEW
сейчас или отложить?

---

## Anti-patterns (не повторять в новой сессии)

### INC-012: Architectural amnesia

Architect нарезал TZ-SETUP-MATCHER для Codex без знания про
существующий cascade.py duplicate и calendar.py отсутствие в
src/features/. Code/Codex написали параллельную реализацию,
тесты прошли изолированно, архитектура развалилась.
Detection: operator вручную обнаружил при ручной проверке.
Fix: TZ-PROJECT-MEMORY-DEFENSE v2 (3 layers).

### INC-013: Architect-side inventory pattern recurrence

3 раза за сессию architect отправлял TZ для нового модуля без
architect-side inventory check (signal_logger, action_tracker,
weekly_comparison_report). Code's inventory check каждый раз
catch'ил. Working safety net, но каждый catch ломает flow.
Fix: skill architect_inventory_first added. ARCHITECT в новой
сессии должен ПЕРЕД отправкой TZ для нового модуля проверить
PROJECT_MAP + RESTORED_FEATURES_AUDIT, нарезать
TZ-INVENTORY-<feature> first если потенциальный overlap.

### Вторичные паттерны

- Architect задавал operator технические вопросы про конфигурацию
  кода (git команды, какой scheduler model, какие пути) которые
  Code мог ответить grep'ом. Skill operator_role_boundary
  применяется — architect должен задавать только direction
  questions (priorities, decisions), не tech inventory.

- Architect один раз после Code rejection попытался "переформулировать
  TZ за один проход" вместо нарезания inventory TZ first. Skill
  architect_inventory_first включает recovery правило — после
  rejection всегда run inventory first.

---

## Recent commits (git log --oneline -25)

```
ef74db7 feat: TZ-PAPER-JOURNAL-LIVE Phase 1 launch — embed paper journal task in app_runner
f5294ff feat: TZ-REGIME-ADAPTER map active classifier to advise_v2 schema
059bb14 audit: TZ-INVENTORY-PAPER-JOURNAL pre-implementation inventory
f26ea35 feat: TZ-WEEKLY-COMPARISON-REPORT analytics on advise_v2 JSONL data
95fc280 feat: TZ-SKILL-ARCHITECT-INVENTORY-FIRST architect-side inventory defense
8a8b5cc chore: TZ-GITIGNORE-ADVISE-RUNTIME protect runtime JSONL
0cd11c9 feat: TZ-CALENDAR-INTO-MARKETCONTEXT integrate session intelligence into MarketContext + setup_matcher
d982d73 feat: TZ-ACTION-TRACKER signal-action-outcome correlator
b1d0a20 audit: TZ-INVENTORY-SIGNAL-LOGGER existing JSONL telemetry analysis
6c10fb4 TZ-SIGNAL-LOGGER: JSONL append-only logger for SignalEnvelope
dccd209 feat: TZ-PROJECT-MAP-WHITELIST suppress collector interface false positives
345491f feat: TZ-CALENDAR-REACTIVATION restore calendar + weekend_gap to src/features/
3620c20 feat: TZ-ROADMAP-INTEGRATION roadmap as source of truth
a91d317 audit: TZ-CONFLICTS-TRIAGE classify 57 parallel implementations
9d7e5c2 feat: TZ-PROJECT-MEMORY-DEFENSE 3-layer defense against architectural amnesia
98f9c62 audit: TZ-INVENTORY-RESTORED-FEATURES manifest of _recovery/restored/
f49c5b3 fix+feat: TZ-LIQ-FIX-BINANCE + TZ-LIQ-INGESTION-90D
92d34b7 audit: TZ-CHECK-EXISTING-LIQUIDATION-DATA market data feeds inventory
fd003ff fix: TZ-RECONCILE-01-METHODOLOGY-FIX 4 issues + re-run
bedb317 feat: TZ-SIGNAL-GENERATOR-INTEGRATION orchestrator for /advise v2
5ffa3db feat: TZ-LAYER-2-3-SIGNAL-GENERATOR ban filter + recommendation builder
015ed90 feat: TZ-SETUP-MATCHER pattern matching layer 1 of signal generator
38c36ea test: TZ-RECONCILE-01-RETRY backtest engine reconciliation on 8 production bots
7bdb118 feat: TZ-ADD-BOT-PARAMS-TO-STATE bot config from GinArea API
952a162 feat: TZ-TREND-HANDLING-CORE pure function for trend_handling block
```

---

## Open TZs to run in new session

### Priority order

1. **Resolve pending operator decisions** (DECISION 1-3 выше)
2. **TZ-FLAKY-TESTS-PROTECTION-ALERTS** — ~30 min Code (deferred, safe to run anytime)
3. **TZ-CASCADE-DECISION** — close as non-issue, update ROADMAP (~15 min)
4. **TZ-CALIBRATE-VS-GINAREA** — нарезать только после DECISION 1+2 от operator
5. **Phase 1 monitoring** — paper journal running, no immediate coding TZ

### Note: TZ-PAPER-JOURNAL-LIVE — DONE

Этот TZ был указан как следующий для новой сессии, но был выполнен
в конце текущей сессии (commit `ef74db7`). Повторная реализация
не нужна. Проверить можно:
```
git show ef74db7 --stat
ls services/advise_v2/paper_journal.py
python -m pytest tests/services/advise_v2/test_paper_journal.py -v
```
Все 16 тестов green. app_runner.py содержит `paper_journal_task` как 8-й asyncio task.

### TZ-FLAKY-TESTS-PROTECTION-ALERTS (следующий для Code)

```
ЦЕЛЬ: стабилизировать test_protection_alerts.py (12 flaky tests)
ПРОБЛЕМА: 1-2 failures каждый полный suite run, 0 failures в
  изоляции. Order-dependent. Pre-existing, не наши.
РАЗРЕШЁННЫЕ ФАЙЛЫ:
  - tests/test_protection_alerts.py (read + edit)
  - services/protection_alerts.py (read only)
ЗАПРЕЩЁННЫЕ ФАЙЛЫ: все остальные
ACCEPTANCE:
  - pytest tests/test_protection_alerts.py -v → 0 failures
  - pytest tests/ -q → baseline ≥507 passed
SAFETY: только тесты, никакой production код
RUN POLICY: CODE LOCAL
Skills applied: regression_baseline_keeper
```

---

## Skills applied

- `state_first_protocol` — run state_snapshot.py перед созданием handoff
- `session_handoff_protocol` — structured handoff document generation
- `encoding_safety` — UTF-8 файл через Write tool
- `regression_baseline_keeper` — регрессия не нарушена (196+1 services + 507+ full)
- `operator_role_boundary` — decisions в секции для operator, не директивы
- `untracked_protection` — только docs/ new files, tracked
