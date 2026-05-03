# MAIN COORDINATOR USAGE GUIDE
# Версия: 1.0 — 2026-05-03
# Назначение: Оперативное руководство по системе MAIN coordinator.

---

## Что такое MAIN coordinator

MAIN — это стратегический слой планирования поверх рабочих сессий (worker). Он:

- **Владеет** недельным планом (`docs/PLANS/WEEK_*.md`)
- **Генерирует** дневной SPRINT (`docs/SPRINTS/SPRINT_YYYY-MM-DD.md`)
- **Валидирует** вечерние deliverable
- **Детектирует** drift и инициирует перепланировку
- **НЕ пишет** код напрямую — делегирует в worker-сессии

---

## Быстрый старт

### Утро (каждый рабочий день)

```bash
# Сгенерировать SPRINT на сегодня
python scripts/main_morning_brief.py \
    --week docs/PLANS/WEEK_2026-05-04_to_2026-05-10.md

# Проверить operator pending actions
cat docs/STATE/STATE_CURRENT.md | grep -A 20 "§5 OPERATOR"
```

SPRINT записывается в `docs/SPRINTS/SPRINT_YYYY-MM-DD.md`. Скопировать в worker-чат.

### Вечер (каждый рабочий день)

```bash
# Валидировать deliverable
python scripts/main_evening_validate.py \
    --sprint docs/SPRINTS/SPRINT_2026-05-04.md

# Обновить STATE_CURRENT.md §2, §4, §6
# Закоммитить
git add docs/STATE/STATE_CURRENT.md docs/PLANS/ docs/SPRINTS/
git commit -m "chore(coordinator): EOD 2026-05-04 state update"
```

### Воскресенье вечером (планирование недели)

```bash
# Скопировать шаблон
cp docs/PLANS/WEEK_TEMPLATE.md \
   docs/PLANS/WEEK_2026-05-11_to_2026-05-17.md

# Заполнить план
# Проверить PENDING_TZ.md на открытые задачи
# Проверить DEPRECATED_PATHS.md — что нельзя повторять
# Проверить DRIFT_HISTORY.md — известные anti-patterns
```

---

## Файловая структура

```
docs/
├── PLANS/
│   ├── WEEK_TEMPLATE.md              # шаблон недельного плана
│   └── WEEK_YYYY-MM-DD_to_*.md      # актуальный план недели
├── SPRINTS/
│   ├── SPRINT_TEMPLATE.md            # шаблон спринта
│   └── SPRINT_YYYY-MM-DD.md          # дневной спринт (генерируется)
├── CONTEXT/
│   ├── STATE_CURRENT.md              # живое состояние проекта
│   ├── DEPRECATED_PATHS.md           # что нельзя строить заново
│   └── DRIFT_HISTORY.md              # known anti-patterns
└── STATE/
    ├── STATE_CURRENT.md              # то же, копия (основной файл)
    ├── PENDING_TZ.md                 # очередь открытых TZ
    └── QUEUE.md                      # детальный навигатор очереди

scripts/
├── main_morning_brief.py             # генератор SPRINT
└── main_evening_validate.py          # валидатор deliverable

.claude/skills/
├── main_coordinator_protocol.md     # полный протокол MAIN
└── anti_drift_validator.md          # drift detection checks

reports/
└── MAIN_COORDINATOR_USAGE_GUIDE.md  # этот файл
```

---

## Скрипты

### `scripts/main_morning_brief.py`

```
python scripts/main_morning_brief.py [OPTIONS]

Options:
  --week PATH    Путь к WEEK_*.md файлу [обязательный]
  --day DATE     Дата YYYY-MM-DD (по умолчанию: сегодня)
  --dry-run      Вывести SPRINT в stdout, не писать файл

Output: docs/SPRINTS/SPRINT_<date>.md
```

**Что генерирует:**
- TODAY'S GOAL — из соответствующего DAY N в week plan
- Operator pending actions — из STATE_CURRENT.md §5
- TODAY'S TZs — таблица из week plan
- HARD DELIVERABLES — checkboxes из week plan
- GATE — если checkpoint-день
- VERIFY COMMANDS — из week plan
- ANTI-DRIFT REMINDERS — статичные напоминания

### `scripts/main_evening_validate.py`

