# PENDING TZ — открытые задачи
# Обновлять при открытии/закрытии TZ.
# Формат: ID | Описание | Приоритет | Статус | Блокер
# Последнее обновление: 2026-05-05 EOD (week 2 close)

---

## NEXT WEEK (week 3, 2026-05-06 → 2026-05-12) — Production K recalibration + clean A/B backtests + dedup expansion

### Priority 1 — Audit-driven backtests + recalibrations (closes Findings A confounding + K trustworthiness)
| ID | Описание | Статус | Блокер |
|----|----------|--------|--------|
| TZ-TRANSITION-MODE-COMPARE-BACKTEST | Operator-side GinArea backtest of 3 candidate TRANSITION_MODE policies (closes P8 §9 Q2) | OPEN | operator GinArea run |
| TZ-PURE-INDICATOR-AB-ISOLATION | Operator-side: BT-014..017 *without* indicator on 86-day window — isolates Finding A from confounded variables (order_count, max_stop, instop) | OPEN | operator GinArea run |
| TZ-K-RECALIBRATE-PRODUCTION-CONFIGS | Re-run direct_k with live configs (size 0.001 BTC / $100, count 200/220, indicator+instop where applicable). Closes audit rows 1-6. | OPEN | — (script ready) |

### Priority 2 — Dedup wrapper expansion (after 24h monitoring)
| ID | Описание | Статус | Блокер |
|----|----------|--------|--------|
| TZ-DEDUP-WIRE-PNL_EVENT | Wire DedupLayer for PNL_EVENT type after threshold tune $200 → $400-500 | OPEN | 24h BOUNDARY_BREACH monitoring confirmed |
| TZ-DEDUP-WIRE-PNL_EXTREME | Wire DedupLayer for PNL_EXTREME after PNL_EVENT validated | OPEN | TZ-DEDUP-WIRE-PNL_EVENT |

### Priority 3 — Audit follow-ups + technical debt
| ID | Описание | Статус | Блокер |
|----|----------|--------|--------|
| TZ-CSV-CONSUMERS-AUDIT | Finding 1 follow-up: audit other consumers of `ginarea_live/snapshots.csv` for the legacy `.0` bot_id issue (decision_log/event_detector + scripts) | OPEN | — |
| TZ-FIX-COLLECTION-ERRORS | 4 broken test files surfaced by full-suite run + brittle datetime test cleanup | OPEN | — |
| TZ-SELF-REGULATING-BOT-RESEARCH | Operator side-idea track (separate from coordinator implementation) | OPEN | operator-defined scope |
| TZ-DASHBOARD-CONTENT-VALIDATION | Low priority — content correctness checks beyond mtime-based freshness | OPEN | — |
| TZ-IMPULSE-RECALIBRATE | KLOD impulse trigger 0 firings/week — re-tune or remove from P8 catalog (Q3 in coordinator design) | OPEN | operator decision |

### Deferred
| ID | Описание | Note |
|----|----------|------|
| TZ-WYCKOFF-CLASSIFIER-IMPROVE | Improve regime_24h classifier (pattern_24h может быть лучше pattern_5m) | low priority — dataset уже useful |
| TZ-OB-MSB-TIER-3 | Order block / MSB Tier-3 features | research |
| TZ-XRP-OOS-STRESS | OOS validation на XRP после 1s download | gated на operator XRP backfill |
| TZ-HEATMAP-OPERATOR-OVERRIDE | Operator override input для heatmaps | next-week or later |
| TZ-VIRTUAL-TRADER-VALIDATE | Time-gated review virtual trader stats | после 2-4 недель накопления |

### P6 — Tooling / infrastructure debt (low-priority chores)
| ID | Описание | Статус | Блокер |
|----|----------|--------|--------|
| TZ-MORNING-BRIEF-MULTITRACK-ADAPT | Fix `scripts/main_morning_brief.py` для multi-track roadmap input (currently emits empty template after WEEK_*.md → ROADMAP migration). Spec: `docs/TZs/TZ-MORNING-BRIEF-MULTITRACK-ADAPT.md` | OPEN | — |

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

### Week 2 close — 2026-05-05 (16 CPs)

