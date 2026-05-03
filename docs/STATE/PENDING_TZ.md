# PENDING TZ — открытые задачи
# Обновлять при открытии/закрытии TZ.
# Формат: ID | Описание | Приоритет | Статус | Блокер
# Последнее обновление: 2026-05-03 EOD

---

## THIS WEEK (2026-05-04 → 2026-05-10) — Forecast system full build

| ID | Описание | День | Статус | Блокер |
|----|----------|------|--------|--------|
| TZ-FORECAST-QUALITATIVE-DEPLOY | Live Telegram briefs 4×day + watch-for triggers | Mon | OPEN | — |
| TZ-FORECAST-REGIME-SPLIT | Data pipeline per-regime split (foundation) | Mon | OPEN | TZ-FORECAST-QUALITATIVE-DEPLOY |
| TZ-REGIME-MODEL-MARKUP | MARKUP model: trend continuation, Brier ≤0.22 | Tue | OPEN | regime split done |
| TZ-REGIME-MODEL-MARKDOWN | MARKDOWN model: bear features, Brier ≤0.22 | Wed | OPEN | regime split done |
| TZ-REGIME-MODEL-RANGE | RANGE model: mean reversion | Thu | OPEN | regime split done |
| TZ-REGIME-MODEL-DISTRIBUTION | DISTRIBUTION model: contrarian | Thu | OPEN | TZ-REGIME-MODEL-RANGE |
| TZ-REGIME-AUTO-SWITCH | Auto-switching engine + hysteresis | Fri | OPEN | all regime models |
| TZ-REGIME-OOS-VALIDATE | Out-of-sample validation on bear/range episodes | Sat | OPEN | auto-switch done |
| TZ-REGIME-SELFMONITOR | Live Brier tracking + calibration deg alert | Sun | OPEN | OOS GO |
| TZ-REGIME-DOCS-TESTS | ≥30 tests + documentation | Sun | OPEN | TZ-REGIME-SELFMONITOR |

**Week success gate:** All 4 regime models Brier ≤0.22 + auto-switch + OOS passed
**Failure rule:** Regime failing 0.28 hard stop → ship that regime as qualitative only. No timeline extension.

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
| TZ-FINAL-HANDOFF-2026-05-03 | 2026-05-03 | ✅ DONE — WEEK plan expanded, MAIN prompt ready, handoff complete |
| TZ-MAIN-COORDINATOR-INFRASTRUCTURE | 2026-05-03 | ✅ DONE — 12 deliverables, 29 tests |
| TZ-MARKET-FORECAST-QUALITY-UPGRADE (ETAP 1-3) | 2026-05-03 | ✅ COMPLETED PARTIAL — CP3 reached, ceiling documented; ETAPs 4-7 superseded by WEEK plan (Variant C) |
| TZ-FIX-EXISTING-TELEGRAM-ALERTS | 2026-05-03 | ✅ DONE — stale filter, enriched format, 20 tests |
| TZ-MARKET-FORWARD-ANALYSIS | 2026-05-03 | ✅ DONE — 45 tests green |
| TZ-CONTEXT-HANDOFF-SKILL | 2026-05-02 | ✅ DONE |
| TZ-DEDUP-SNAPSHOTS-CSV | 2026-05-02 | ✅ DONE |
| TZ-DIAGNOSE-TRACKER-FALSE-NEGATIVE | 2026-05-02 | ✅ DONE |
| TZ-FIX-COMBO-STOP-GEOMETRY | 2026-05-02 | ✅ DONE |
| TZ-VERIFY-INDICATOR-GATE-MECHANICS | 2026-05-02 | ✅ DONE |
| TZ-CLAUDE-TZ-VALIDATOR | 2026-05-02 | ✅ DONE |
| TZ-PROJECT-STATE-AUDIT | 2026-05-02 | ✅ DONE |
