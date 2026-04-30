# CANON INDEX

**docs/CANON/ — source of truth для проекта.**
**Читается ПЕРВЫМ при старте каждой новой Claude/Code/Codex session.**

## Файлы (читать в этом порядке)

1. **STRATEGY_CANON_2026-04-30.md** — главный документ, архитектура
   стратегии, боли, принципы, статус компонентов
2. **HYPOTHESES_BACKLOG.md** — все P-NN паттерны и гипотезы
   (текущие + draft)
3. **OPERATOR_QUESTIONS.md** — открытые вопросы оператора
   (Q-1..Q-N) для backtest framework
4. **CUSTOM_BOTS_REGISTRY.md** — реестр всех live ботов оператора
   с ролями и активационными условиями
5. **RUNNING_SERVICES_INVENTORY_2026-04-30.md** — реестр всех
   11 asyncio tasks в app_runner с ролями, форматами Telegram
   сообщений, статусом active/legacy.

## Связи с другими docs

CANON ссылается на (но НЕ дублирует):
- docs/MASTER.md — оригинальные принципы P0-P8, action matrix
- docs/PLAYBOOK.md — полные YAML-блоки P-1..P-12
- docs/OPPORTUNITY_MAP_v1.md — sizing rules, fазовая карта
- docs/SESSION_LOG.md — эпизоды manual интервенций
- docs/STATE/STRATEGY_DIGEST_2026-04-30.md — выписки из docs
  с file:line ссылками

## Жизненный цикл CANON

- Создан: 2026-04-30
- Обновляется: при каждой новой gathered intelligence из session
- Format: append-mostly (не переписывать прошлые версии)
- Version: 1.0
