# docs/ INDEX — карта документации

> **Назначение**: единая карта всего, что лежит в `docs/`, с пометками статуса.
> Создан 2026-05-07 для наведения порядка. Это диагностический файл, ничего не двигает.
>
> **См. также**: [GROUP_I_AUDIT.md](GROUP_I_AUDIT.md) — детальные карточки 39 файлов корня docs/, CONTEXT/, STATE/, CANON/ с зафиксированными ключевыми решениями (D-018..D-104, INC-013/014, P-15, K-числа, и т.д.).
>
> **Легенда:**
> - **AUTHORITATIVE** — живой источник правды, читать первым
> - **REFERENCE** — стабильная справка, читать при необходимости
> - **ARCHIVED** — историческая ценность, не для текущей работы
> - **SUPERSEDED** — заменён более новой версией, кандидат на архив
> - **AUTO-GENERATED** — машинный вывод, кандидат на ротацию
> - **UNCLEAR** — статус не выяснен, нужно решение оператора
> - **DUPLICATE** — копия есть в другом месте, нужно решить какая каноническая

---

## 1. Корень `docs/`

| Файл | Статус | Заметка |
|---|---|---|
| `README.md` | REFERENCE | Корневой README docs |
| `MASTER.md` | UNCLEAR | Большой агрегатор, проверить актуальность |
| `PLAYBOOK.md` | REFERENCE | Operator playbook |
| `PLAYBOOK_MANUAL_LAUNCH_v1.md` | AUTHORITATIVE | План запуска первого бота |
| `REGULATION_v0_1.md` | SUPERSEDED | Заменён `v0_1_1` |
| `REGULATION_v0_1_1.md` | AUTHORITATIVE | Финальная regulation |
| `INCIDENTS.md` | AUTHORITATIVE | Журнал инцидентов |
| `SESSION_LOG.md` | UNCLEAR | Очень разрозненный, кандидат на ротацию |
| `OPPORTUNITY_MAP_v1.md` | SUPERSEDED | Заменён v2 |
| `OPPORTUNITY_MAP_v2.md` | REFERENCE | Карта возможностей |
| `OPERATOR_DEDUP_MONITORING.md` | REFERENCE | Operator manual |
| `OPERATOR_NIGHT_DOWNLOAD_1S_OHLCV.md` | REFERENCE | Operator manual |
| `GINAREA_MECHANICS.md` | REFERENCE | Механика GinArea |
| `PROJECT_MANIFEST.md` | UNCLEAR | Старый манифест? |
| `PROJECT_KNOWLEDGE_SYNC_2026-05-05.md` | AUTHORITATIVE | Синхронизация с PK (рефакторить под живой) |
| `NEXT_CHAT_PROMPT.md` | UNCLEAR | Одноразовый промпт? |
| `CLEANUP_GUIDE.md` | REFERENCE | Руководство по чистке репо |
| `REAL_SUMMARY_2026-04-28.md` | ARCHIVED | Снимок недельной давности |
| `BASELINE_INVESTIGATION_DESIGN_v0.1.md` | UNCLEAR | Дизайн-документ, проверить статус |
| `CALIBRATION_LOG_DESIGN_v0.1.md` | UNCLEAR | Дизайн-документ |
| `KILLSWITCH_DESIGN_v0.1.md` | UNCLEAR | Дизайн-документ |
| `ORCHESTRATOR_LOOP_DESIGN_v0.1.md` | UNCLEAR | Дизайн-документ |
| `ORCHESTRATOR_TELEGRAM_DESIGN_v0.1.md` | UNCLEAR | Дизайн-документ |
| `ENGINE_BUG_HYPOTHESES_2026-04-30.md` | ARCHIVED | Снимок диагностики недельной давности |
| `dashboard.css` / `dashboard.html` / `dashboard.js` / `state_inline.js` | REFERENCE | Дашборд-фронт. **Странно что в docs/, а не в `services/dashboard/`** |

### HANDOFF файлы в корне (должны переехать в `docs/HANDOFFS/`)

| Файл | Статус |
|---|---|
| `HANDOFF_2026-04-29.md` | ARCHIVED |
| `HANDOFF_2026-04-29_evening.md` | ARCHIVED |
| `HANDOFF_2026-04-30_evening_final.md` | ARCHIVED |
| `HANDOFF_2026-04-30_part01.md` | ARCHIVED |
| `HANDOFF_2026-04-30_part01_kickoff.txt` | ARCHIVED |
| `HANDOFF_2026-05-04.md` | ARCHIVED |
| `Handoff_2026-05-06.md` | AUTHORITATIVE | Последний (заметь регистр имени — несогласованно) |

