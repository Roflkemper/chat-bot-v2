# docs/ CLEANUP PROPOSAL

> **Создан**: 2026-05-07
> **Статус**: ПРЕДЛОЖЕНИЕ. Ничего не удалено и не перемещено. Жду твоё «да/нет» по каждому пункту.
>
> **Принцип**: ничего не удаляем безвозвратно. Всё спорное → `docs/ARCHIVE/`, оттуда легко достать.

---

## Целевая структура `docs/`

```
docs/
├── INDEX.md                      ← карта всего
├── README.md
├── CONTEXT/                      ← живая шапка проекта (читается каждой новой сессией)
│   ├── STATE.md                  ← где мы сейчас (5-15 строк, обновляется в EOS)
│   ├── ROADMAP.md                ← что строим (link на MULTI_TRACK_ROADMAP)
│   ├── DECISIONS.md              ← ADR-журнал (новый файл, ведём с этой сессии)
│   ├── DRIFT_HISTORY.md
│   ├── DEPRECATED_PATHS.md
│   └── PROJECT_CONTEXT.md
├── HANDOFFS/                     ← все handoff в одном месте
│   ├── HANDOFF_2026-04-29.md
│   ├── HANDOFF_2026-04-29_evening.md
│   ├── ... (все старые)
│   └── HANDOFF_2026-05-06.md     ← последний, нормализуем регистр
├── DESIGN/                       ← без изменений
├── RESEARCH/
│   ├── *.md                      ← финальные отчёты
│   └── _artifacts/               ← все _*.json, _*.png
├── ANALYSIS/
│   ├── *.md
│   └── _artifacts/               ← все _*.json
├── PLANS/                        ← без изменений
├── SPRINTS/                      ← последний sprint живой, остальные в ARCHIVE
├── TZ/                           ← НОВАЯ единая папка для всех TZ/specs
├── CANON/                        ← без изменений (но проверить INDEX.md vs наш)
├── STATE/
│   ├── CURRENT_STATE_latest.md
│   ├── PENDING_TZ.md
│   ├── PROJECT_MAP.md
│   ├── BOT_INVENTORY.md
│   ├── TELEGRAM_EMITTERS_INVENTORY.md
│   └── _archive/
│       ├── 2026-04/              ← все CURRENT_STATE_2026-04-XX
│       └── 2026-05/              ← все CURRENT_STATE_2026-05-XX (кроме последних 24ч)
├── OPERATOR/                     ← НОВАЯ для операторских мануалов
│   ├── PLAYBOOK.md
│   ├── PLAYBOOK_MANUAL_LAUNCH_v1.md
│   ├── OPERATOR_DEDUP_MONITORING.md
│   └── OPERATOR_NIGHT_DOWNLOAD_1S_OHLCV.md
├── REGULATION/                   ← НОВАЯ
│   └── REGULATION_v0_1_1.md      (v0_1 → ARCHIVE)
└── ARCHIVE/                      ← всё устаревшее
    ├── handoffs_old/
    ├── designs_v0/
    ├── tz_old/
    ├── audits_2026-04/
    ├── calibration_phase1/
    ├── release_history/
    ├── history/
    └── snapshots_2026-04/
```

---

## Этап 2 — конкретные действия (атомарные, по группам)

Каждая группа = одна операция = один коммит. После каждой можно сделать паузу и проверить.

### Группа A — handoff'ы в одну папку (низкий риск)

**Действие**: создать `docs/HANDOFFS/`, переместить туда все 9 handoff-файлов.

