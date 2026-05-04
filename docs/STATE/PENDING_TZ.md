# PENDING TZ — открытые задачи
# Обновлять при открытии/закрытии TZ.
# Формат: ID | Описание | Приоритет | Статус | Блокер
# Последнее обновление: 2026-05-04 EOD

---

## THIS WEEK (2026-05-11 → 2026-05-17) — Actionability layer + bot management

### Priority 1 — Actionability layer
| ID | Описание | Статус | Блокер |
|----|----------|--------|--------|
| TZ-SETUP-DETECTION-WIRE | Connect setup_detector to RegimeForecastSwitcher (forecast → setup gate) | OPEN | — |
| TZ-SIZING-MULTIPLIER-ENGINE | 0–2× sizing multiplier с reasoning (regime + forecast + setup confluence) | OPEN | TZ-SETUP-DETECTION-WIRE |
| TZ-DIRECTION-AWARE-WORKFLOW | Promote in MARKUP, normal flow elsewhere | OPEN | TZ-SIZING-MULTIPLIER-ENGINE |

### Priority 2 — Regime-aware bot management
| ID | Описание | Статус | Блокер |
|----|----------|--------|--------|
| TZ-BOT-STATE-INVENTORY | Что deployed, что manual, что paper | OPEN | — |
| TZ-K-TARGET-CONDITIONAL | Regression K = f(target_pct, side) на 12+ точках, посмотреть структуру outliers (target<0.25 → K boost ×1.5–2) | OPEN | direct_k results (✅ done) |
| TZ-RESEARCH-DIRS-AUDIT | countertrend / defensive / exhaustion применимость или decommission | OPEN | — |

### Priority 3 — MARKUP-1h numeric improvement
| ID | Описание | Статус | Блокер |
|----|----------|--------|--------|
| TZ-MARKUP-1H-IMPROVEMENT | Try regime-specific signal logic OR lightGBM (lightGBM требует explicit operator approval per failure rule) | OPEN | operator approval для lightGBM track |

### Priority 4 — Dashboard wire-in
| ID | Описание | Статус | Блокер |
|----|----------|--------|--------|
| TZ-DASHBOARD-PHASE-1 | Wire forecast / regime / virtual_trader → state_builder.py (3 hooks, ~30 мин) | OPEN | — |

### Deferred
| ID | Описание | Note |
|----|----------|------|
| TZ-WYCKOFF-CLASSIFIER-IMPROVE | Improve regime_24h classifier (pattern_24h может быть лучше pattern_5m) | low priority — dataset уже useful |
| TZ-OB-MSB-TIER-3 | Order block / MSB Tier-3 features | research |
| TZ-XRP-OOS-STRESS | OOS validation на XRP после 1s download | gated на operator XRP backfill |
| TZ-HEATMAP-OPERATOR-OVERRIDE | Operator override input для heatmaps | next-week or later |
| TZ-VIRTUAL-TRADER-VALIDATE | Time-gated review virtual trader stats | после 2-4 недель накопления |

---

## Phase 0.5 — Engine validation

| ID | Описание | Приоритет | Статус | Блокер |
|----|----------|-----------|--------|--------|
| ~~TZ-ENGINE-FIX-RESOLUTION~~ | ✅ DONE 2026-05-04 — direct_k via reconcile_direct_k.py | — | CLOSED | — |

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
| TZ-ENGINE-FIX-RESOLUTION | 2026-05-04 | ✅ direct_k done: K_SHORT=8.87 (CV 31.8%), K_LONG=4.13 (CV 43.1% — DP-001 confirmed) |
| TZ-DASHBOARD-DISCOVERY | 2026-05-04 | ✅ inventory + sync mechanism (snapshot JSON variant A) |
| TZ-OPERATOR-NIGHT-DOWNLOAD-PREP | 2026-05-04 | ✅ docs/OPERATOR_NIGHT_DOWNLOAD_1S_OHLCV.md |
| TZ-FINAL (week 1 close: brief + virtual trader + monitor + delivery) | 2026-05-04 | ✅ 21 tests, 55/55 total green, RU brief renders end-to-end |
| TZ-REGIME-AUTO-SWITCH | 2026-05-04 | ✅ RegimeForecastSwitcher + hysteresis + transition gating, 14 tests |
| TZ-OOS-VALIDATION | 2026-05-04 | ✅ 5 windows × 3 regimes × 3 horizons = 45 Brier points, 7/9 numeric |
| TZ-REGIME-MODEL-RANGE | 2026-05-04 | ✅ all YELLOW, most stable (CV 0.003-0.039) |
| TZ-REGIME-MODEL-MARKDOWN | 2026-05-04 | ✅ 1h GREEN 0.20, 4h YELLOW, 1d qualitative (transition contamination) |
| TZ-MARKDOWN-1D-DIAGNOSTIC | 2026-05-04 | ✅ window-specific (range 0.082), не systemic |
| TZ-REGIME-MODEL-MARKUP | 2026-05-04 | ✅ per-horizon hybrid: 1h qual / 4h num / 1d gated |
| TZ-TIER2-MARKUP | 2026-05-04 | ✅ +12 vol-profile + RSI-derivative features |
| TZ-1H-FIX (per-horizon gating) | 2026-05-04 | ✅ FAIL gate, reverted, infra param kept |
| TZ-TIER1-COMPLETE-WIRING | 2026-05-04 | ✅ ny_pm + kz_mid + bars_since decay wired into Signal D |
| TZ-TIER1-FEATURE-EXPANSION | 2026-05-04 | ✅ 22 new features, sharpness 0.037→0.064 |
| TZ-FIX-REGIME-INT-MAPPING | 2026-05-04 | ✅ feature_pipeline.py:217 mapping fix (uptrend/downtrend/sideways) |
| TZ-REGIME-MODEL-MARKUP (initial) | 2026-05-04 | ✅ 14 tests, MARKUP-biased weights |
| TZ-SESSION-CLOSE-PROPER-HANDOFF-2026-05-03 | 2026-05-03 | ✅ DONE — MAIN prompt rewritten (physical constraints), setup guide, Day 1 pre-generated |
| TZ-FINAL-HANDOFF-2026-05-03 | 2026-05-03 | ✅ SUPERSEDED by TZ-SESSION-CLOSE-PROPER-HANDOFF |
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