---

## 2. `docs/CONTEXT/` — должна быть «живая шапка проекта»

| Файл | Статус | Заметка |
|---|---|---|
| `PROJECT_CONTEXT.md` | AUTHORITATIVE | Корневой контекст проекта |
| `DEPRECATED_PATHS.md` | AUTHORITATIVE | Deprecated paths registry |
| `DRIFT_HISTORY.md` | AUTHORITATIVE | История дрейфа решений |
| `STATE_CURRENT.md` | UNCLEAR | Vs `STATE_CURRENT_2026-05-05_EOS.md` — какой канонический? |
| `STATE_CURRENT_2026-05-05_EOS.md` | DUPLICATE | Также лежит в `docs/STATE/` |
| `HANDOFF_2026-05-02.md` | ARCHIVED | Должен быть в `docs/HANDOFFS/` |
| `HANDOFF_2026-05-03.md` | ARCHIVED | Должен быть в `docs/HANDOFFS/` |
| `MAIN_CHAT_OPENING_PROMPT_2026-05-04.md` | ARCHIVED | Одноразовый промпт |
| `MAIN_PROJECT_SETUP_GUIDE_2026-05-04.md` | UNCLEAR | Setup guide, проверить актуальность |
| `SESSION_DELTA_2026-05-02.md` | ARCHIVED | Дельта одной сессии |
| `main_prompt_audit_2026-05-03.md` | ARCHIVED | Аудит промпта |
| `_handoff_current.json` | AUTO-GENERATED | Машинный handoff |
| `README.md` | REFERENCE | README папки |

---

## 3. `docs/STATE/` — ЗОНА БЕДСТВИЯ

**211 файлов `CURRENT_STATE_*.md`** автогенерации каждые 30 мин с 2026-04-29 до сегодня.

| Файл | Статус | Заметка |
|---|---|---|
| `CURRENT_STATE_latest.md` | AUTHORITATIVE | Последний снапшот |
| `CURRENT_STATE_2026-XX-XX_HHMM.md` (×210) | AUTO-GENERATED | Кандидат на ротацию в `_archive/YYYY-MM/` |
| `STATE_CURRENT_2026-05-05_EOS.md` | AUTHORITATIVE | EOS-снимок (дубль с CONTEXT) |
| `PENDING_TZ.md` | AUTHORITATIVE | Очередь TZ |
| `PROJECT_MAP.md` | AUTHORITATIVE | Карта проекта |
| `ROADMAP.md` | UNCLEAR | Vs `docs/PLANS/MULTI_TRACK_ROADMAP.md` — какой канонический? |
| `QUEUE.md` | UNCLEAR | Vs `PENDING_TZ.md`? |
| `BOT_INVENTORY.md` | REFERENCE | Инвентарь ботов |
| `TELEGRAM_EMITTERS_INVENTORY.md` | REFERENCE | Telegram emitters |
| `DASHBOARD_INVENTORY_2026-04-30.md` | ARCHIVED | Снимок инвентаря |
| `DEBT_CLASSIFICATION_2026-05-02.md` | ARCHIVED | Классификация долга |
| `STRATEGY_DIGEST_2026-04-30.md` | ARCHIVED | Дайджест стратегии |
| `INVENTORY_*_2026-04-29*.md/json` (×3) | ARCHIVED | Снимки инвентаря |
| `RECONCILE_01_2026-04-29*.md/json` (×3 пары) | ARCHIVED | Reconcile снимки |
| `RESTORED_FEATURES_AUDIT_2026-04-29*.md/json` | ARCHIVED | Audit снимок |
| `MARKET_DATA_AUDIT_2026-04-29*.md/json` | ARCHIVED | Audit снимок |
| `CONFLICTS_TRIAGE_2026-04-29*.md` + `conflicts_triage_*.json` | ARCHIVED | Triage снимок |
| `CURRENT_STATE_2026-04-29_*.md` (×9) | ARCHIVED | Pre-auto-rotation снимки |
| `CURRENT_STATE_2026-04-30_0204.md` | ARCHIVED | Snapshot |
| `dashboard_state.json` / `state_latest.json` / `project_map.json` | AUTO-GENERATED | Машинное состояние |
| `ohlcv_ingest_log.jsonl` | AUTO-GENERATED | Лог ingest |

---

## 4. `docs/DESIGN/` — архитектурные специи

