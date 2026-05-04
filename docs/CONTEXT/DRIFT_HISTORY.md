# DRIFT HISTORY
# Назначение: anti-patterns и drift incidents. Читать перед новой TZ.
# Формат: каждый incident — ID, дата, тип, симптомы, root cause, fix.
# Обновлять при каждом обнаруженном дрейфе.

---

## DRIFT-001 — Playbook v3 reactive anti-pattern

**Date:** 2026-05-01 → 2026-05-03
**Type:** drift+ (scope creep — built something not in plan)
**Detected by:** TZ-COUNTERTREND-VALIDATE-VS-OPERATOR (commit 1ffdc12)

**Symptoms:**
- Bot generating 6 "advise" signals/day that operator ignored
- Playbook rules said "act on signal" but operator acted on market feel instead
- Growing gap between playbook-recommended actions and actual operator decisions

**Root cause:**
- Playbook built as per-alert reactive tree (DP-003)
- Did not account for operator's phase-level state awareness
- Each alert treated as independent without MTF context

**Fix:**
- Playbook v3 with early-intervention branch (db8f064)
- Phase classifier feeds branch selection upstream
- Operator brief generated once/day, not per-alert

**Prevention rule:**
> Before adding any new operator-facing signal: verify operator will actually use it.
> If no operator action in 3+ consecutive signals of a type → deprecate the signal type.

---

## DRIFT-002 — INERT-BOTS confusion

**Date:** 2026-04-28 → 2026-04-30
**Type:** drift- (incomplete — work started, wrong direction)
**Detected by:** TZ-PROJECT-STATE-AUDIT (2026-05-02)

**Symptoms:**
- Bot started, tracker showed RUNNING, but no actual trades executed
- Operator assumed bots were active; they were "inert" (running but not trading)
- Counter-long, boundary-expand, adaptive-grid all showed RUNNING with 0 actions

**Root cause:**
- Services launched but no live positions existed to act on
- Tracker RUNNING = process alive, not "doing something meaningful"
- No distinction between "service running" and "service actively managing positions"

**Fix:**
- Added `cmdline_must_contain` fallback check in tracker (TZ-DIAGNOSE-TRACKER-FALSE-NEGATIVE)
- Paper journal started (Day 1) as Phase 1 to generate observable signal record

**Prevention rule:**
> RUNNING in tracker = process alive only. Always check last_action timestamp.
> If last_action > 6h ago for an active service → investigate before assuming OK.

---

## DRIFT-003 — Premature TZ without prerequisite inventory

**Date:** 2026-04-26 → 2026-04-29
**Type:** drift+ (wrong direction — built without checking what existed)
**Detected by:** TZ-PROJECT-STATE-AUDIT

**Symptoms:**
- TZ-057/065/066 queued before H10 backtest data existed
- TZ-ENGINE-FIX-RESOLUTION started before operator confirmed 1s OHLCV availability
- Multiple TZs blocked immediately after start (no data, no baseline)

**Root cause:**
- TZs written without checking PENDING_TZ.md for existing blockers
- Dependency graph not validated before scheduling
- "Optimistic planning" — assumed data/infrastructure would be ready

**Fix:**
- TZ validator CLI: `tools/validate_tz.py` (TZ-CLAUDE-TZ-VALIDATOR, 20 tests)
- Mandatory pre-TZ check: validate_tz before starting any TZ
- Operator action items listed explicitly in §5 of STATE_CURRENT.md

**Prevention rule:**
> Before scheduling any TZ that depends on data: verify data exists with `ls -la data/`.
> Before scheduling any TZ that depends on another TZ: confirm that TZ is ✅ DONE in STATE_CURRENT.

---

## DRIFT-004 — Context window exhaustion mid-TZ

**Date:** 2026-05-03 (this session)
**Type:** drift- (incomplete — TZ interrupted by context limits)
**Detected by:** Session summary trigger

**Symptoms:**
- TZ-MAIN-COORDINATOR-INFRASTRUCTURE started (12 deliverables)
- Context hit limit after deliverable 1 (WEEK_TEMPLATE.md)
- Work state scattered across session summary

