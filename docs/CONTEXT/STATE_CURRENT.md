# STATE CURRENT — Grid Orchestrator
# Последнее обновление: 2026-05-04 EOD
# НАЗНАЧЕНИЕ: Текущее состояние проекта. Обновляется в конце каждой сессии.
# Формат: обновляй секции §1-§5, добавляй в §6 Changelog строку.

---

## §1 PHASE STATUS

| Фаза | Название | Статус | Прогресс |
|---|---|---|---|
| 0 | Infrastructure | 🔄 in_progress | Долги классифицированы, DEBT-04 split plan готов |
| 0.5 | Engine validation | ✅ UNBLOCKED | direct_k done on 31.5M 1s bars: K_SHORT=8.87, K_LONG=4.13 (DP-001 confirmed) |
| 1 | Paper Journal | 🔄 in_progress | Day 4/14 + forecast pipeline OPERATIONAL |
| 2 | Operator Augmentation | ⬜ planned | actionability layer next (sizing/direction-aware) |
| 3 | Tactical Bot Management | ⬜ planned | — |
| 4 | Full Auto | ⬜ planned | — |

**Текущий фокус:** week 2 — actionability layer (sizing multiplier, direction-aware workflow, setup wiring к forecast switcher)

---

## §2 ПОСЛЕДНИЕ RESULTS (что нового относительно прошлой сессии)

### Completed 2026-05-04 (full week 1 closed)

| TZ | Результат |
|---|---|
| TZ-FORECAST-QUALITATIVE-DEPLOY | ✅ Russian briefs + 3 trigger types deployed |
| TZ-FORECAST-REGIME-SPLIT | ✅ regime split foundation |
| TZ-FIX-REGIME-INT-MAPPING | ✅ emergency: feature_pipeline.py:217 mapping fix |
| TZ-DATA-INVENTORY / TZ-FEATURE-INVENTORY | ✅ discovery |
| TZ-TIER1-FEATURE-EXPANSION + COMPLETE-WIRING | ✅ 44→72 cols, Signal D/E extended |
| TZ-TIER2-MARKUP | ✅ +12 vol-profile + RSI-derivative features (84 cols) |
| TZ-MARKDOWN-1D-DIAGNOSTIC | ✅ 1d Brier 0.298 → window-specific contamination, не systemic |
| TZ-REGIME-MODEL-MARKUP | ✅ 1h qualitative, 4h numeric, 1d gated |
| TZ-REGIME-MODEL-MARKDOWN | ✅ 1h GREEN 0.20, 4h YELLOW, 1d qualitative |
| TZ-REGIME-MODEL-RANGE | ✅ all 3 horizons numeric, most stable (CV 0.003-0.039) |
| TZ-REGIME-MODEL-DISTRIBUTION | ✅ closed как априори qualitative (576 rows insufficient) |
| TZ-REGIME-OOS-VALIDATE | ✅ 7/9 numeric cells validated across 5 windows |
| TZ-REGIME-AUTO-SWITCH | ✅ RegimeForecastSwitcher + hysteresis + transition gating |
| TZ-REGIME-SELFMONITOR | ✅ live_monitor.py rolling Brier + alerts |
| TZ-REGIME-DOCS-TESTS | ✅ 55/55 tests, README documented |
| TZ-OPERATOR-NIGHT-DOWNLOAD-PREP | ✅ instructions for 1s OHLCV backfill |
| TZ-DASHBOARD-DISCOVERY | ✅ inventory + sync mechanism recommendation |
| TZ-ENGINE-FIX-RESOLUTION | ✅ resolved via reconcile_direct_k.py — K factors computed |

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
| K_SHORT (direct 1s) | 8.87 median (mean 10.16) | ⚠️ DIRECT-1S (CV 31.8%, n=6, range [7.90, 17.32]) |
| K_LONG (direct 1s) | 4.13 median (mean 4.84) | ❌ DIRECT-1S (CV 43.1%, structurally unstable — DP-001 confirmed) |
| Coordinated grid best | $37,769/year | 🔬 1 year, needs multi-year |
| Decisions (operator_journal) | 86 | ✅ clean data после dedup |
| Setup detector WR (strength=9) | 43.1%, +$16,163 | 1y BTCUSDT |
| LONG ground truth | −0.5 BTC/year | 6 GinArea backtests |
| SHORT ground truth | +$31k..+$50k/year | 6 GinArea backtests |
| **Forecast pipeline (validated CV matrix)** | | |
| MARKUP | 1h qual / 4h yel 0.259 / 1d gated 0.235 | ✅ deployed |
| MARKDOWN | 1h GREEN 0.204 / 4h yel 0.228 / 1d qual | ✅ deployed |
| RANGE | 1h yel 0.247 / 4h yel 0.248 / 1d yel 0.250 | ✅ deployed (most stable) |
| Test count (regime pipeline) | 55/55 | ✅ green |
| 1s OHLCV coverage | 31.5M bars (2025-05-01 → 2026-04-30) | ✅ 100% GA window |

