# CANON INDEX

**docs/CANON/ — узкоспециализированные backlog'и оператора.**

> **2026-05-07 cleanup**: STRATEGY_CANON_2026-04-30, RUNNING_SERVICES_INVENTORY_2026-04-30, CUSTOM_BOTS_REGISTRY заархивированы — их уникальное содержимое **слито в живые документы** (см. ниже). После merge'а CANON/ содержит только ту информацию которая **не дублируется** в MASTER/PLAYBOOK/STATE.
>
> История слияний задокументирована в `docs/GROUP_I_AUDIT.md` и `docs/CLEANUP_PROPOSAL.md`.

---

## Что осталось в CANON/

| Файл | Назначение |
|---|---|
| `HYPOTHESES_BACKLOG.md` | P-NN draft гипотезы (P-15+) — то что ещё не CONFIRMED в PLAYBOOK |
| `OPERATOR_QUESTIONS.md` | Q-1..Q-N открытые вопросы оператора для backtest framework |
| `INDEX.md` | этот файл |

## Что переехало (2026-05-07)

| Откуда | Куда | Что именно |
|---|---|---|
| STRATEGY_CANON_2026-04-30 §1-§7,§10 | `MASTER.md` §16.8 / §16.9 / §16.10 | Метрики (net BTC, currency hedge ratio), $10.5M target, конкурс $618k, цикл-смерти, gaps G-1..G-13 |
| STRATEGY_CANON_2026-04-30 §6.5 | `STATE/RUNNING_SERVICES_INVENTORY.md` | Live asyncio tasks (regenerated, 16 tasks vs old 11) |
| CUSTOM_BOTS_REGISTRY → Bot 6399265299 | `STATE/BOT_INVENTORY.md` (Bot 6399265299 row) | P-16 Post-impulse SHORT booster activation procedure |
| RUNNING_SERVICES_INVENTORY_2026-04-30 | `STATE/RUNNING_SERVICES_INVENTORY.md` | Полный regenerated inventory + старая версия в ARCHIVE |

Архивные копии всех слитых файлов: `docs/ARCHIVE/superseded_2026-05-07/`.

---

## Связи с другими docs

- `docs/MASTER.md` — стратегия (включая §16 OPERATOR TRADING PROFILE = главный документ оператора)
- `docs/PLAYBOOK.md` — confirmed P-1..P-12
- `docs/OPPORTUNITY_MAP_v2.md` — sizing rules + cost model
- `docs/RESEARCH/REGULATION_v0_1_1.md` — operational regulation
- `docs/STATE/PENDING_TZ.md` — текущая очередь
- `docs/STATE/PROJECT_MAP.md` — auto-generated карта модулей кода
- `docs/STATE/RUNNING_SERVICES_INVENTORY.md` — live asyncio tasks
- `docs/STATE/BOT_INVENTORY.md` — реестр всех 22 ботов
