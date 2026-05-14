# STATE CURRENT — Grid Orchestrator
# Последнее обновление: 2026-05-05 EOD (week 2 close)
# НАЗНАЧЕНИЕ: Текущее состояние проекта. Обновляется в конце каждой сессии.
# Формат: обновляй секции §1-§5, добавляй в §6 Changelog строку.

---

## §1 PHASE STATUS

| Фаза | Название | Статус | Прогресс |
|---|---|---|---|
| 0 | Infrastructure | 🔄 in_progress | DEBT-04 split plan готов; 4 broken test files surfaced (TZ-FIX-COLLECTION-ERRORS backlog) |
| 0.5 | Engine validation | ✅ UNBLOCKED | direct_k done; K values flagged as research-grade (TZ-K-RECALIBRATE-PRODUCTION-CONFIGS pending) |
| 1 | Paper Journal | 🔄 in_progress | Day 5/14 + forecast pipeline OPERATIONAL + sizing v0.1 + direction-aware closed |
| 2 | Operator Augmentation | 🔄 partial | P1 chain closed structurally; awaits paper-journal evidence to promote to production |
| 3 | Tactical Bot Management | 🔄 partial | P8 design (coordinator v0.1) + range detection done; impl pending Q2 backtest decision |
| 4 | Full Auto | ⬜ planned | — |

**Текущий фокус week 3:** clean-A/B GinArea backtests (TRANSITION-MODE-COMPARE + PURE-INDICATOR-AB), production K recalibration with live configs, P8 implementation decision after Q2 backtest closure.

---

## §2 ПОСЛЕДНИЕ RESULTS (что нового относительно прошлой сессии)

### Completed 2026-05-05 (week 2 — 16 CPs)

| CP | TZ | Result |
|----|-----|--------|
| CP15-17 | TZ-RGE-RESEARCH-EXPANSION | ✅ 5×3 expansion variant matrix (DISTRIBUTION skipped per anti-drift); 0.9s wall-clock; B variant DP-001-visible (PnL doubles, DD doubles); D variant only one differing in RANGE |
| CP18 | TZ-LONG-TP-SWEEP | ✅ 5 TP × 4 windows (FULL_YEAR + 3 regimes), 6.4s; net PnL monotonic with TP ($564→$1,476); MARKUP-only cells flagged as discontinuous-bars artifact |
| CP19 | TZ-BACKTEST-AUDIT | ✅ Trust map for 11 STATE §3 numbers; 7 ⚠️ partial / 1 ❌ default / 2 ✅ signal-side; coordinated grid $37k overstated ~10× as live forecast; setup detector $16k overstated ~50× |
| CP20 | TZ-BACKTEST-DATA-CONSOLIDATION | ✅ 17 GinArea backtests structured BT-001..017; 4 groups G1-G4; 13 clean A/B + 4 confounded |
| CP21 | TZ-REGIME-CLASSIFIER-PERIODS-ANALYSIS | ✅ 1y stats: MARKUP 13% / MARKDOWN 15% / RANGE 72% / DISTRIBUTION absent; 645 episodes, ZERO direct trend↔trend transitions |
| CP22 | TZ-DEDUP-DRY-RUN-PRODUCTION-LOG | ✅ 4-day decision_log replay: BOUNDARY 95% TOO AGGRESSIVE, PNL_EVENT 88% HIGH, POSITION_CHANGE 10.6% HEALTHY |
| CP23 | TZ-DASHBOARD-LIVE-FRESHNESS | ✅ 60s loop + 3-tier freshness layer + corrupted-snapshots regression test |
| CP24 | TZ-REGIME-OVERLAY | ✅ BT × regime PnL allocation table (proportional, ~96-99% coverage) |
| CP28 | TZ-CP28-JOINT-FINDINGS | ✅ Findings A/B/C consolidated by operator+MAIN |
| CP30 | TZ-K-DUAL-MODE-COORDINATOR-DESIGN | ✅ docs/DESIGN/P8_DUAL_MODE_COORDINATOR_v0_1.md (12 sections, 5 op questions, 3 phased validation, 9 v0.1 exclusions) |
| CP31 | TZ-CROSS-CHECK-FINDING-A | ✅ Verdict A: sign-flip survives period correction. ~0.40 BTC swing across 86-day window confirmed |
| CP32 | TZ-DASHBOARD-POSITION-DEDUP | ✅ Bot_id `.0` legacy suffix dedup. shorts.total_btc: −2.241 → −1.296 (matches operator reality) |
| CP-G | TZ-DEDUP-WIRE-PRODUCTION (POSITION_CHANGE) | ✅ DedupLayer wired in DecisionLogAlertWorker; flag DEDUP_LAYER_ENABLED_FOR_POSITION_CHANGE; 12 tests |
| CP-G2 | TZ-DEDUP-WIRE-BOUNDARY_BREACH | ✅ Cluster-collapse for BOUNDARY_BREACH; 10 tests; ready for 24h monitoring |
| CP-H | TZ-DASHBOARD-FRESHNESS-FINALIZE | ✅ D77 closed: snapshots.csv accepted as v1 live source; README Data flow section added |
| CP-Y | TZ-DASHBOARD-POSITION-DEDUP (final fix) | ✅ See CP32 |

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