```
python scripts/main_evening_validate.py [OPTIONS]

Options:
  --sprint PATH   Путь к SPRINT_*.md файлу [обязательный]
  --strict        Exit 1 при любом предупреждении
  --no-verify     Не запускать verify commands

Exit codes:
  0 — все deliverable пройдены
  1 — есть failures или drift
```

**Что валидирует:**
- Файловые deliverable: `ls` существует?
- Тестовые deliverable: `pytest --collect-only` >= N?
- Метрические deliverable: `Brier ≤X` — флагует для ручной проверки
- Commit deliverable: `git log --since=today` есть коммиты?
- Drift detection: 2+ failed → drift-, все failed → drift- critical

---

## Skills

### `main_coordinator_protocol`

Загружать в каждой MAIN-сессии. Содержит:
- Утренний протокол
- Вечерний протокол
- Протокол планирования недели
- Протокол перепланирования
- Правила чего MAIN делает/не делает

### `anti_drift_validator`

Запускать перед каждой TZ. 5 чеков:
1. **Pre-TZ inventory** — TZ не дублирует существующую? Данные есть?
2. **Scope boundary (drift+)** — каждый deliverable в спеке?
3. **Completeness (drift-)** — все deliverable выполнены?
4. **Time drift** — задача не вышла за 2x estimate?
5. **Replan triggers** — gate failed / blocker discovered?

---

## Недельный цикл

```
Воскресенье
  └─ Заполнить WEEK_*.md из шаблона
  └─ Проверить PENDING_TZ.md
  └─ Отправить оператору на апрув

Понедельник-Пятница (каждый день)
  Утро:
    └─ main_morning_brief.py → SPRINT_*.md
    └─ Вставить SPRINT в worker-чат
    └─ anti_drift_validator CHECK 1 для каждой TZ
  
  Работа:
    └─ Worker-сессии выполняют TZ из SPRINT
    └─ Коммитят deliverable
  
  Вечер:
    └─ main_evening_validate.py → отчёт
    └─ Обновить STATE_CURRENT.md §2, §4, §6
    └─ Если drift → обновить DRIFT_HISTORY.md
    └─ EOD commit

Суббота
  └─ Только если Friday deliverables не закрыты

Воскресенье
  └─ Ретроспектива (заполнить WEEKLY RETROSPECTIVE в week plan)
  └─ Следующий week plan
```

---

## Replan triggers

Немедленно перепланировать при ЛЮБОМ из:

| Триггер | Действие |
|---------|----------|
| CP gate fail (Brier > threshold, tests red) | STOP worker, notify operator |
| Оператор не загрузил данные к дедлайну | Pull следующую TZ вперёд |
| 2+ hard deliverable пропущены за день | Mid-week replan |
| Critical blocker (API down, data missing) | Escalate → replan |
| Operator меняет направление | Новый week plan |

---

## Anti-patterns (не делать)

| Что | Почему | Источник |
|-----|--------|---------|
| Запускать TZ без inventory check | Дублирование, premature deps | DRIFT-003 |
| Добавлять scope mid-TZ "пока я тут" | drift+ scope creep | DRIFT-001 |
| Держать сервис RUNNING и считать его активным | INERT-BOTS confusion | DRIFT-002 |
| Продолжать tuning после 3 попыток без улучшения | Calibration ceiling | DRIFT-005 |
| Планировать >6 deliverable без interim commit | Context loss mid-TZ | DRIFT-004 |
| Повторять deprecated подход | Потраченное время | DEPRECATED_PATHS.md |

---

## FAQ

**Q: Как узнать какие TZ открыты?**
```bash
cat docs/STATE/PENDING_TZ.md
# или
cat docs/STATE/QUEUE.md
```

**Q: Как создать новую неделю?**
```bash
cp docs/PLANS/WEEK_TEMPLATE.md docs/PLANS/WEEK_2026-05-11_to_2026-05-17.md
# Заполнить секции вручную или через MAIN coordinator skill
```

**Q: Sprint не отражает изменения в week plan?**
```bash
# Перегенерировать
python scripts/main_morning_brief.py --week docs/PLANS/WEEK_*.md
```

**Q: Validate говорит что файл не найден, но он есть?**
- Проверить: путь в deliverable совпадает с реальным путём от ROOT
- Использовать относительный путь от c:\bot7

**Q: Когда использовать `--strict`?**
- При gate-дне (CP1/CP2/CP3) — любое предупреждение = блокер
- В обычный день — без `--strict` (предупреждения фиксируются, но не блокируют)