---

## §4 OPEN TZs & BLOCKERS

### Week 2 priorities (see PENDING_TZ.md for full list)

**Priority 1 — Actionability layer:**
- TZ-SETUP-DETECTION-WIRE (connect setup_detector to forecast switcher)
- TZ-SIZING-MULTIPLIER-ENGINE (0–2× multiplier with reasoning)
- TZ-DIRECTION-AWARE-WORKFLOW (promote in MARKUP, normal flow elsewhere)

**Priority 2 — Regime-aware bot management:**
- TZ-BOT-STATE-INVENTORY (deployed vs manual)
- TZ-K-TARGET-CONDITIONAL (K = f(target_pct, side) regression)
- TZ-RESEARCH-DIRS-AUDIT (countertrend/defensive/exhaustion применимость)

**Priority 3 — MARKUP-1h numeric:**
- TZ-MARKUP-1H-IMPROVEMENT (regime-specific signal logic OR lightGBM — lightGBM требует operator approval)

**Priority 4 — Dashboard wire-in:**
- TZ-DASHBOARD-PHASE-1 (forecast/regime/virtual_trader → state_builder)

### Остаточный engine blocker

| ID | Задача | Блокер |
|---|---|---|
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
| Подтвердить Semant A или B для LONG instop | TZ-ENGINE-FIX-INSTOP-SEMANTICS-B | 5 мин |
| Загрузить XRP 1s OHLCV (опционально) | `python scripts/ohlcv_ingest.py --symbol XRPUSDT --interval 1s --start-date 2025-05-01T00:00:00Z --target-end 2026-04-30T23:59:59Z --workers 4` | 3-6h overnight |
| Запустить H10 overnight backtest | `scripts/run_backtest_h10_overnight.bat` | overnight |
| Подтвердить деплой idempotent write в tracker | При следующем restart tracker | 2 мин |

---

## §6 CHANGELOG (date → что изменилось)

```
2026-05-04 | TZ-ENGINE-FIX-RESOLUTION ✅ via reconcile_direct_k.py: K_SHORT=8.87, K_LONG=4.13 (DP-001 confirmed)
2026-05-04 | 1s OHLCV backfill complete: 31.5M bars covering full GA window (2025-05-01 → 2026-04-30)
2026-05-04 | Forecast pipeline OPERATIONAL: 3 regime models, 7/9 numeric cells CV-validated, switcher + virtual trader + RU briefs
2026-05-04 | regime_int mapping bug fixed (feature_pipeline.py:217), all regime splits regenerated with STAGE 0 verification
2026-05-04 | Tier-1 + Tier-2 features: 44 → 84 cols (session levels, bars_since decay, vol profile, RSI derivatives)
2026-05-04 | DRIFT-007..015 + META-PATTERN-001 logged
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
