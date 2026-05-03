# PENDING TZ — открытые задачи
# Обновлять при открытии/закрытии TZ.
# Формат: ID | Описание | Приоритет | Статус | Блокер
# Последнее обновление: 2026-05-03

---

## Phase 0.5 — Engine validation

| ID | Описание | Приоритет | Статус | Блокер |
|----|----------|-----------|--------|--------|
| TZ-ENGINE-FIX-RESOLUTION | Reconcile v3: 1s OHLCV resolution | P0 | BLOCKED | Оператор: загрузить 1s OHLCV |

---

## Phase 1 — Paper journal

| ID | Описание | Приоритет | Статус | Блокер |
|----|----------|-----------|--------|--------|
| Paper journal 14 дней | День 4/14 | P1 | IN_PROGRESS | — |
| TZ-WEEKLY-COMPARISON-REPORT | Week 1 paper vs operator actions | P1 | PENDING | ≥7 дней данных |
| H10 overnight backtest | `scripts/run_backtest_h10_overnight.bat` | P1 | PENDING | Оператор: запустить |

---

## Phase 0 — Infrastructure debt

| ID | Описание | Приоритет | Статус | Блокер |
|----|----------|-----------|--------|--------|
| DEBT-04-A | Collection errors subset A (high-frequency) | P1 | OPEN | — |
| DEBT-04-B | Collection errors subset B | P1 | OPEN | DEBT-04-A |
| DEBT-04-C | Collection errors subset C | P2 | OPEN | DEBT-04-B |
| DEBT-04-D | Collection errors subset D | P2 | OPEN | DEBT-04-C |
| DEBT-04-E | Collection errors subset E | P3 | OPEN | DEBT-04-D |
| Windows PID lock race | tracker.py stale PID fix (at restart) | P3 | OPEN | next restart deploy |

---

## Forecast quality — awaiting operator decision

| ID | Описание | Приоритет | Статус | Блокер |
|----|----------|-----------|--------|--------|
| TZ-MARKET-FORECAST-QUALITY-UPGRADE (ETAPs 4-7) | GA evidence layer + output enrichment | P1 | BLOCKED | Operator GO/NO-GO at CP3 (Brier 0.257, gate 0.22-0.28) |

**CP3 decision options for operator:**
- (A) Accept ceiling → qualitative briefs only, no numeric Brier
- (B) Add trend-following features (momentum, EMA crossovers) to fix signal inversion
- (C) Other approach

---

## Blocked on backtest results

| ID | Описание | Статус |
|----|----------|--------|
| TZ-057 (H10 dedup) | PENDING — ждёт H10 overnight backtest |
| TZ-065 (H10 live) | PENDING — ждёт H10 overnight backtest |
| TZ-066 (H10 calibration) | PENDING — ждёт H10 overnight backtest |

---

## ✅ Закрытые (последние)

| ID | Дата | Результат |
|----|------|-----------|
| TZ-MAIN-COORDINATOR-INFRASTRUCTURE | 2026-05-03 | ✅ DONE — 12 deliverables, 29 tests |
| TZ-MARKET-FORECAST-QUALITY-UPGRADE (ETAP 1-3) | 2026-05-03 | ✅ DONE — CP3 gate triggered |
| TZ-FIX-EXISTING-TELEGRAM-ALERTS | 2026-05-03 | ✅ DONE — stale filter, enriched format, 20 tests |
| TZ-MARKET-FORWARD-ANALYSIS | 2026-05-03 | ✅ DONE — 45 tests green |
| TZ-CONTEXT-HANDOFF-SKILL | 2026-05-02 | ✅ DONE |
| TZ-DEDUP-SNAPSHOTS-CSV | 2026-05-02 | ✅ DONE |
| TZ-DIAGNOSE-TRACKER-FALSE-NEGATIVE | 2026-05-02 | ✅ DONE |
| TZ-FIX-COMBO-STOP-GEOMETRY | 2026-05-02 | ✅ DONE |
| TZ-VERIFY-INDICATOR-GATE-MECHANICS | 2026-05-02 | ✅ DONE |
| TZ-CLAUDE-TZ-VALIDATOR | 2026-05-02 | ✅ DONE |
| TZ-PROJECT-STATE-AUDIT | 2026-05-02 | ✅ DONE |