**Root cause:**
- 12-deliverable TZ is too large for single session without handoff checkpoints
- No mid-TZ checkpoints defined (only end-of-TZ commit planned)
- WEEK_TEMPLATE was first deliverable but commit deferred to end

**Fix:**
- Resumed from session summary (context preserved across compaction)
- Deliverables being written sequentially, committed at end

**Prevention rule:**
> For TZs with >6 deliverables: commit after every 3rd deliverable as intermediate checkpoint.
> Mid-TZ commit message: "wip(TZ-ID): deliverables N-M done, N+1 to N+6 remaining"

---

## DRIFT-005 — Calibration ceiling mistaken for fixable bug

**Date:** 2026-05-03
**Type:** drift+ (scope creep — kept trying to improve past fundamental ceiling)
**Detected by:** CP3 GO/NO-GO gate

**Symptoms:**
- Brier target: ≤0.22. Actual: ~0.257 across all trials
- Spent ~2h on threshold tuning (1% → 0.3%), feature additions, weight perturbations
- Each attempt improved Brier marginally but never crossed 0.22

**Root cause:**
- Rule-based signals (positioning extreme, structural context) are systematically contrarian
- In strong bull year (2025-2026), contrarian signals fire bearish during markup
- No amount of weight tuning fixes systematic signal inversion

**Fix:**
- CP3 gate triggered (0.22-0.28 → report operator, wait)
- Sent to operator as GO/NO-GO decision (not treated as a bug to fix)
- WHATIF-V3 full rebuild killed (DP-002)

**Prevention rule:**
> If Brier does not improve after 3 different approaches → it is a ceiling, not a bug.
> At ceiling: document the root cause, trigger operator gate, do not continue tuning.

---

## DRIFT-006 — Minimum viable scope when operator asked for full system

**Date:** 2026-05-03
**Type:** drift- (wrong direction — scoped too small for the actual goal)
**Detected by:** Operator clarification after CP3 gate

**Symptoms:**
- Architect proposed "qualitative briefs only" and "accept calibration ceiling" as final answer
- Options given: (A) accept ceiling, (B) add trend features, (C) other
- Operator clarified: "полноценная система... что бы понимало и просчитывало все режимы рынка"
- Architect had been solving the *minimum viable* version, not the actual goal

**Root cause:**
- CP3 gate framed as binary: Brier good enough vs not good enough
- Missed that the fundamental architecture (one unified model) was wrong
- Should have asked: "what does success look like end-state?" before building ETAP 1-3

**Fix:**
- Variant C: regime-conditional calibration — separate model per regime
- Full week plan with 7 ETAPs: qualitative → regime models → auto-switch → OOS → self-monitor
- DEPRECATED: trend-following in unified model (DP-006)

**Prevention rule:**
> Before any 5+ hour TZ: ask operator "what does end-state look like when this is truly done?"
> If operator says "полноценная" / "sustainable" / "practical and useful" → that is a MAJOR PROJECT, not a TZ.
> Scope explicitly before starting any ETAP sequence.

---

## DRIFT-007 — Estimates в человеко-часах vs wall-clock Claude Code

**Date:** 2026-05-04
**Type:** drift- (некорректное планирование, пересмотр)
**Detected by:** оператор после 20-минутного закрытия 5-часового плана Day 1

**Symptoms:**
- Week plan estimates: 4–5h на TZ
- Actual wall-clock: 2 сек – 3 мин на TZ
- Расхождение ×10 – ×100

**Root cause:**
- Week plan был написан с unit "developer hours from scratch", не "Claude Code wall-clock с full context"
- Coordinator (MAIN) этого не пересмотрел в morning brief

**Fix:**
- Switched to block-based protocol (не daily ETAP frame)
- Removed morning brief / EOD report ceremony when blocks <30 мин
- Continued protocol через CP snapshots + verdict

**Prevention rule:**
> Estimates writes в wall-clock Claude Code, не в developer-hours.
> При первом значимом mismatch — pivot на block-based.

---

## DRIFT-008 — Inference about ceiling from numbers measured on inconsistent splits

**Date:** 2026-05-04
**Type:** drift+ (преждевременный вывод на грязных данных)
**Detected by:** оператор-bot exchange при tracking sample size после regime_int fix

