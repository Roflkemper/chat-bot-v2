# CLEANUP GUIDE — что делать со старыми файлами

После переноса MASTER.md / PLAYBOOK.md / SESSION_LOG.md в `C:\bot7\docs\`.

---

## Что делать со старыми файлами

Создать папку `C:\bot7\docs\archive\2026-04-26_pre_consolidation\` и переместить туда **все** старые .md (кроме новых трёх). Список:

### MASTER_CONTEXT* (4 файла)
- MASTER_CONTEXT.md
- MASTER_CONTEXT_v1.2.md
- MASTER_CONTEXT_v1_3.md
- → **АРХИВ**. Содержание перенесено в MASTER.md §1, §11.

### STRATEGY* (3 файла)
- STRATEGY_v1.md
- STRATEGY_v1.3.md
- STRATEGY_v1_4.md
- → **АРХИВ**. Принципы перенесены в MASTER §7. Каталог приёмов — в PLAYBOOK.md.

### TZ_QUEUE* (2 файла)
- TZ_QUEUE.md
- TZ_QUEUE_v2.md
- TZ_QUEUE_v3.md
- → **АРХИВ**. Очередь работ — в MASTER §12.

### DECISIONS* (2 файла)
- DECISIONS.md
- DECISIONS_v2.md
- DECISIONS_v3.md
- → **АРХИВ**. Текущие решения — в SESSION_LOG.md (последняя запись D-018 до D-025).

### LESSONS_LEARNED* (2 файла)
- LESSONS_LEARNED.md
- LESSONS_LEARNED_v2.md
- → **АРХИВ**. Косяки К14-К20 — в MASTER §0.

### SESSION_HANDOFF* (2 файла)
- SESSION_HANDOFF.md
- SESSION_HANDOFF_v2.md
- SESSION_HANDOFF_v3.md
- → **АРХИВ**. Заменено протоколом начала сессии в MASTER §14.

### Дизайн-документы (3 файла)
- KILLSWITCH_DESIGN_v0.1.md
- ORCHESTRATOR_LOOP_DESIGN_v0.1.md
- ORCHESTRATOR_TELEGRAM_DESIGN_v0.1.md
- CALIBRATION_LOG_DESIGN_v0.1.md
- BASELINE_INVESTIGATION_DESIGN_v0.1.md
- → **АРХИВ**. Это дизайны модулей которые уже в проде или устарели. При необходимости вернуться можно.

### Технические референсы (СОХРАНИТЬ как есть, не архивировать)
- **GINAREA_MECHANICS.md** — это НЕ архивировать, оставить рядом с MASTER. Это reference на API GinArea и механику параметров. Источник истины для бэктест-движка.
- **ROADMAP_BACKTEST.md** — устарел, **АРХИВ**. План работ — в MASTER §12.

### Прочее
- **PROJECT_MANIFEST.md** — АРХИВ (дублируется в MASTER §0 §1)
- **README.md** — оставить, **обновить** под новую структуру (3 рабочих файла + GINAREA_MECHANICS)

### Драфты сегодняшней сессии
- PLAYBOOK_DRAFT_v0_1.md — АРХИВ
- PLAYBOOK_DRAFT_v0_2.md — АРХИВ (заменён PLAYBOOK.md v1.0)
- TZ_COUNTER_LONG_AUTO.md, TZ_BOUNDARY_EXPAND.md, TZ_ADAPTIVE_GRID.md, TZ_ANTI_SPAM.md, TZ_DEBT_02*.md — оставить в `archive/tz_2026-04-26/`. Это рабочие ТЗ, после реализации = историческая документация.

---

## Результат

После cleanup в `C:\bot7\docs\` останется:

```
C:\bot7\docs\
├── MASTER.md              ← новый, единый источник правды
├── PLAYBOOK.md            ← новый, machine-readable приёмы
├── SESSION_LOG.md         ← новый, append-only журнал
├── GINAREA_MECHANICS.md   ← reference на API, не трогать
├── README.md              ← обновлён под новую структуру
└── archive/
    └── 2026-04-26_pre_consolidation/
        └── (21 старый файл)
```

Это всё. Любые новые правки — в MASTER, PLAYBOOK, SESSION_LOG. Не плодим новые .md.

---

## Команды для выполнения (PowerShell на Windows)

```powershell
cd C:\bot7\docs

# Создать папку архива
New-Item -ItemType Directory -Path "archive\2026-04-26_pre_consolidation" -Force
New-Item -ItemType Directory -Path "archive\tz_2026-04-26" -Force

# Переместить старые .md в архив
$files_to_archive = @(
    "MASTER_CONTEXT.md", "MASTER_CONTEXT_v1.2.md", "MASTER_CONTEXT_v1_3.md",
    "STRATEGY_v1.md", "STRATEGY_v1.3.md", "STRATEGY_v1_4.md",
    "TZ_QUEUE.md", "TZ_QUEUE_v2.md", "TZ_QUEUE_v3.md",
    "DECISIONS.md", "DECISIONS_v2.md", "DECISIONS_v3.md",
    "LESSONS_LEARNED.md", "LESSONS_LEARNED_v2.md",
    "SESSION_HANDOFF.md", "SESSION_HANDOFF_v2.md", "SESSION_HANDOFF_v3.md",
    "KILLSWITCH_DESIGN_v0.1.md",
    "ORCHESTRATOR_LOOP_DESIGN_v0.1.md",
    "ORCHESTRATOR_TELEGRAM_DESIGN_v0.1.md",
    "CALIBRATION_LOG_DESIGN_v0.1.md",
    "BASELINE_INVESTIGATION_DESIGN_v0.1.md",
    "ROADMAP_BACKTEST.md",
    "PROJECT_MANIFEST.md",
    "PLAYBOOK_DRAFT_v0_1.md",
    "PLAYBOOK_DRAFT_v0_2.md"
)

foreach ($f in $files_to_archive) {
    if (Test-Path $f) {
        Move-Item $f "archive\2026-04-26_pre_consolidation\" -Force
        Write-Host "Archived: $f"
    }
}

# Переместить TZ файлы
$tz_files = @(
    "TZ_COUNTER_LONG_AUTO.md",
    "TZ_BOUNDARY_EXPAND.md",
    "TZ_ADAPTIVE_GRID.md",
    "TZ_ANTI_SPAM.md",
    "TZ_DEBT_02.md",
    "TZ_DEBT_02_FIX_v1.md",
    "TZ_DEBT_02_INVESTIGATE_v3.md",
    "TZ_DEBT_02_FIX_v2.md"
)

foreach ($f in $tz_files) {
    if (Test-Path $f) {
        Move-Item $f "archive\tz_2026-04-26\" -Force
        Write-Host "TZ archived: $f"
    }
}

Write-Host "Cleanup done. Active files:"
Get-ChildItem -Filter "*.md"
```

После выполнения — в папке должно остаться 4-5 .md файлов: MASTER, PLAYBOOK, SESSION_LOG, GINAREA_MECHANICS, README.

---

## Финальный шаг

Обновить README.md одним абзацем:

```markdown
# Grid Orchestrator

Single-file documentation:
- **MASTER.md** — единый источник правды по проекту
- **PLAYBOOK.md** — каталог торговых приёмов (machine-readable)
- **SESSION_LOG.md** — журнал сессий
- **GINAREA_MECHANICS.md** — reference на API GinArea

Старые версии docs в `archive/`.

Начало новой сессии Claude:
> Прочти MASTER.md, PLAYBOOK.md и последние 3 записи SESSION_LOG.md.
> Подтверди в 5 строках: главная цель проекта, текущая фаза, следующие 3 шага.
```

Готово.
