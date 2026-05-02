# STATE CURRENT — Grid Orchestrator
# Последнее обновление: 2026-05-02 (конец дня)
# НАЗНАЧЕНИЕ: Текущее состояние проекта. Обновляется в конце каждой сессии.
# Формат: обновляй секции §1-§5, добавляй в §6 Changelog строку.

---

## §1 PHASE STATUS

| Фаза | Название | Статус | Прогресс |
|---|---|---|---|
| 0 | Infrastructure | 🔄 in_progress | Долги классифицированы, DEBT-04 split plan готов |
| 0.5 | Engine validation | 🔄 in_progress | Combo-stop fixed, reconcile blocked на 1s OHLCV |
| 1 | Paper Journal | 🔄 in_progress | Day 4/14, 6 advise signals |
| 2 | Operator Augmentation | ⬜ planned | — |
| 3 | Tactical Bot Management | ⬜ planned | — |
| 4 | Full Auto | ⬜ planned | — |

**Текущий фокус:** Phase 0.5 unblock (1s OHLCV) + Phase 1 продолжение (paper journal 14 дней)

---

## §2 ПОСЛЕДНИЕ RESULTS (что нового относительно прошлой сессии)

### Completed 2026-05-02

| TZ | Результат |
|---|---|
| TZ-PROJECT-STATE-AUDIT | 7-вопросный audit → 3 operator actions (TZ-051, BT, TZ-067) |
| TZ-CLAUDE-TZ-VALIDATOR | CLI `tools/validate_tz.py` — фазовый валидатор, 20 тестов |
| TZ-VERIFY-INDICATOR-GATE-MECHANICS | Case B confirmed — engine_v2 уже корректен |
| TZ-DIAGNOSE-TRACKER-FALSE-NEGATIVE | Fixed: stale PID + cmdline fallback, 7 тестов |
| TZ-FIX-COMBO-STOP-GEOMETRY | Case A confirmed — entry_floor guard уже применён (K fix) |
| TZ-DEDUP-SNAPSHOTS-CSV | 45k дублей удалены, decisions 71→86, idempotent write |
| TZ-CONTEXT-HANDOFF-SKILL | ✅ DONE — docs/CONTEXT/ + tools/handoff.py + skill + 6 тестов |
| TZ-COORDINATED-GRID-TRIM-DETAILS | ✅ DONE — 1039 trim событий, playbook rule для оператора |
| TZ-HANDOFF-FIX-INCLUDE-FULL-SKILLS-AND-GAPS | ✅ DONE — PART 5 (16 скилов) + PART 6 (gaps) в handoff; 7-строчный onboarding |

### Completed 2026-04-30 → 2026-05-01 (предыдущая сессия)

| TZ | Результат |
|---|---|
| TZ-CALIBRATION-LONG-EXTEND | K_LONG = 4.275, CV=24.9% (TD-dependent, structural) |
| TZ-RESEARCH-COORDINATED-GRID | Best: $37,769/year, 20 configs |
| TZ-RECALIBRATE-CODEX-SIM-RESULTS | V1/V2/V3 findings все CONFIRMED |
| TZ-ICT-LEVELS-INTEGRATE-DETECTOR | ICT context в setup_detector |
| TZ-KLOD-IMPULSE-GRID-SEARCH | 96-combo trigger param search |

---

## §3 CALIBRATION NUMBERS (актуальные)

| Метрика | Значение | Статус |
|---|---|---|
| K_SHORT | 9.637 | ✅ STABLE (CV 3.0%, n=6) |
| K_LONG | 4.275 | ⚠️ TD-DEPENDENT (CV 24.9%, n=6) |
| Coordinated grid best | $37,769/year | 🔬 1 year, needs multi-year |
| Decisions (operator_journal) | 86 | ✅ clean data после dedup |
| Setup detector WR (strength=9) | 43.1%, +$16,163 | 1y BTCUSDT |
| LONG ground truth | −0.5 BTC/year | 6 GinArea backtests |
| SHORT ground truth | +$31k..+$50k/year | 6 GinArea backtests |

---

## §4 OPEN TZs & BLOCKERS

### Высокий приоритет (Phase 0.5 unblock)

| ID | Задача | Блокер |
|---|---|---|
| TZ-ENGINE-FIX-RESOLUTION | Reconcile v3: 1s OHLCV resolution | **Оператор: загрузить 1s OHLCV** |
| TZ-ENGINE-FIX-INSTOP-SEMANTICS-B | Проверить instop direction для LONG | Оператор: подтвердить Semant A или B |

### Phase 1 (paper journal продолжение)

| ID | Задача | Статус |
|---|---|---|
| Paper journal 14 дней | День ~3/14 | 🔄 running |
| TZ-WEEKLY-COMPARISON-REPORT | Ждёт ~7 дней данных | 🕐 pending |
| H10 backtest overnight | Запустить скрипт | Оператор: `scripts/run_backtest_h10_overnight.bat` |

### Infrastructure debt

| ID | Задача | Приоритет |
|---|---|---|
| DEBT-04 | 91 collection errors | P1 — FIX-BEFORE-PHASE-2 |
| DEBT-04-A..E | Split plan готов | 📋 backlog |
| Windows PID lock race | tracker.py | P3 — DEBT (next restart deploy) |

### Заблокировано на backtest results

TZ-057 (H10 dedup), TZ-065 (H10 live), TZ-066 (H10 calibration) — ждут overnight backtest.

---

## §5 OPERATOR PENDING ACTIONS

| Действие | Файл/команда | Оценка |
|---|---|---|
| Загрузить 1s OHLCV (BTC+XRP) | `scripts/ohlcv_ingest.py --resolution 1s` | 15 мин |
| Запустить H10 overnight backtest | `scripts/run_backtest_h10_overnight.bat` | 5 мин (overnight) |
| Подтвердить деплой idempotent write в tracker | При следующем restart tracker | 2 мин |

---

## §6 CHANGELOG (date → что изменилось)

```
2026-05-02 | TZ-HANDOFF-FIX: PART 5 (16 skills) + PART 6 (gaps) + 7-line onboarding в handoff generator
2026-05-02 | TZ-COORDINATED-GRID-TRIM-DETAILS: 1039 trim events, playbook rule, trim_analyzer.py
2026-05-02 | TZ-CONTEXT-HANDOFF-SKILL: docs/CONTEXT/ layer + tools/handoff.py CLI + Telegram /handoff
2026-05-02 | TZ-DEDUP: snapshots.csv dedup 160k→115k строк
2026-05-02 | TZ-DIAGNOSE-TRACKER: PID fallback + cmdline_must_contain fix
2026-05-02 | TZ-FIX-COMBO-STOP: K=-0.99 root cause documented, entry_floor уже applied
2026-05-02 | TZ-VERIFY-INDICATOR: engine_v2 indicator gate CORRECT (no fix needed)
2026-05-02 | decisions.parquet rebuild: 71 → 86 decisions на clean data
2026-05-01 | TZ-CALIBRATION-LONG-EXTEND: K_LONG=4.275, CV=24.9% TD-dependent confirmed
2026-05-01 | TZ-RESEARCH-COORDINATED-GRID: $37,769/year coordinated grid best result
2026-04-30 | Combo-stop B1+A1 fix: entry_floor/entry_cap guards в group.py
2026-04-30 | setup_detector 4-layer combo filter deployed
2026-04-30 | H10 detector rebuilt: C1/C2 params confirmed, 5/5 GT
2026-04-30 | Paper journal started (Day 1)
```