| Откуда | Куда |
|---|---|
| `docs/HANDOFF_2026-04-29.md` | `docs/HANDOFFS/HANDOFF_2026-04-29.md` |
| `docs/HANDOFF_2026-04-29_evening.md` | `docs/HANDOFFS/HANDOFF_2026-04-29_evening.md` |
| `docs/HANDOFF_2026-04-30_evening_final.md` | `docs/HANDOFFS/HANDOFF_2026-04-30_evening_final.md` |
| `docs/HANDOFF_2026-04-30_part01.md` | `docs/HANDOFFS/HANDOFF_2026-04-30_part01.md` |
| `docs/HANDOFF_2026-04-30_part01_kickoff.txt` | `docs/HANDOFFS/HANDOFF_2026-04-30_part01_kickoff.txt` |
| `docs/HANDOFF_2026-05-04.md` | `docs/HANDOFFS/HANDOFF_2026-05-04.md` |
| `docs/Handoff_2026-05-06.md` | `docs/HANDOFFS/HANDOFF_2026-05-06.md` *(нормализация регистра)* |
| `docs/CONTEXT/HANDOFF_2026-05-02.md` | `docs/HANDOFFS/HANDOFF_2026-05-02.md` |
| `docs/CONTEXT/HANDOFF_2026-05-03.md` | `docs/HANDOFFS/HANDOFF_2026-05-03.md` |

**Плюсы**: handoff'ы больше не разбросаны по 2 директориям, читаются последовательно.
**Риски**: если кто-то ссылается на путь — поправить ссылки. Я могу прогрепить перед перемещением.

---

### Группа B — авто-снапшоты в архив (низкий риск, большой эффект)

**Действие**: создать `docs/STATE/_archive/2026-04/` и `docs/STATE/_archive/2026-05/`. Переместить туда все `CURRENT_STATE_YYYY-MM-DD_HHMM.md` **кроме последних 48 часов**.

- ~211 файлов уйдут из верхнего уровня `STATE/`
- На верхнем уровне остаётся: `CURRENT_STATE_latest.md` + последние 48ч (≈100 шт. → можно жёстче, последние 24ч)

**Альтернатива (рекомендую)**: оставить только `CURRENT_STATE_latest.md`, всё остальное в `_archive/`. Если нужна диагностика — посмотрит в архиве.

**Также в архив**:
- `INVENTORY_*_2026-04-29*.md/json` (3 пары)
- `RECONCILE_01_2026-04-29*.md/json` (3 пары)
- `RESTORED_FEATURES_AUDIT_2026-04-29*.md/json` (1 пара)
- `MARKET_DATA_AUDIT_2026-04-29*.md/json` (1 пара)
- `CONFLICTS_TRIAGE_2026-04-29*.md` + json
- `CURRENT_STATE_2026-04-29_*.md`, `CURRENT_STATE_2026-04-30_0204.md`
- `DASHBOARD_INVENTORY_2026-04-30.md`
- `STRATEGY_DIGEST_2026-04-30.md`
- `DEBT_CLASSIFICATION_2026-05-02.md`

**Плюсы**: `STATE/` становится читаемым. Сейчас открыть его — это паника.

---

### Группа C — старые design/calibration/audit в ARCHIVE (низкий риск)

**Перемещения в `docs/ARCHIVE/`**:

| Откуда | Куда | Почему |
|---|---|---|
| `docs/calibration/` (вся папка) | `docs/ARCHIVE/calibration_phase1/` | Все файлы Phase 1 от 2026-04-30 |
| `docs/audit/` (вся папка) | `docs/ARCHIVE/audits_2026-04/` | Аудиты 2026-04-30 |
| `docs/decision_log/` (вся папка) | `docs/ARCHIVE/decision_log_2026-04/` | 1 файл от 2026-04-30 |
| `docs/release_history/` (вся папка) | `docs/ARCHIVE/release_history/` | 80+ старых FIX*_NOTES.txt |
| `docs/history/` (вся папка) | `docs/ARCHIVE/history/` | Старые чек-листы и манифесты |
| `docs/SESSIONS/` (вся папка) | `docs/ARCHIVE/sessions/` | 1 файл 2026-05-04 |
| `docs/SPRINTS/SPRINT_2026-05-04*.md` (2 шт) | `docs/ARCHIVE/sprints/` | Только последний живой |
| `docs/REGULATION_v0_1.md` | `docs/ARCHIVE/regulation_v0_1.md` | Заменён v0_1_1 |
| `docs/OPPORTUNITY_MAP_v1.md` | `docs/ARCHIVE/opportunity_map_v1.md` | Заменён v2 |
| `docs/HANDOFF_*` старые | `docs/ARCHIVE/handoffs_old/` ИЛИ `docs/HANDOFFS/` | См. Группу A |
| `docs/REAL_SUMMARY_2026-04-28.md` | `docs/ARCHIVE/` | Снимок недельной давности |
| `docs/ENGINE_BUG_HYPOTHESES_2026-04-30.md` | `docs/ARCHIVE/` | Снимок диагностики |
| `docs/CONTEXT/MAIN_CHAT_OPENING_PROMPT_2026-05-04.md` | `docs/ARCHIVE/` | Одноразовый промпт |
| `docs/CONTEXT/SESSION_DELTA_2026-05-02.md` | `docs/ARCHIVE/` | Дельта старой сессии |
| `docs/CONTEXT/main_prompt_audit_2026-05-03.md` | `docs/ARCHIVE/` | Аудит промпта |

---

### Группа D — _*.json/png сырые артефакты в `_artifacts/`

**Действие**:
- `docs/RESEARCH/_*.json` и `_*.png` (17 файлов) → `docs/RESEARCH/_artifacts/`
- `docs/ANALYSIS/_*.json` (10 файлов) → `docs/ANALYSIS/_artifacts/`
- `docs/DESIGN/_classifier_disagreement_raw.json` → `docs/DESIGN/_artifacts/`

**Плюсы**: финальные `.md` отчёты остаются на виду, raw-данные не маячат.

---

### Группа E — superseded версии в ARCHIVE

| Файл | Статус |
|---|---|
| `docs/RESEARCH/REGIME_OVERLAY_v1.md` | SUPERSEDED → ARCHIVE |
| `docs/RESEARCH/REGIME_OVERLAY_v1_CROSSCHECK.md` | ARCHIVED → ARCHIVE |
| `docs/RESEARCH/REGIME_OVERLAY_v2.md` | SUPERSEDED → ARCHIVE |
| `docs/RESEARCH/REGIME_OVERLAY_v3.md` | **НЕ ТРОГАЮ** (UNCLEAR — твой ответ был «нет ответа») |
| `docs/RESEARCH/TRANSITION_MODE_COMPARE_v1.md` | SUPERSEDED → ARCHIVE |
| `docs/RESEARCH/FORECAST_MODEL_REPLACEMENT_RESEARCH_v1_codex.md` | SUPERSEDED → ARCHIVE |
| `docs/RESEARCH/MARKET_DECISION_SUPPORT_RESEARCH_v1_codex.md` | SUPERSEDED → ARCHIVE |

---

### Группа F — TZ-папки в одну (средний риск)

**Действие**:
1. Создать `docs/TZ/` (uppercase, единственная)
2. `docs/tz/TZ-005..010` → `docs/ARCHIVE/tz_old/` (старая нумерация, закрытые TZ)
3. `docs/TZs/TZ-MORNING-BRIEF-MULTITRACK-ADAPT.md` → `docs/TZ/` (если живой) или `docs/ARCHIVE/`
4. `docs/specs/ADVISE_V2_SPEC_2026-04-30.md` → `docs/TZ/` или `docs/ARCHIVE/` (по статусу advise v2 — DONE? тогда ARCHIVE)
5. Удалить пустые `docs/tz/`, `docs/TZs/`, `docs/specs/`

**Нужно решение**: TZ-MORNING-BRIEF-MULTITRACK-ADAPT — это закрытая или активная TZ?

---

### Группа G — операторские мануалы вместе

