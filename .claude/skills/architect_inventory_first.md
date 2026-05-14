---
# Skill: architect inventory first

## For whom
Этот skill применяется ARCHITECT'ом (Claude в текущей сессии)
ПЕРЕД нарезанием TZ для Code или Codex. Это self-check, не
Code-side check.

## Trigger
Architect собирается отправить TZ оператору, который содержит:
- Создание нового модуля (новый .py файл с >50 строк)
- "implement", "build", "create new", "add feature" в формулировке
- Новый pydantic модель / новая функция в новом file
- Новый scheduler / cron / handler

## Mandatory steps BEFORE отправки TZ оператору

1. Architect формулирует TZ полностью.

2. ПЕРЕД отправкой проводит self-inventory check:

   a. Прочитать PROJECT_MAP.md (генерируется state_snapshot.py)
      — есть ли в active modules что-то с похожим именем
      / purpose?

   b. Прочитать RESTORED_FEATURES_AUDIT_<latest>.json
      — есть ли в restored relevant модули?
      Особенно проверить:
      - _recovery/restored/src/advisor/
      - _recovery/restored/src/whatif/
      - _recovery/restored/src/features/
      - active src/whatif/, src/advisor/

   c. Проверить что Skills applied секция в TZ содержит
      project_inventory_first.

   d. Проверить что PRE-FLIGHT блок содержит конкретные
      inventory checks (grep commands относящиеся к feature
      keywords).

3. Если на шаге 2.a/2.b найдены existing/restored implementations —
   STOP, не отправлять TZ. Вместо этого: нарезать
   TZ-INVENTORY-<feature> для Code сначала. Получить
   recommendation. Потом основной TZ.

4. Если на шаге 2.c/2.d пробелы — допилить TZ до отправки.

## Forbidden
- Полагаться на Code/Codex inventory check как primary defense.
  Они secondary — защита от architect ошибок, не замена.
- Отправлять TZ если architect не прочитал PROJECT_MAP +
  RESTORED_FEATURES_AUDIT для текущего feature.
- "Я думаю в restored ничего нет" без проверки.

## Allowed
- Skip self-inventory check для:
  - Pure tests (только tests, без production code)
  - Pure docs / markdown updates
  - Bug fixes на known existing files (path известен)
  - Audit / inventory TZs themselves (они сами inventory)

## Recovery
Если architect отправил TZ и Code rejected с "inventory check
found existing":
- Зафиксировать как self-check failure в INCIDENTS.md
- Немедленно run inventory TZ для feature
- Не пытаться "переписать" rejected TZ за один проход

## Why
INC-013: ARCHITECT trice during one session отправил TZ для
нового модуля без architect-side inventory check (signal_logger,
action_tracker — caught preemptively, weekly_comparison_report
— caught at submission). Каждый раз Code's inventory check
catch'ил пропуск. Это working safety net, но каждый incident
ломает flow и тратит cycle.

Skill enforces architect-side discipline.