| ID | CP | Результат |
|----|-----|-----------|
| TZ-RGE-RESEARCH-EXPANSION | CP15-17 | 5×3 expansion variant matrix, 0.9s; B variant DP-001-visible; D variant only one differing in RANGE |
| TZ-LONG-TP-SWEEP | CP18 | 5 TP × 4 windows; net PnL monotonic with TP ($564→$1,476); MARKUP cells flagged as discontinuous-bars artifact |
| TZ-BACKTEST-AUDIT | CP19 | Trust map: 7 ⚠️ partial / 1 ❌ default / 2 ✅ signal-side; coord grid $37k overstated ~10× |
| TZ-BACKTEST-DATA-CONSOLIDATION | CP20 | 17 GinArea backtests structured BT-001..017; 13 clean A/B + 4 confounded |
| TZ-REGIME-CLASSIFIER-PERIODS-ANALYSIS | CP21 | 1y stats: RANGE 72%, ZERO direct trend↔trend transitions, 645 episodes |
| TZ-DEDUP-DRY-RUN-PRODUCTION-LOG | CP22 | 4-day decision_log: BOUNDARY 95% TOO AGGRESSIVE, POSITION_CHANGE 10.6% HEALTHY |
| TZ-DASHBOARD-LIVE-FRESHNESS | CP23 | 60s loop + 3-tier freshness layer + corruption regression test |
| TZ-REGIME-OVERLAY | CP24 | BT × regime PnL allocation table (96-99% coverage) |
| TZ-CP28-JOINT-FINDINGS | CP28 | Findings A/B/C operator+MAIN consolidated |
| TZ-K-DUAL-MODE-COORDINATOR-DESIGN | CP30 | docs/DESIGN/P8_DUAL_MODE_COORDINATOR_v0_1.md (12 sections, 5 op questions) |
| TZ-CROSS-CHECK-FINDING-A | CP31 | Verdict A: sign-flip survives period correction (~0.40 BTC swing on 86-day window) |
| TZ-DASHBOARD-POSITION-DEDUP | CP32 / CP-Y | Bot_id `.0` legacy suffix dedup; shorts.total_btc -2.241 → -1.296 (matches operator) |
| TZ-DEDUP-WIRE-PRODUCTION (POSITION_CHANGE) | CP-G | DedupLayer wired in DecisionLogAlertWorker; 12 tests; 24h monitoring required |
| TZ-DEDUP-WIRE-BOUNDARY_BREACH | CP-G2 | Cluster-collapse for BOUNDARY_BREACH; 10 tests |
| TZ-DASHBOARD-FRESHNESS-FINALIZE | CP-H | D77 closed: snapshots.csv accepted as v1 source; README Data flow added |
| TZ-MORNING-BRIEF-MULTITRACK-ADAPT | (P6) | --roadmap mode + 14 tests |
| TZ-BOT-ALIAS-HYGIENE | (P6) | bot_registry stable UIDs + migration script + 20 tests |
| TZ-METRICS-RENDER-FIX | (P7) | mobile-safe visuals (MAX_LINE_WIDTH=28) + canonical metrics_block + 14 tests |
| TZ-ALERT-DEDUP-LAYER | (P7) | services/telegram/dedup_layer.py + 17 tests |
| TZ-SETUP-DETECTION-WIRE | (P1) | services/market_forward_analysis/setup_bridge.py + 20 tests |
| TZ-SIZING-MULTIPLIER-ENGINE | (P1) | services/sizing/* v0.1 rule-based + 31 tests |
| TZ-DIRECTION-AWARE-WORKFLOW | (P1) | apply_direction_workflow() post-clamp layer + 12 tests |
| TZ-DASHBOARD-PHASE-1 | (P4) | Wire forecast/regime/virtual_trader → state_builder + 16 tests |
| TZ-BOT-STATE-INVENTORY | (P2) | docs/STATE/BOT_INVENTORY.md — 22 bots + P8 role gaps |
| TZ-RGE-RANGE-DETECTION | (P8) | docs/DESIGN/P8_RANGE_DETECTION_v0_1.md — Method D Hybrid recommended |
| TZ-TELEGRAM-INVENTORY | (P7) | docs/STATE/TELEGRAM_EMITTERS_INVENTORY.md — 18 emitters mapped |

### Earlier closed entries

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
