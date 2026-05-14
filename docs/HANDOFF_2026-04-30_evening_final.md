# HANDOFF 2026-04-30 evening (final)

**Session:** 2026-04-30 ~19:00 → 2026-05-01 ~08:30 UTC  
**Commits:** a04ceaf → eb2e1c7 (7 commits)  
**Tests:** 773 → 835 green (+62), 14 failed (all pre-existing test_protection_alerts)

---

## 🏁 Что построено за сессию

| TZ | Commit | Artifact |
|---|---|---|
| TZ-DECISION-LOG-SILENT-MODE | 44337da | DecisionLogAlertWorker silent_mode=True; ADVISE_V2_SPEC |
| TZ-SETUP-DETECTOR-LIVE | a04ceaf | services/setup_detector/ — models, indicators, 4 detector types, storage, loop (5min) |
| TZ-SETUP-TRACKER-OUTCOMES | a04ceaf | outcomes.py, tracker.py (60s), stats_aggregator.py |
| TZ-SETUP-HISTORICAL-BACKTEST | a04ceaf | services/setup_backtest/ — HistoricalContextBuilder, replay_engine, outcome_simulator; tools/run_setup_backtest.py |
| TZ-SETUP-BACKTEST-CSV-LOADER-FIX | 7da07a2 | Fix: Unix-ms ts column → DatetimeIndex; 3 regression tests |
| TZ-SETUP-BACKTEST-OUTCOME-FIX | 670df98 | Fix: detected_at = datetime.now() → historical ts в replay; O(log n) .loc; stop-before-TP worst-case |
| TZ-FILTER-LOSING-COMBOS-IN-LIVE | bd39989 | combo_filter.py: 2-way (type×regime) BLOCK/ALLOW table |
| TZ-COMBO-FILTER-STRENGTH | eb2e1c7 | 4-layer filter: exempt → strength≥9 → 2-way → 3-way session |

---

## 📊 Year backtest BTCUSDT 2025-05-01..2026-04-29

**18,712 setups detected** (после outcome fix)

### По strength
| strength | setups | WR | PnL/yr |
|---|---|---|---|
| 7 | 1,149 | 49.1% | +$2,449 |
| **8** | 10,368 | 24.6% | **+$384** ← noise |
| **9** | 7,195 | 38.4% | **+$17,404** ← 86% PnL |

→ MIN_ALLOWED_STRENGTH = 9 в combo_filter

### Profitable combos (ALLOW)
| combo | WR | PnL/yr |
|---|---|---|
| LONG_PDL_BOUNCE × trend_down | 53.4% | +$5,165 |
| LONG_DUMP_REVERSAL × trend_down | 30.8% | +$8,851 |
| SHORT_PDH_REJECTION × trend_up | 41.8% | +$2,831 |
| SHORT_RALLY_FADE × trend_up | 28.5% | +$2,675 |
| LONG_PDL_BOUNCE × consolidation | 32.3% | +$995 |
| SHORT_PDH_REJECTION × consolidation | 28.8% | +$246 |

### Losing combos (BLOCK)
| combo | WR | PnL/yr |
|---|---|---|
| LONG_DUMP_REVERSAL × consolidation | 19.9% | -$5,282 |
| SHORT_RALLY_FADE × consolidation | 17.9% | -$5,493 |
| SHORT_OVERBOUGHT_FADE × trend_up | 14.9% | -$1,637 |
| LONG_OVERSOLD_RECLAIM × trend_down | 17.6% | -$1,153 |
| SHORT_RALLY_FADE × trend_down | 32.3% | -$309 |
| LONG_DUMP_REVERSAL × trend_up | 29.0% | -$234 |

### 3-way session blocks
| combo | PnL/yr |
|---|---|
| LONG_DUMP_REVERSAL × trend_down × NY_LUNCH | -$1,033 |
| LONG_DUMP_REVERSAL × trend_down × NY_AM | -$886 |
| SHORT_PDH_REJECTION × consolidation × LONDON | -$812 |

