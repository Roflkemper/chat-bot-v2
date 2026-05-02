---
# Skill: phase aware planning

## For whom
Этот skill применяется ARCHITECT'ом (Claude) ПЕРЕД нарезанием
TZ, который может затрагивать функциональность будущих фаз
(Phase 2/3/4). Защищает от "перепрыгивания фаз" и работы
над Phase 3 пока Phase 1 не закрыт.

## Trigger
TZ упоминает любое из:
- **Phase 2 (Operator Augmentation):** /advise behavior change,
  weekly comparison report, paper journal automation, recommendation
  engine changes
- **Phase 3 (Tactical Bot Management):** GinArea API **write** ops
  (create/pause/resume/update_params), bot lifecycle automation,
  tactical interventions без оператора
- **Phase 4 (Full Auto):** автономное принятие торговых решений,
  bot-on-bot decisions, kill-switch automation engaging без
  оператора
- TZ ID содержит подстроки `ADVISE-V2`, `BOT-AUTO`, `TACTICAL`,
  `LIFECYCLE`, `AUTO-DEPLOY`, `FULL-AUTO`

## Rule
**Phase 2/3/4 TZs не нарезаются пока предыдущая фаза != done.**

Конкретно:
- Phase 2 TZ rejected, если Phase 1 != done
- Phase 3 TZ rejected, если Phase 2 != done
- Phase 4 TZ rejected, если Phase 3 != done

"Done" определяется exit criteria из docs/STATE/ROADMAP.md, не
по самочувствию. Phase 1 done = paper journal закрыл 14 дней
+ weekly report показывает положительный edge vs status quo.

## Mandatory steps BEFORE отправки TZ оператору

1. Architect открывает docs/CONTEXT/STATE_CURRENT.md §1
   PHASE STATUS. Записывает текущую фазу проекта.

2. Открывает docs/STATE/ROADMAP.md, читает exit criteria
   текущей фазы.

3. Сверяет TZ против triggers выше:
   - Если ни один не сработал → пропустить skill, продолжить
   - Если сработал → проверить статус соответствующей фазы

4. Если TZ относится к будущей фазе:
   - Не отправлять оператору
   - Положить в backlog с пометкой "BLOCKED on Phase N closure"
   - Если оператор явно настаивает — потребовать explicit
     phase-skip approval строкой в TZ

## Forbidden
- "Подготовительный код" к Phase 2/3 функциональности под видом
  Phase 0/1 TZ. Если код только понадобится после закрытия фазы
  — он не нужен сейчас.
- Маскировка Phase 3 (write ops) под Phase 2 read-only. Любая
  GinArea API write call относится к Phase 3.
- "Сделаем сейчас, чтобы потом было готово" — нарушает порядок
  exit criteria и блокирует ranking приоритетов.

## Allowed
- TZ-INVENTORY / TZ-DESIGN для будущей фазы — research-only
  документы без production-кода. Эти TZ помогают подготовить
  фазу, не реализуя её.
- Bug fixes на existing Phase 1 функциональности, даже если
  файл случайно используется в будущем коде Phase 2.
- TZ-VALIDATION тестов которые ещё не активированы в Phase 1
  flow (закрытое крыло).

## Recovery
Если TZ для будущей фазы был оформлен и Code rejected:
- Не "переписать" задачу под текущую фазу. Это маскировка.
- Зафиксировать в INCIDENTS.md
- Открыть отдельный TZ-PHASE-N-EXIT-CRITERIA если непонятно
  что блокирует закрытие текущей фазы

## Why
Roadmap фаз существует чтобы ranking приоритетов был prediктабильным
и оператор мог планировать своё участие. Перепрыгивание фаз
приводит к ситуации: сделана половина Phase 3 функциональности,
но Phase 1 paper journal не закрыт → нет данных оправдать Phase 2
изменения → Phase 3 код мёртв.

PROJECT_CONTEXT §9: "Phase awareness: Phase 2/3 TZs не нарезаются
пока Phase 1 не closed."