**Действие**: создать `docs/OPERATOR/`, переместить:
- `docs/PLAYBOOK.md` → `docs/OPERATOR/PLAYBOOK.md`
- `docs/PLAYBOOK_MANUAL_LAUNCH_v1.md` → `docs/OPERATOR/PLAYBOOK_MANUAL_LAUNCH_v1.md`
- `docs/OPERATOR_DEDUP_MONITORING.md` → `docs/OPERATOR/OPERATOR_DEDUP_MONITORING.md`
- `docs/OPERATOR_NIGHT_DOWNLOAD_1S_OHLCV.md` → `docs/OPERATOR/OPERATOR_NIGHT_DOWNLOAD_1S_OHLCV.md`
- `docs/CLEANUP_GUIDE.md` → `docs/OPERATOR/CLEANUP_GUIDE.md`

---

### Группа H — dashboard-фронт переехать в код

**Спорный пункт**: `docs/dashboard.html`, `dashboard.css`, `dashboard.js`, `state_inline.js` — это рабочий фронт дашборда. Логически это **код**, а не документация.

**Предложение**: переместить в `services/dashboard/static/` или `web/dashboard/`. **Но**: возможно на эти пути ссылается какой-то код, прежде чем двигать — прогрепить.

**Альтернатива**: оставить как есть, документация про дашборд это нормально.

**Нужно решение**.

---

### Группа I — корневой мусор без статуса

Эти файлы я не классифицировал — **прошу тебя пройтись и сказать какие живые**:

- `docs/MASTER.md` — большой агрегатор, проверить актуальность
- `docs/SESSION_LOG.md` — что это, кто пишет, когда последний раз обновлялся
- `docs/PROJECT_MANIFEST.md` — старый? новый?
- `docs/NEXT_CHAT_PROMPT.md` — одноразовый или живой шаблон?
- `docs/BASELINE_INVESTIGATION_DESIGN_v0.1.md` — статус?
- `docs/CALIBRATION_LOG_DESIGN_v0.1.md` — статус? (есть ли соответствующий код?)
- `docs/KILLSWITCH_DESIGN_v0.1.md` — реализован? тогда DONE → ARCHIVE
- `docs/ORCHESTRATOR_LOOP_DESIGN_v0.1.md` — реализован? (orchestrator есть в коде → ARCHIVE?)
- `docs/ORCHESTRATOR_TELEGRAM_DESIGN_v0.1.md` — то же самое
- `docs/CONTEXT/MAIN_PROJECT_SETUP_GUIDE_2026-05-04.md` — актуален?
- `docs/CONTEXT/STATE_CURRENT.md` vs `STATE_CURRENT_2026-05-05_EOS.md` — какой канон?
- `docs/STATE/ROADMAP.md` vs `docs/PLANS/MULTI_TRACK_ROADMAP.md` — какой канон?
- `docs/STATE/QUEUE.md` vs `docs/STATE/PENDING_TZ.md` — оба или один?
- `docs/CANON/INDEX.md` vs `docs/INDEX.md` (этот) — мерджить или оставить отдельно?
- `docs/CANON/RUNNING_SERVICES_INVENTORY_2026-04-30.md` — обновить или ARCHIVE?

---

## Что я сделаю автоматизированно после твоего одобрения

1. Перед каждой Группой — `git grep` ссылок на старые пути; покажу что сломается.
2. Использую `git mv` (история сохраняется).
3. Один коммит на одну Группу с понятным сообщением.
4. После каждой Группы — обновляю `INDEX.md`.

## Что НЕ буду делать без явного «да»

- Удалять что-либо безвозвратно (всё в `ARCHIVE/`)
- Трогать `docs/dashboard.*` (Группа H)
- Решать про UNCLEAR (REGIME_OVERLAY_v3, TZ-папки, файлы из Группы I)

---

## Следующий шаг

Скажи по группам коротко — например `A,B,C,D,E,G — да; F,H — нет; I — отвечу позже`.

Дальше делаю Группу A (handoff'ы), показываю diff, если ок — Группу B, и так далее.