**Best filter (strength=9 + no consolidation):** 4,495 setups, 43.1% WR, +$16,163, $11.30/fill

---

## 🔄 Live setup_detector filter (4 layers)

```python
# services/setup_detector/combo_filter.py
# Layer 1: GRID_* и DEFENSIVE_* → always ALLOW (exempt)
# Layer 2: strength < 9 → BLOCK ("low_strength:8<9")
# Layer 3: (type × regime) → COMBO_FILTER 2-way table
# Layer 4: (type × regime × session) → THREE_WAY_BLOCKS
```

Expected live: 3–4× меньше Telegram cards, все strength=9 + profitable combo + good session. ~10-20 cards/day.

---

## 📋 Open backlog (priority order)

### КРИТИЧЕСКИЕ (next session)
1. **TZ-REGIME-RED-GREEN-FORMALIZATION** — главная архитектурная ось следующих 1-2 недель
2. **TZ-ICT-SESSION-LEVELS-DETECTION** — gap в setup detector (бот не видит уровней которые видит operator)

### Среднеприоритетные
3. TZ-OUTCOME-SIMULATOR-GRID-ACTION-HANDLER (Bug A: grid_booster 0 fills)
4. TZ-ORDER-BLOCKS-DETECTION (после ICT levels)
5. TZ-PHASE-3-LONG-SIGN-LIFECYCLE-INVESTIGATION

### Низкоприоритетные
6. TZ-DEBT-PERF-OUTCOME-SIMULATOR (10× backtest speedup — mask → .loc для replay)
7. TZ-FLAKY-TESTS-PROTECTION-ALERTS (14 flaky tests, известный)
8. TZ-CALIBRATE-VS-GINAREA (ждёт GinArea backtest скрины)

---

## ❓ Decisions awaiting operator

- **D-A:** docs/CANON/* → archive в docs/archive/ (сейчас или отдельным TZ?)
- **D-B:** decision_log silent_mode=True → keep или selectively re-enable?
- **D-C:** services/dashboard/ → deploy в app_runner сейчас или после Phase 1?

---

## 🔧 Architectural rules (не нарушать!)

### Three-file rule
Source of truth = MASTER.md + PLAYBOOK.md + SESSION_LOG.md.  
НЕ создавать новые .md для повторяющихся концепций.

### Project inventory FIRST
Перед любым TZ для нового модуля:
1. grep по services/ src/ tests/ на keywords
2. Прочитать docs/MASTER.md статус (§11, §12)
3. Если есть похожий модуль → READ first, decide modify/extend/keep separate

INC-013 + INC-014 (architectural amnesia) случались 30.04. Не повторять.

### Trader-first filter
Каждый TZ должен:
(a) приближать к real trade с лучшим risk profile  
(b) тестировать hypothesis на real data  
(c) защищать капитал от bugs

### Visual feedback приоритет
Screenshots (RED/GREEN boxes, ICT killzones, MSB-OB) дают больше понимания за 1 день чем недели описаний. Приветствуй скрины, проси если нужен контекст рынка.

---

## 💬 Onboarding instruction для нового чата

> Это продолжение проекта Grid Orchestrator. Прочти через Code:
> 1. docs/HANDOFF_2026-04-30_evening_final.md полностью
> 2. docs/MASTER.md §16 (trading profile)
> 3. docs/OPPORTUNITY_MAP_v1.md
> 4. .claude/PROJECT_RULES.md + .claude/skills/*.md
>
> После прочтения подтверди в 5 строках:
> 1. Главная цель проекта
> 2. Что построено в session 30.04
> 3. Year backtest BTCUSDT — главные числа (PnL, WR, лучший combo)
> 4. Текущий filter в setup_detector_loop — что делает
> 5. Что считаешь next critical TZ из backlog
>
> Не задавай мне описать стратегию — всё в §16 + этот handoff.
> Перед любым TZ для нового модуля → grep + project_inventory_first.
> Приветствуй мои screenshots — они дают больше понимания чем слова.