**Symptoms:**
- Coordinator неоднократно объявлял "потолок 0.253 реальный" на основе сравнений
- Все pre-Tier-1-wired сравнения были на различных train/test splits (29,953 mixed → 14,085 clean MARKUP)
- При первой пересборке split sample упал на 53% — данные не сравнимы

**Root cause:**
- Не verified split integrity перед каждым ceiling-claim
- "Apples-to-apples" подтверждалось только по seed, не по dataset state

**Fix:**
- Введён STAGE 0 verification mandatory для каждого regime model block (MARKDOWN, RANGE — оба обнаружили stale splits, оба regenerated)
- Все ceiling-claims после Tier-1 wired сравниваются только в рамках одного валидного split

**Prevention rule:**
> Перед любым ceiling-claim: verify (1) sample size matches expected from regime classifier output,
> (2) regime_int distribution на 100% соответствует метке режима,
> (3) outcome distribution sane для режима.
> Ceiling claims на single split всегда tentative до CV.

---

## DRIFT-009 — Per-horizon failure rule интерпретация

**Date:** 2026-05-04
**Type:** positive deviation (расширение интерпретации правила)
**Detected by:** coordinator при анализе MARKUP результатов (1d GREEN, 1h YELLOW)

**Symptoms:**
- Failure rule был "ANY regime failing Brier 0.28 hard stop → ship qualitative only"
- Buchstabe rule = per regime
- Реальность: matrix regime × horizon, разные ячейки имеют разные predictability

**Resolution:**
- Operator approved расширение интерпретации
- Per-horizon delivery matrix вместо all-or-nothing per regime
- 7/9 numeric ячеек вместо нулевого numeric coverage если бы держались buchstabe

**Prevention rule:**
> Failure rules написаны на одном уровне абстракции.
> При появлении более детальной структуры (per-horizon, per-pair, per-session) — explicit operator approval для расширения интерпретации, фиксация в DRIFT_HISTORY.

---

## DRIFT-010 — Single-window Brier claims must be CV-validated

**Date:** 2026-05-04
**Type:** drift+ (преждевременная уверенность в numeric claim)
**Detected by:** MARKDOWN-1d diagnostic, потом OOS validation

**Symptoms:**
- MARKUP-1d Brier 0.226 объявлен GREEN на single window
- CV выявил: mean 0.235, σ=0.114, max 0.294 — фактически window-sensitive
- Single-window estimates систематически смещены к best-case в trending данных

**Root cause:**
- Time-series with regime structure имеют high inter-window variance
- Single split testing не отражает production behavior

**Prevention rule:**
> Любой claim "GREEN/YELLOW gate passed" — tentative до CV (минимум 4 windows).
> Production deployment решений не принимать на single-window evidence.

---

## DRIFT-011 — Coordinator inherited single-track week plan

**Date:** 2026-05-04
**Type:** drift- (отсутствие project mapping at session start)

**Symptoms:**
- Started session with focus только на forecast pipeline, не сделал inventory всех направлений проекта (GinArea LONG fix, engine validation, research dirs)
- Operator явно указал на это: "это первое что должен был сделать координатор"

**Prevention rule:**
> Каждая новая coordinator-сессия начинается с project map check (что в проекте, какие приоритеты), даже если есть готовый week plan. Inherit the plan, don't inherit the scope.

---

## DRIFT-012 — Forecast pipeline built без подключения к боту

**Date:** 2026-05-04
**Type:** drift- (analytics layer без integration)

**Symptoms:**
- Closed forecast pipeline за день, но он стоит idle — не плюгнут ни к GinArea, ни к ручной торговле, ни к operator workflow
- 55 тестов green, но zero downstream consumers

**Prevention rule:**
> Перед building analytics layer спросить у оператора как analytics будет переводиться в action. Если ответ "разберёмся потом" — это research, не production.

---

## DRIFT-013 — Coordinator built tools без actionability layer

**Date:** 2026-05-04
**Type:** drift- (technical work без user pain alignment)

**Symptoms:**
- Forecast выдаёт probability, но не sizing multiplier
- Operator pain "перебираю/недобираю" не закрыта построенной системой
- Probability → action gap не закрыт ни кодом, ни планом

**Prevention rule:**
> Map operator pains to deliverables до начала building. Если deliverable не закрывает pain — это research, не production.