**⚠️ Structural caveat (audit CP19, 2026-05-05):** the calibration sim does NOT model `instop` or `indicator gate` — these are ABSENT from `services/calibration/sim.py`, not just parameters set to defaults. Live GinArea bots run with both. All K-factor and grid-PnL numbers above are therefore **research-grade approximations**, valid for *structural* conclusions (DP-001 K-instability) but NOT for absolute-PnL forecasts. A production-replica sim is a separate (large) TZ. Recalibration with live configs (TZ-K-RECALIBRATE-PRODUCTION-CONFIGS) addresses parameter-mismatch but cannot fix the structural absence.

**Week 3 priorities (audit-driven):**
1. **TZ-TRANSITION-MODE-COMPARE-BACKTEST** — close P8 §9 Q2 (TRANSITION_MODE policy) with operator-side GinArea backtest of 3 candidate transition policies
2. **TZ-PURE-INDICATOR-AB-ISOLATION** — operator-side GinArea backtest of BT-014..017 *without* indicator on 86-day window (closes Finding A's confounding)
3. **TZ-K-RECALIBRATE-PRODUCTION-CONFIGS** — re-run direct_k with live configs (size 0.001 BTC / $100, order_count 200/220, indicator/instop where applicable)

---

## §4 OPEN TZs & BLOCKERS

### Week 3 priority queue (top 10, full list in PENDING_TZ.md)

| Rank | TZ | Track | Notes |
|------|-----|-------|-------|
| 1 | **TZ-TRANSITION-MODE-COMPARE-BACKTEST** | P3/P8 | Closes P8 §9 Q2 — operator-side GinArea backtest of TRANSITION policy candidates |
| 2 | **TZ-PURE-INDICATOR-AB-ISOLATION** | P3 | Operator-side: BT-014..017 without indicator, same 86-day window — isolates Finding A's confounded variables |
| 3 | **TZ-K-RECALIBRATE-PRODUCTION-CONFIGS** | P3 | Re-run direct_k with live configs (size 0.001 BTC / $100, count 200/220) — closes audit row 1-6 |
| 4 | TZ-DEDUP-WIRE-PNL_EVENT | P3 | After 24h BOUNDARY_BREACH monitoring confirms; threshold tune $200→$400-500 first |
| 5 | TZ-DEDUP-WIRE-PNL_EXTREME | P3 | After PNL_EVENT |
| 6 | TZ-CSV-CONSUMERS-AUDIT | P3 | Finding 1 follow-up: other consumers of snapshots.csv with `.0` issue |
| 7 | TZ-FIX-COLLECTION-ERRORS | P3 | 4 broken test files surfaced by full-suite run; brittle datetime test |
| 8 | TZ-SELF-REGULATING-BOT-RESEARCH | P3 | Operator side-idea (separate track from coordinator) |
| 9 | TZ-DASHBOARD-CONTENT-VALIDATION | P3 | Low priority — content correctness checks beyond freshness |
| 10 | TZ-IMPULSE-RECALIBRATE | P4 | Contingent on operator decision: KLOD impulse trigger 0 firings/week — re-tune or remove from catalog |

### Closed week 2 (sequential)

P1 chain ✅ (3/3 TZs): SETUP-DETECTION-WIRE / SIZING-MULTIPLIER-ENGINE / DIRECTION-AWARE-WORKFLOW
P2 ✅ BOT-STATE-INVENTORY (others deferred per P8 supersedence)
P4 ✅ DASHBOARD-PHASE-1 + PHASE-1.5 (live freshness); PHASE-2/3 deferred
P6 ✅ MORNING-BRIEF-MULTITRACK + BOT-ALIAS-HYGIENE
P7 ✅ TELEGRAM-INVENTORY + ALERT-DEDUP-LAYER + 2 emitters wired (POSITION_CHANGE, BOUNDARY_BREACH)
P8 ✅ RANGE-DETECTION + DUAL-MODE-COORDINATOR-DESIGN; impl pending Q2 backtest decision

### Остаточный engine blocker

| ID | Задача | Блокер |
|---|---|---|
| TZ-ENGINE-FIX-INSTOP-SEMANTICS-B | Проверить instop direction для LONG | Оператор: подтвердить Semant A или B |

### Остаточный engine blocker

| ID | Задача | Блокер |
|---|---|---|
| TZ-ENGINE-FIX-INSTOP-SEMANTICS-B | Проверить instop direction для LONG | Оператор: подтвердить Semant A или B |

### Phase 1 (paper journal продолжение)

| ID | Задача | Статус |
|---|---|---|
| Paper journal 14 дней | Day 5/14 | 🔄 running |
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
| **24h monitoring: POSITION_CHANGE + BOUNDARY_BREACH dedup wrappers** | `docs/OPERATOR_DEDUP_MONITORING.md` checklist | 5 min/day x 2 days |
| Confirm sizing v0.1 frozen params (Q1-Q5 closed) — если intuitions changed | `docs/DESIGN/SIZING_MULTIPLIER_v0_1.md` "Decisions" | 10 min review |
| Answer P8 coordinator §9 questions (Q1-Q5 partial) | `docs/DESIGN/P8_DUAL_MODE_COORDINATOR_v0_1.md` | 15 min |
| Operator-side GinArea backtest: TRANSITION-MODE-COMPARE | new GinArea run | overnight |
| Operator-side GinArea backtest: PURE-INDICATOR-AB-ISOLATION (BT-014..017 без indicator) | new GinArea run | overnight |
| Подтвердить Semant A или B для LONG instop | TZ-ENGINE-FIX-INSTOP-SEMANTICS-B | 5 мин |
| Загрузить XRP 1s OHLCV (опционально) | `python scripts/ohlcv_ingest.py --symbol XRPUSDT --interval 1s --start-date 2025-05-01T00:00:00Z --target-end 2026-04-30T23:59:59Z --workers 4` | 3-6h overnight |
| Запустить H10 overnight backtest | `scripts/run_backtest_h10_overnight.bat` | overnight |

---

## §6 CHANGELOG (date → что изменилось)

```
2026-05-05 | Session close — 16 CPs (CP15-17 expansion, CP18 LONG TP sweep, CP19 audit, CP20 backtest registry, CP21 regime periods, CP22 dedup dry-run, CP23 dashboard freshness, CP24 regime overlay, CP28 joint findings, CP30 P8 coordinator design, CP31 cross-check Finding A, CP32 position dedup fix, CP-G/G2 dedup wire production POSITION_CHANGE+BOUNDARY_BREACH, CP-H freshness finalize, CP-Y position dedup final)
2026-05-05 | Production wire-ups: POSITION_CHANGE dedup (10.6% suppression) + BOUNDARY_BREACH cluster-collapse — 24h monitoring required
2026-05-05 | Dashboard position dedup fixed: shorts.total_btc -2.241→-1.296 (matches operator reality); _normalize_bot_id strips legacy `.0` suffix
2026-05-05 | DRIFT-016..022 logged (7 incidents) + META-PATTERN updated
2026-05-05 | Anti-finding A confounded: cross-check confirmed sign-flip but flagged 4 confounded variables; PURE-INDICATOR-AB-ISOLATION queued
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