| Файл | Статус |
|---|---|
| `DECISION_LAYER_v1.md` | AUTHORITATIVE |
| `MTF_DISAGREEMENT_v1.md` | AUTHORITATIVE |
| `MTF_FEASIBILITY_v1.md` | AUTHORITATIVE |
| `CLASSIFIER_AUTHORITY_v1.md` | AUTHORITATIVE |
| `BOT_ID_SCHEMA_v0_1.md` | REFERENCE |
| `P8_DUAL_MODE_COORDINATOR_v0_1.md` | REFERENCE |
| `P8_RANGE_DETECTION_v0_1.md` | REFERENCE |
| `SIZING_MULTIPLIER_v0_1.md` | REFERENCE |
| `_classifier_disagreement_raw.json` | AUTO-GENERATED |

---

## 5. `docs/RESEARCH/` — исследовательские артефакты

### Финальные .md (foundation)

| Файл | Статус |
|---|---|
| `REGIME_OVERLAY_v2_1.md` | AUTHORITATIVE (по списку оператора) |
| `REGIME_OVERLAY_v3.md` | UNCLEAR (новее v2_1, нужно подтверждение) |
| `REGIME_OVERLAY_v2.md` | SUPERSEDED |
| `REGIME_OVERLAY_v1.md` | SUPERSEDED |
| `REGIME_OVERLAY_v1_CROSSCHECK.md` | ARCHIVED |
| `HYSTERESIS_CALIBRATION_v1.md` | AUTHORITATIVE |
| `TRANSITION_MODE_COMPARE_v2.md` | AUTHORITATIVE |
| `TRANSITION_MODE_COMPARE_v1.md` | SUPERSEDED |
| `FORECAST_CALIBRATION_DIAGNOSTIC_v1.md` | AUTHORITATIVE |
| `FORECAST_FEED_ROOT_CAUSE_v1.md` | REFERENCE |
| `FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_claude.md` | AUTHORITATIVE (выбран оператором) |
| `FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_codex.md` | SUPERSEDED |
| `MARKET_DECISION_SUPPORT_RESEARCH_v1_claude.md` | AUTHORITATIVE (выбран оператором) |
| `MARKET_DECISION_SUPPORT_RESEARCH_v1_codex.md` | SUPERSEDED |
| `MTF_CALIBRATION_HISTOGRAM_v1.md` | AUTHORITATIVE |
| `BACKTEST_AUDIT.md` | REFERENCE |
| `DEDUP_DRY_RUN_2026-05-04.md` | REFERENCE |
| `DEDUP_THRESHOLD_TUNING_v1.md` | REFERENCE |
| `GINAREA_BACKTESTS_REGISTRY_v1.md` | REFERENCE |
| `K_RECALIBRATE_PRODUCTION_v1.md` | REFERENCE |
| `LONG_TP_SWEEP_v1.md` | REFERENCE |
| `P8_RGE_EXPANSION_RESULTS_v0_1.md` | REFERENCE |
| `POSITION_CLEANUP_SIMULATION_v1.md` | AUTHORITATIVE |
| `POSITION_DEDUP_DIAGNOSIS.md` | REFERENCE |
| `REGIME_PERIODS_2025_2026.md` | REFERENCE |
| `DASHBOARD_USABILITY_DIAGNOSIS_v1.md` | REFERENCE |

### Сырые артефакты — все AUTO-GENERATED, кандидаты в `_artifacts/`

| `_*.json`, `_*.png` (×17 файлов) | AUTO-GENERATED |

---

## 6. `docs/PLANS/`

| Файл | Статус |
|---|---|
| `MULTI_TRACK_ROADMAP.md` | AUTHORITATIVE |
| `WEEK_2026-05-04_to_2026-05-10.md` | AUTHORITATIVE (текущая неделя) |
| `WEEK_TEMPLATE.md` | REFERENCE |

---

## 7. `docs/SPRINTS/`

| Файл | Статус |
|---|---|
| `SPRINT_2026-05-05.md` | AUTHORITATIVE (последний спринт) |
| `SPRINT_2026-05-04.md` | ARCHIVED |
| `SPRINT_2026-05-04_DRAFT.md` | ARCHIVED (draft устарел) |
| `SPRINT_TEMPLATE.md` | REFERENCE |

---

## 8. `docs/SESSIONS/`

| Файл | Статус |
|---|---|
| `SESSION_2026-05-04_FULL.md` | ARCHIVED |

---

## 9. `docs/TZ-папки` — три места одного назначения

| Папка | Содержимое | Решение |
|---|---|---|
| `docs/tz/` (lowercase) | TZ-005...TZ-010 — старая нумерация | ARCHIVED — старые TZ |
| `docs/TZs/` (uppercase plural) | 1 файл TZ-MORNING-BRIEF | UNCLEAR — мерджить в `docs/TZ/` |
| `docs/specs/` | 1 файл ADVISE_V2_SPEC | UNCLEAR — это spec, не TZ; оставить отдельно или мерджить |
| `docs/TZ/` (новая каноническая) | НЕ СОЗДАНА | Создать как единый источник |

