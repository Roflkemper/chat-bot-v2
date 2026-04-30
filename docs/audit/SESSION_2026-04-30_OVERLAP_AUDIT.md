# SESSION 2026-04-30 — Overlap Audit

**Generated:** 2026-04-30  
**TZ:** TZ-OPERATOR-TRADING-PROFILE-AND-CLEANUP  
**Scope:** Артефакты session 30.04 vs existing infrastructure — классификация, решения

---

## Existing infrastructure (preserve always)

- `/advise` v2 multi-asset (BTC/ETH/XRP) — `services/advise_v2/`
- `paper_journal.py` Phase 1 (running, пишет `advise_signals.jsonl` с 28.04)
- What-If engine (TZ-022) — `src/whatif/` (runner, horizon_runner, snapshot, grid_search)
- `weekly_comparison_report` (TZ-WEEKLY-COMPARISON-REPORT) — `services/advise_v2/weekly_report.py`
- 9 skills + PROJECT_RULES — `.claude/skills/`, `.claude/PROJECT_RULES.md`
- `regime_adapter`, `setup_matcher`, `signal_generator` — `services/advise_v2/`
- `calendar.py` + `weekend_gap` (TZ-CALENDAR-REACTIVATION) — `src/features/`
- Live features writer — `src/features/pipeline.py`
- 5 supervised processes (supervisor, app_runner, tracker, collectors, watchdog)
- Auto outcome reconciliation — `services/advise_v2/action_tracker.py`
- `MASTER.md`, `PLAYBOOK.md`, `OPPORTUNITY_MAP_v1.md`, `SESSION_LOG.md`
- `GINAREA_MECHANICS.md`, `HANDOFF_*.md`
- `services/h10_detector.py`, `services/liquidity_map.py`, `services/h10_grid.py`
- `services/protection_alerts.py`, `services/telegram_runtime.py`

---

## Today's artifacts vs existing — overlap matrix