---

## DRIFT-014 — Operator workflow assumed not asked

**Date:** 2026-05-04
**Type:** drift- (predefined assumption)

**Symptoms:**
- Coordinator predefined "operator замечает setup, спрашивает систему" workflow в roadmap
- Operator поправил: "это я замечаю setup? я думал система говорит вот сетап"
- Inverted direction of information flow not validated before write

**Prevention rule:**
> Operator workflows нельзя додумывать. Когда дизайнишь интерфейс — спросить explicitly у оператора кто инициатор и кто получатель в каждом канале коммуникации.

---

## DRIFT-015 — Fictional CLI command transmitted to operator

**Date:** 2026-05-04
**Type:** drift- (transmission of unverified instruction)

**Symptoms:**
- Worker написал `python -m services.calibration.reconcile_v3 --mode direct_k` в TZ-OPERATOR-NIGHT-DOWNLOAD-PREP D5 как next step
- Module не имел CLI — это library file без `if __name__ == "__main__":`
- Coordinator передал команду оператору без verification
- Operator запустил, exit code 0, no output — потеряли время на диагностику

**Prevention rule:**
> Любая operator-facing команда от worker должна быть verified. Запросить у worker'а demonstration что команда runs (хотя бы --help output). Особенно когда команда — "next step" а не "тест проверь работает ли".

---

## META-PATTERN-001 — Inference under shifting conditions

**Date:** 2026-05-04 (consolidation of DRIFT-005, 008, 010)
**Type:** meta-pattern (cross-incident)

**Pattern:**
Когда base data меняется (regime_int fix, split regeneration, sample size change) — все предшествующие inference на этих данных tentative и требуют re-verification. Coordinator склонен accumulating claims без revisiting basis.

**Examples:**
- DRIFT-005 — ceiling-chasing without explicit stop
- DRIFT-008 — inconsistent splits (29k → 14k after regime_int fix invalidated all prior ceiling claims)
- DRIFT-010 — single-window 0.226 GREEN claim refuted by CV (mean 0.235, σ 0.114)

**Prevention rule:**
> Перед любым ceiling/gate claim проверять три уровня одновременно:
> 1. **Data integrity** — sample size, label distribution, outcome distribution sane
> 2. **Cross-experiment consistency** — claim сделан на same dataset как предыдущие comparisons
> 3. **Cross-window stability** — variance acceptable across multiple time-series splits
> Failure любого слоя ставит ВСЕ claims под сомнение, не только напрямую затронутый.

---

## DRIFT-PATTERN SUMMARY

| Pattern | Count | Typical trigger |
|---------|-------|----------------|
| Premature TZ (no inventory check) | 3 | Optimistic scheduling |
| Reactive builds (no operator validation) | 2 | Alert-first design |
| Analytics layer без integration / actionability | 2 | Building tools without user pain mapping (D-012, D-013) |
| Context exhaustion mid-TZ | 1 | >6 deliverable TZs |
| Calibration ceiling chasing | 2 | Missing explicit stop criterion / inconsistent splits |
| Service confusion (RUNNING ≠ active) | 1 | Tracker status misread |
| Minimum viable scope vs full system | 1 | CP3 gate framed too narrowly |
| Estimate-unit mismatch (dev-h vs wall-clock) | 1 | Plan written without Claude Code calibration |
| Single-window claim treated as CV-validated | 1 | High inter-window variance in time-series |
| Per-regime rule applied to per-cell structure | 1 | Failure rule written at coarser abstraction |
| Coordinator inherited plan без project map | 1 | Single-track focus, no inventory at session start |
| Workflow assumed not asked | 1 | Predefined operator interaction pattern |
| Unverified CLI transmitted to operator | 1 | "next step" assumption without demonstration |

**Most common:** Premature TZ without checking prerequisites.
**Highest impact:** INERT-BOTS confusion (2+ days of false confidence).
**Recurring pattern (META-PATTERN-001):** Drawing inferences from data measured under shifting conditions (DRIFT-005, 008, 010).
**Process insight (DRIFT-009):** When a rule meets a more-detailed structure than it was written for, get explicit operator approval.
**New session-opening rule (DRIFT-011):** Every coordinator session starts with project map check, even with inherited plan.