**Предложение**: создать `docs/TZ/` как канонический. `docs/tz/` → `docs/ARCHIVE/tz_old/`. Содержимое `docs/TZs/` и `docs/specs/` → `docs/TZ/` (если живые) или ARCHIVE.

---

## 10. `docs/ANALYSIS/` — кросс-чеки и аналитика 2026-05-06

Все файлы датированы 2026-05-06 (вчерашняя сессия). Это рабочий аналитический «ток».

Парные `_cc` / `_codex` файлы:
- `CROSS_CHECK_CC_BY_CODEX` + `CROSS_CHECK_CODEX_BY_CC` — взаимные ревью, оба валидны
- `EXIT_VARIANTS_*_cc` + `_codex` — оба валидны
- `EXTENDED_BACKTEST_*_cc` + `_codex` — оба валидны
- `OI_DEEP_DIVE_*_cc` + `_codex` — оба валидны

Уникальные:
- `GINAREA_BACKTEST_RECONCILIATION_2026-05-06.md` | AUTHORITATIVE
- `HEDGE_BOT_PRICE_SIMULATOR_2026-05-06.md` | REFERENCE
- `LIVE_HEDGE_BOT_ANALYSIS_2026-05-06.md` | REFERENCE
- `LIVE_REGIME_READ_2026-05-06.md` | REFERENCE
- `LONG_HEDGE_BOT_ANALYSIS_2026-05-06.md` | REFERENCE
- `REGIME_V2_CALIBRATION_2026-05-06.md` | AUTHORITATIVE
- `SHORT_EXIT_OPTIONS_2026-05-06.md` | REFERENCE
- `SHORT_FINAL_RECONCILED_2026-05-06.md` | AUTHORITATIVE (финальное согласование)
- `SHORT_THESIS_REVIEW_2026-05-06.md` | REFERENCE
- `UPTREND_ANALOG_REVIEW_2026-05-06.md` | REFERENCE
- `UPTREND_PULLBACK_ANALOGS_2026-05-06.md` | REFERENCE

Все `_*.json` — AUTO-GENERATED, кандидаты в `_artifacts/`.

`_archive/` — уже есть, проверить содержимое.

---

## 11. `docs/CANON/` — канонические справочники

| Файл | Статус |
|---|---|
| `INDEX.md` | REFERENCE (старый CANON-индекс, может конфликтовать с этим INDEX.md) |
| `STRATEGY_CANON_2026-04-30.md` | AUTHORITATIVE |
| `CUSTOM_BOTS_REGISTRY.md` | AUTHORITATIVE |
| `RUNNING_SERVICES_INVENTORY_2026-04-30.md` | UNCLEAR (дата старая) |
| `HYPOTHESES_BACKLOG.md` | AUTHORITATIVE |
| `OPERATOR_QUESTIONS.md` | REFERENCE |

---

## 12. Прочие подпапки

| Папка | Статус | Заметка |
|---|---|---|
| `docs/STRATEGIES/` | REFERENCE | 1 файл H10.md |
| `docs/api/` | REFERENCE | GinArea API notes |
| `docs/audit/` | ARCHIVED | Аудиты 2026-04-30 |
| `docs/calibration/` | ARCHIVED | Все Phase 1 фазы 2026-04-30 |
| `docs/decision_log/` | ARCHIVED | 1 файл 2026-04-30 |
| `docs/github/` | REFERENCE | Setup инструкции |
| `docs/managed_grid_sim/` | REFERENCE | Архитектура симулятора |
| `docs/setup_backtest/` | REFERENCE | Архитектура |
| `docs/history/` | ARCHIVED | Чек-листы/манифесты/release_notes — старая история |
| `docs/release_history/` | ARCHIVED | 80+ файлов FIX*_NOTES.txt — старая история релизов |
| `docs/CLEANUP_GUIDE.md` | REFERENCE | Гайд по чистке |

---

## Сводка по объёмам

| Зона | Файлов | Главный балласт |
|---|---|---|
| `docs/STATE/` | ~230 | 211 авто-снапшотов CURRENT_STATE_*.md |
| `docs/release_history/` | ~80 | FIX*_NOTES.txt |
| `docs/RESEARCH/` | ~45 | 17 `_*.json/png` сырых |
| `docs/ANALYSIS/` | ~30 | парные cc/codex + json |
| остальные | ~80 | разное |

**Итого**: ~470 файлов в `docs/`. После чистки целевой объём — **~150 файлов** на верхнем доступе, остальное в `_archive/`.
