# docs/

Документация проекта bot7 — Grid Orchestrator для GinArea / BitMEX.

## С чего начинать новую сессию

1. **`MASTER.md`** — главный документ. §0 правила общения / К-косяки, §16 OPERATOR TRADING PROFILE.
2. **`CONTEXT/PROJECT_CONTEXT.md`** — обзорная страница входа.
3. **`CONTEXT/STATE_CURRENT.md`** — текущий operational status (фазы, blocker'ы, week priority queue).
4. **последний HANDOFF** — `Handoff_2026-05-06.md` (или последний на дату сессии).

## Карта документации

- **`INDEX.md`** — карта всех файлов docs/ со статусами (AUTHORITATIVE / REFERENCE / ARCHIVED / SUPERSEDED / UNCLEAR).
- **`GROUP_I_AUDIT.md`** — детальные карточки 39 ключевых файлов с ключевыми решениями (D-018..D-104, INC, P-15, K-числа). Ничего не забыто при cleanup.
- **`CLEANUP_PROPOSAL.md`** — план реструктуризации по группам A-I.

## Структура (после cleanup 2026-05-07)

```
docs/
├── MASTER.md                       Главный документ стратегии
├── PLAYBOOK.md                     Confirmed P-1..P-12 (machine-readable)
├── PLAYBOOK_MANUAL_LAUNCH_v1.md    Pre-launch checklist первого бота
├── OPPORTUNITY_MAP_v2.md           Sizing rules + cost model
├── REGULATION_v0_1_1.md            Active operational regulation
├── INCIDENTS.md                    Журнал инцидентов с prevention rules
├── GINAREA_MECHANICS.md            Технический reference платформы
├── INDEX.md / GROUP_I_AUDIT.md     Cleanup / навигация
│
├── CONTEXT/                        Живая шапка проекта
│   ├── PROJECT_CONTEXT.md          Обзор + правила
│   ├── STATE_CURRENT.md            Текущий status
│   ├── DRIFT_HISTORY.md            История дрейфа решений
│   ├── DEPRECATED_PATHS.md         Deprecated paths registry
│   ├── SESSION_CLOSE_2026-05-05.md Session close snapshot 05.05
│   ├── MAIN_PROJECT_SETUP_GUIDE_2026-05-04.md  Setup MAIN coordinator
│   └── MAIN_COORDINATOR_INSTRUCTIONS.md        Custom instructions для Claude.ai Project
│
├── DESIGN/                         Архитектурные специи (v1+)
│   ├── DECISION_LAYER_v1.md
│   ├── MTF_DISAGREEMENT_v1.md
│   ├── MTF_FEASIBILITY_v1.md
│   ├── CLASSIFIER_AUTHORITY_v1.md
│   └── (P8 components, BOT_ID_SCHEMA, SIZING_MULTIPLIER)
│
├── RESEARCH/                       Исследовательские отчёты + foundation evidence
│   ├── REGIME_OVERLAY_v2_1.md      21 GinArea runs allocation per regime
│   ├── HYSTERESIS_CALIBRATION_v1.md
│   ├── TRANSITION_MODE_COMPARE_v2.md
│   ├── FORECAST_CALIBRATION_DIAGNOSTIC_v1.md
│   ├── MTF_CALIBRATION_HISTOGRAM_v1.md
│   └── ... (другие .md + сырые _*.json/png)
│
├── STATE/                          Живые snapshots / inventory
│   ├── CURRENT_STATE_latest.md     Последний auto-snapshot
│   ├── PROJECT_MAP.md              Auto-generated карта модулей
│   ├── RUNNING_SERVICES_INVENTORY.md  16 asyncio tasks (regenerated 2026-05-07)
│   ├── BOT_INVENTORY.md            22 live ботов (включая P-16 booster)
│   ├── PENDING_TZ.md               Текущая очередь TZ
│   ├── TELEGRAM_EMITTERS_INVENTORY.md
│   └── (auto-rotation snapshots)
│
├── PLANS/                          Roadmap / sprint planning
│   ├── MULTI_TRACK_ROADMAP.md
│   ├── WEEK_2026-05-04_to_2026-05-10.md
│   └── WEEK_TEMPLATE.md
│
├── SPRINTS/                        Текущий sprint
│
├── ANALYSIS/                       Кросс-чеки CC ↔ Codex по сессиям
│
├── CANON/                          Backlog'и оператора (что не дублируется в MASTER)
│   ├── INDEX.md                    Карта + история merge'ей
│   ├── HYPOTHESES_BACKLOG.md       P-NN draft гипотезы
│   └── OPERATOR_QUESTIONS.md       Q-1..Q-N открытые вопросы
│
├── ARCHIVE/                        Ничего не удалено безвозвратно
│   ├── design_v0_1/                Killed by реализацией в коде (BASELINE/CALIBRATION/KILLSWITCH/ORCHESTRATOR designs)
│   └── superseded_2026-05-07/      REGULATION_v0_1, CLEANUP_GUIDE, NEXT_CHAT_PROMPT, OPERATOR_NIGHT_DOWNLOAD, STRATEGY_CANON, RUNNING_SERVICES_INVENTORY, CUSTOM_BOTS_REGISTRY, QUEUE, ROADMAP, PROJECT_MANIFEST и др.
│
└── (прочие подпапки: api/, github/, history/, release_history/, audit/, calibration/, decision_log/, managed_grid_sim/, setup_backtest/, STRATEGIES/)
```

## Routine оператора

- **Утро**: открыть `CONTEXT/STATE_CURRENT.md` + последний `HANDOFF_*.md`
- **Конец сессии**: один абзац в текущий handoff + commit
- **Еженедельно**: `PLANS/WEEK_*` обновить

Полный protocol: `CONTEXT/MAIN_PROJECT_SETUP_GUIDE_2026-05-04.md`.

## Cleanup history

- **2026-04-26** — `CLEANUP_GUIDE.md` (теперь в ARCHIVE) предложил консолидацию в MASTER+PLAYBOOK+SESSION_LOG. Частично применён.
- **2026-05-07** — Группа I cleanup: 14 файлов в ARCHIVE (всё superseded), уникальное содержание слито в живые документы. Полный аудит: `GROUP_I_AUDIT.md`.