| Артефакт 30.04 | Existing equivalent | Overlap | Action |
|---|---|---|---|
| `docs/CANON/STRATEGY_CANON_2026-04-30.md` | `docs/MASTER.md` §1-§7 | **HIGH** | Merge: §1 LONG/SHORT arch → `MASTER §16`. Остальное уже в MASTER. |
| `docs/CANON/HYPOTHESES_BACKLOG.md` | ничего | LOW | **KEEP** — уникальный контент |
| `docs/CANON/OPERATOR_QUESTIONS.md` | ничего | LOW | **KEEP** — уникальный контент; интегрировать как gaps в MASTER §16.6 |
| `docs/CANON/CUSTOM_BOTS_REGISTRY.md` | `MASTER §6` (краткий) | LOW | **KEEP** — детальнее чем §6 |
| `docs/CANON/RUNNING_SERVICES_INVENTORY_2026-04-30.md` | `HANDOFF` / `STATE/` | MEDIUM | **ARCHIVE** — данные на timestamp, перенести актуальное в STATE |
| `docs/CANON/INDEX.md` | `docs/README.md` | MEDIUM | **ARCHIVE** — при наличии README дублирует; CANON/* → docs/archive/ |
| `services/decision_log/` | `services/advise_v2/paper_journal.py` | MEDIUM | **KEEP, разделить scope** — см. Action 2 |
| `services/managed_grid_sim/` | `src/whatif/` (What-If engine) | LOW-MEDIUM | **KEEP как отдельный слой** — см. Action 3 |
| `services/dashboard/` | `/advise stats` Telegram команда | LOW | **KEEP** — разные слои (visual vs text) |
| `services/adaptive_grid_manager.py` | `config/adaptive_grid.yaml` + whatif | LOW | **KEEP** — конкретный play manager |
| `services/boundary_expand_manager.py` | P-1 logic | LOW | **KEEP** — автоматизация confirmed play |
| `services/counter_long_manager.py` | P-3 logic | LOW | **KEEP** — автоматизация confirmed play |

**Примечание:** `services/liq_clusters/` — директория не создана. `/liq_set` Telegram команда запланирована как часть Phase 1+ (THREAD 10 в handoff). Актуально.

---

## Детальный анализ по actions

### Action 1: CANON/* merge / archive

**Что есть:**
```
docs/CANON/
  STRATEGY_CANON_2026-04-30.md   ← дублирует MASTER §1 (arch) + §7 (principles)
  HYPOTHESES_BACKLOG.md           ← новый, ценный
  OPERATOR_QUESTIONS.md           ← новый, входит в §16.6 gaps
  CUSTOM_BOTS_REGISTRY.md         ← детальнее чем MASTER §6
  RUNNING_SERVICES_INVENTORY_2026-04-30.md ← timestamp snapshot
  INDEX.md                        ← дублирует README.md
```

**Решение (не выполнять без подтверждения):**
- `STRATEGY_CANON_2026-04-30.md` → контент unique parts → MASTER §16. Файл → archive.
- `HYPOTHESES_BACKLOG.md` → переместить в `docs/HYPOTHESES_BACKLOG.md` (top-level)
- `OPERATOR_QUESTIONS.md` → интегрировать в MASTER §16.6. Файл → archive.
- `CUSTOM_BOTS_REGISTRY.md` → переместить в `docs/CUSTOM_BOTS_REGISTRY.md` (top-level)
- `RUNNING_SERVICES_INVENTORY_2026-04-30.md` → archive (STATE/ — источник истины)
- `INDEX.md` → archive (README.md достаточно)
- Директория `docs/CANON/` → `docs/archive/CANON_2026-04-30/`

**Правило MASTER §0.9:** "Не плодить .md файлы. Правки — в существующие."  
CANON/* нарушает §0.9 — это новый слой параллельной документации. Merge закрывает нарушение.

---

### Action 2: decision_log vs paper_journal

**Что есть:**
- `services/advise_v2/paper_journal.py` — advisor proposes, логирует в `advise_signals.jsonl`
- `services/decision_log/` — system detects events, логирует в `state/decision_log/events.jsonl`

**Scope разные:**
- `paper_journal` = "советник предлагает приём" → телеметрия Phase 1
- `decision_log` = "система детектировала событие" → пассивное наблюдение

**Статус decision_log на 30.04:**
- `state/decision_log/events.jsonl` — данные накапливаются
- Telegram alerts реализованы в `services/telegram_runtime.py` (DecisionLogAlertWorker)
- Layer 2 dedup добавлен (TZ-EVENT-DEDUP-WINDOW, commit 1356d46)
- RU polish сделан (commit 0ec68ec)

**RECOMMENDATION:**
- **KEEP decision_log** — уникальный capture layer, не дублирует paper_journal
- **Telegram alerts: оставить включёнными** (dedup уже сделан, RU polish сделан)
- JSONL запись продолжается
- Scope: decision_log = event detection layer; paper_journal = advisor telemetry layer

**[DECISION НЕ ТРЕБУЕТСЯ]** — scope определён, keep both.

---

### Action 3: managed_grid_sim vs What-If engine

**Что есть:**
- `src/whatif/` — What-If engine v1, episode-based, 12 plays из PLAYBOOK, parquet output
- `services/managed_grid_sim/` — managed grid simulation, 8 файлов, intervention rules layer

**Ключевое отличие (проверено по коду):**
```python
# managed_runner.py line 27-29:
def _ensure_engine_path() -> None:
    candidate = Path(r"C:\Users\Kemper\Documents\Codex\2026-04-20-new-chat\src")
```

`managed_grid_sim` импортирует Codex `engine_v2` (backtest_lab), **НЕ** `src/whatif/`.  
Это НЕ дубль What-If. Это обёртка над низкоуровневым engine_v2 с добавлением:
- Intervention rules (остановить/перезапустить бот при DD, росте, etc.)
- Managed runner (применяет правила к simulation)
- Regime classifier (классификация рыночного режима)
- Sweep engine (grid search по intervention params)

**What-If engine** работает на уровне plays/episodes (P-1, P-2, etc.).  
**managed_grid_sim** работает на уровне bot simulation с intervention rules.

**RECOMMENDATION: KEEP как отдельный слой.**  
Потенциальная будущая интеграция: managed_grid_sim results → feed What-If episode library.

---

### Action 4: dashboard

**Что есть:**
- `services/dashboard/loop.py`, `services/dashboard/state_builder.py`
- Live state visualization из state files

**Existing:** `/advise stats`, `/portfolio`, `/regime` в Telegram — текстовые команды

**Overlap:** LOW — dashboard = continuous visual layer, Telegram = on-demand text

**RECOMMENDATION: KEEP** — дополняет Telegram commands, не заменяет.  
Нет активного интеграция в app_runner пока — деплой по готовности.

---

### Action 5: play managers (adaptive_grid, boundary_expand, counter_long)

Три файла: `services/adaptive_grid_manager.py`, `services/boundary_expand_manager.py`,  
`services/counter_long_manager.py`

Это автоматизация confirmed plays (P-12, P-1, P-3) в рамках Phase 1+ dry-run.  
Никаких дублей в existing infrastructure — новый слой automation.

**RECOMMENDATION: KEEP** — aligned с ROADMAP Phase 1+ automation.

---

### Action 6: engine calibration tooling

- `tools/calibrate_ginarea.py` — calibration tool sim vs GinArea ground truth
- `docs/calibration/` — 4 отчёта фаз 1/2

Это уникальный инструмент. No overlap. **KEEP.**

---

## ROADMAP impact — обновления после 30.04

### §11 статус требует обновления:
- Phase 1 paper_journal: День N, работает с 28.04 → 14 days target
- Engine Phase 1 fixes: A2+A3 applied (calibration tool, bot7), A1+B1 applied (Codex engine_v2 external)
- Supervisor config: BOT_TOKEN/CHAT_ID alignment fixed
- decision_log + dedup + RU polish: production ready
- managed_grid_sim: implemented, not yet integrated in prod
- dashboard: implemented, не деплоен

### §12 next steps после cleanup:
1. Phase 1 monitoring — накопить 14 дней paper_journal data
2. TZ-BOOSTER-ACTIVATION-PATTERNS (Gap 1)
3. TZ-MANUAL-LONG-CLOSE-ANALYSIS (Gap 2)

---

## Cleanup proposal summary (FOR OPERATOR REVIEW)

| # | Action | Risk | Effort | Unlocks |
|---|---|---|---|---|
| 1 | Archive docs/CANON/* → docs/archive/CANON_2026-04-30/ | LOW | 15 min | §0.9 compliance |
| 2 | Keep decision_log (both layers live) | — | 0 | clarity of scope |
| 3 | Keep managed_grid_sim (separate layer) | — | 0 | future integration path |
| 4 | Keep dashboard (not deployed yet) | — | 0 | visual layer ready |
| 5 | Keep play managers | — | 0 | Phase 1+ ready |
| 6 | Merge STRATEGY_CANON unique content → MASTER §16 | LOW | 30 min | single source of truth |

**Action 1 + 6 требует подтверждения оператора. Все остальные — автоматически KEEP.**

---

## Decisions required

| # | Вопрос | Варианты |
|---|---|---|
| D-A | CANON merge: сейчас или позже? | (a) Сейчас в этом TZ (b) Отдельный TZ |
| D-B | Telegram alerts decision_log: оставить включёнными? | (a) Включены (dedup есть) (b) Silent mode |
| D-C | dashboard: деплоить в app_runner? | (a) Сейчас (b) После Phase 1 data |
